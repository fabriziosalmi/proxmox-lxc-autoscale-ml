#!/usr/bin/env python3

import logging
import sys
import time

import pandas as pd
from collections import defaultdict
from datetime import datetime, timedelta

# Ensure all modules in the lxc_autoscale_ml directory are accessible
sys.path.append('/usr/local/bin/lxc_autoscale_ml')

# Import custom modules
from logger import setup_logging
from lock_manager import create_lock_file, remove_lock_file
from config_manager import load_config
from data_manager import load_data, preprocess_data
from model import train_anomaly_models, predict_anomalies
from scaling_decisions import determine_scaling_action, apply_scaling
from signal_handler import setup_signal_handlers
from async_api_client import fetch_container_configs_sync

CONFIG_PATH = "/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml"


# Circuit breaker state for API calls
class CircuitBreaker:
    """Simple circuit breaker to avoid hammering failed APIs."""
    def __init__(self, failure_threshold=3, timeout=300):
        self.failure_threshold = failure_threshold
        self.timeout = timeout  # seconds
        self.failures = defaultdict(int)
        self.opened_at = defaultdict(lambda: None)

    def is_open(self, key):
        """Check if circuit is open (blocking requests)."""
        if self.opened_at[key] is None:
            return False

        # Check if timeout has passed
        if datetime.now() - self.opened_at[key] > timedelta(seconds=self.timeout):
            logging.info(f"Circuit breaker for {key} timeout expired, attempting reset")
            self.reset(key)
            return False

        return True

    def record_failure(self, key):
        """Record a failure and open circuit if threshold reached."""
        self.failures[key] += 1
        if self.failures[key] >= self.failure_threshold:
            self.opened_at[key] = datetime.now()
            logging.warning(
                f"Circuit breaker opened for {key} after {self.failures[key]} failures. "
                f"Will retry in {self.timeout}s"
            )

    def record_success(self, key):
        """Record a success and reset circuit."""
        if self.failures[key] > 0:
            logging.info(f"Circuit breaker for {key} reset after successful request")
        self.reset(key)

    def reset(self, key):
        """Reset circuit breaker state."""
        self.failures[key] = 0
        self.opened_at[key] = None


def build_circuit_breaker(config):
    """Build the circuit breaker from the `circuit_breaker` config section.

    Previously hard-coded, so the documented settings had no effect.
    """
    breaker_config = config.get("circuit_breaker", {})
    if not breaker_config.get("enabled", True):
        logging.info("Circuit breaker disabled by configuration")
        return None
    return CircuitBreaker(
        failure_threshold=breaker_config.get("failure_threshold", 3),
        timeout=breaker_config.get("timeout_seconds", 300),
    )


def ignored_container_ids(config):
    """Container IDs excluded from autoscaling, as strings.

    The `ignore_lxc` list is compared as strings because container ids arrive
    from JSON object keys; a config written as `[101, 102]` must still match.
    """
    return {str(container_id) for container_id in config.get("ignore_lxc") or []}


def current_container_ids(df):
    """Container IDs present in the most recent snapshot.

    The metrics file keeps `max_metrics_entries` cycles of history and the
    monitor only records running containers, so a container's rows linger long
    after it stops existing.
    """
    latest = df["timestamp"].max()
    return [str(cid) for cid in df[df["timestamp"] == latest]["container_id"].unique()]


def metrics_are_stale(df, config):
    """True when the newest sample is too old to scale on.

    The monitor can wedge or die while the model keeps running. Without this
    check the model retrains and scales on a frozen snapshot forever, and
    because each target is absolute and derived from the live allocation, the
    allocation ratchets towards a limit on every cycle.
    """
    interval = config.get("interval_seconds", 60)
    max_age = config.get("max_metrics_age_seconds", interval * 3)
    newest = df["timestamp"].max()
    age = (pd.Timestamp.now() - newest).total_seconds()
    if age > max_age:
        logging.error(
            f"Newest metrics sample is {age:.0f}s old (limit {max_age:.0f}s). "
            f"The monitor may be stopped or wedged; refusing to scale on stale data."
        )
        return True
    return False


def run_cycle(config, circuit_breaker=None):
    """
    Run one full collection -> prediction -> scaling pass.

    Returns:
        bool: True if the cycle completed, False if it was skipped because the
        input data or the model was not usable. A skipped cycle is not fatal;
        the caller waits for the next interval and tries again.
    """
    df = load_data(config.get("data_file", "/var/log/lxc_metrics.json"))
    if df is None:
        logging.error("No usable metrics data; skipping this cycle.")
        return False

    df = preprocess_data(df, config)
    if df is None or df.empty:
        logging.error("Preprocessing produced no usable data; skipping this cycle.")
        return False

    if metrics_are_stale(df, config):
        return False

    model, features_to_use = train_anomaly_models(df, config)
    if model is None:
        logging.error("Model training failed; skipping this cycle.")
        return False

    logging.info("Processing containers for scaling decisions...")

    # Container ids are strings throughout: data_manager takes them from JSON
    # object keys. Comparing the column against int(container_id) matched no
    # rows at all, so the very first container raised IndexError and killed
    # the whole run.
    #
    # Only containers present in the NEWEST snapshot are evaluated. Taking
    # unique() over the whole retained history evaluated containers that were
    # stopped or destroyed hours ago -- and, because Proxmox reuses VMIDs, a
    # brand new container could be scaled on its predecessor's metrics until
    # the old rows aged out of the window.
    container_ids = current_container_ids(df)

    ignored = ignored_container_ids(config)
    if ignored:
        skipped = [cid for cid in container_ids if cid in ignored]
        container_ids = [cid for cid in container_ids if cid not in ignored]
        if skipped:
            logging.info(f"Ignoring containers listed in ignore_lxc: {', '.join(skipped)}")

    if not container_ids:
        logging.info("No containers to evaluate.")
        return True

    scaling_config = config.get("scaling", {})
    dry_run = bool(scaling_config.get("dry_run", False))
    if dry_run:
        logging.info("dry_run is enabled: scaling decisions will be logged, not applied.")
    min_confidence = scaling_config.get("min_confidence", 0)

    logging.info(f"Batch fetching configs for {len(container_ids)} containers...")
    batch_start = time.monotonic()

    api_config = config["api"]
    all_configs = fetch_container_configs_sync(
        container_ids,
        api_config["api_url"],
        circuit_breaker=circuit_breaker,
        # `timeout` is accepted as well for configs written against the
        # older documentation.
        timeout=api_config.get("timeout_seconds", api_config.get("timeout", 5)),
        max_concurrent=api_config.get("max_concurrent", 10),
    )

    batch_duration = time.monotonic() - batch_start
    successful_fetches = sum(1 for c in all_configs.values() if c is not None)
    rate = successful_fetches / batch_duration if batch_duration > 0 else float("inf")
    logging.info(
        f"Batch fetch completed in {batch_duration:.2f}s: "
        f"{successful_fetches}/{len(container_ids)} successful "
        f"({rate:.1f} containers/sec)"
    )

    for container_id in container_ids:
        try:
            evaluate_container(
                container_id=container_id,
                df=df,
                model=model,
                features_to_use=features_to_use,
                container_config=all_configs.get(container_id),
                config=config,
                dry_run=dry_run,
                min_confidence=min_confidence,
            )
        except Exception:
            # One bad container must not abandon the rest of the fleet.
            logging.exception(f"Failed to evaluate container {container_id}; continuing.")

    return True


def evaluate_container(container_id, df, model, features_to_use, container_config,
                       config, dry_run, min_confidence):
    """Decide and, unless dry_run is set, apply scaling for one container."""
    container_data = df[df["container_id"] == container_id]
    if container_data.empty:
        logging.warning(f"No metrics rows for container {container_id}; skipping.")
        return

    latest_metrics = container_data.iloc[-1].copy()

    # Every target this function computes is ABSOLUTE -- `pct set -cores N`,
    # not a delta -- and every one is derived from the container's current
    # allocation. Substituting the configured minimum when the fetch failed
    # therefore does not degrade gracefully: it writes the container down to
    # the floor in a single cycle, and the write is self-masking because the
    # next fetch then reports the value we just imposed. Skip instead.
    cores = (container_config or {}).get("cores")
    memory_mb = (container_config or {}).get("memory_mb")
    if cores is None or memory_mb is None:
        logging.warning(
            f"Skipping container {container_id}: its current allocation is unknown "
            f"({'no response from the API' if not container_config else 'response missing cores/memory_mb'}). "
            f"Scaling from a guessed allocation would resize it to the wrong absolute value."
        )
        return

    latest_metrics["current_cores"] = cores
    latest_metrics["current_ram_mb"] = memory_mb
    logging.debug(
        f"Container {container_id} current config: {cores} cores, {memory_mb} MB RAM")

    scaling_decision, confidence = predict_anomalies(
        model, latest_metrics, features_to_use, config)

    if scaling_decision is None:
        logging.warning(f"Skipping scaling for container {container_id} due to lack of prediction.")
        return

    cpu_action, ram_action, new_cores, new_ram = determine_scaling_action(
        latest_metrics, scaling_decision, confidence, config)

    logging.debug(
        f"Scaling decision for container {container_id}: "
        f"CPU - {cpu_action}, RAM - {ram_action} | Confidence: {confidence:.2f}%"
    )

    if cpu_action == "No Scaling" and ram_action == "No Scaling":
        logging.info(f"No scaling needed for container {container_id}. | Confidence: {confidence:.2f}%")
        return

    if confidence < min_confidence:
        logging.info(
            f"Skipping scaling for container {container_id}: confidence "
            f"{confidence:.2f}% is below min_confidence {min_confidence}%."
        )
        return

    if dry_run:
        logging.info(
            f"[dry_run] Would scale container {container_id}: "
            f"CPU - {cpu_action} (-> {new_cores}), RAM - {ram_action} (-> {new_ram}) "
            f"| Confidence: {confidence:.2f}%"
        )
        return

    logging.info(
        f"Applying scaling actions for container {container_id}: "
        f"CPU - {cpu_action}, RAM - {ram_action} | Confidence: {confidence:.2f}%"
    )
    apply_scaling(container_id, new_cores, new_ram, config)


def main():
    config = load_config(CONFIG_PATH)
    setup_logging(
        config.get("log_file", "/var/log/lxc_autoscale_ml.log"),
        # log_level was in the shipped config but never passed through.
        config.get("log_level", "INFO"),
    )

    logging.info("Starting the LXC auto-scaling script...")

    lock_file = config.get("lock_file", "/run/lxc_autoscale_ml.lock")
    create_lock_file(lock_file)

    # Ensure the lock is released on SIGINT/SIGTERM too, not only on a clean
    # exit from the loop below.
    setup_signal_handlers(cleanup_function=lambda: remove_lock_file(lock_file))

    circuit_breaker = build_circuit_breaker(config)
    interval = config.get("interval_seconds", 60)

    try:
        while True:
            try:
                run_cycle(config, circuit_breaker)
            except Exception:
                # A failed cycle is not a reason to stop the service. Exiting
                # here returned 0, so systemd's Restart=on-failure never fired
                # and autoscaling silently stopped until someone noticed.
                logging.exception("Scaling cycle failed; retrying at the next interval.")

            logging.info(f"Sleeping for {interval} seconds before the next run.")
            time.sleep(interval)
    finally:
        remove_lock_file(lock_file)
        logging.info("Script execution completed.")


if __name__ == "__main__":
    main()
