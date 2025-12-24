#!/usr/bin/env python3

import sys
import time
import logging
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
from scaling import determine_scaling_action, apply_scaling
from signal_handler import setup_signal_handlers
from async_api_client import fetch_container_configs_sync

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

# Global circuit breaker instance
api_circuit_breaker = CircuitBreaker(failure_threshold=3, timeout=300)


def main():
    config = load_config("/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml")
    setup_logging(config.get("log_file", "/var/log/lxc_autoscale_ml.log"))

    logging.info("Starting the LXC auto-scaling script...")

    create_lock_file(config.get("lock_file", "/tmp/lxc_autoscale_ml.lock"))

    try:
        while True:
            # Load and preprocess data
            df = load_data(config.get("data_file", "/var/log/lxc_metrics.json"))
            if df is None:
                logging.error("Exiting due to data loading error.")
                return

            df = preprocess_data(df, config)

            # Train anomaly detection models
            model, features_to_use = train_anomaly_models(df, config)
            if model is None:
                logging.error("Model training failed. Exiting.")
                return

            logging.info("Processing containers for scaling decisions...")

            # Get all unique container IDs
            container_ids = [str(cid) for cid in df["container_id"].unique()]
            
            # Batch fetch all container configs in parallel (10x faster than sequential!)
            logging.info(f"Batch fetching configs for {len(container_ids)} containers...")
            batch_start = time.time()
            
            all_configs = fetch_container_configs_sync(
                container_ids,
                config["api"]["api_url"],
                circuit_breaker=api_circuit_breaker,
                timeout=5,
                max_concurrent=10
            )
            
            batch_duration = time.time() - batch_start
            successful_fetches = sum(1 for c in all_configs.values() if c is not None)
            logging.info(
                f"Batch fetch completed in {batch_duration:.2f}s: "
                f"{successful_fetches}/{len(container_ids)} successful "
                f"({successful_fetches/batch_duration:.1f} containers/sec)"
            )

            # Iterate over each container and make scaling decisions
            for container_id in container_ids:
                container_data = df[df["container_id"] == int(container_id)]
                latest_metrics = container_data.iloc[-1].copy()

                # Use batch-fetched config or defaults
                config_data = all_configs.get(container_id)
                if config_data:
                    latest_metrics["current_cores"] = config_data.get("cores", config["scaling"]["min_cpu_cores"])
                    latest_metrics["current_ram_mb"] = config_data.get("memory_mb", config["scaling"]["min_ram_mb"])
                    logging.debug(f"Container {container_id} current config: {config_data.get('cores')} cores, {config_data.get('memory_mb')} MB RAM")
                else:
                    latest_metrics["current_cores"] = config["scaling"]["min_cpu_cores"]
                    latest_metrics["current_ram_mb"] = config["scaling"]["min_ram_mb"]
                    logging.warning(f"Using defaults for container {container_id} (config fetch failed)")

                logging.debug(f"Latest metrics for container {container_id}: {latest_metrics.to_dict()}")

                scaling_decision, confidence = predict_anomalies(model, latest_metrics, features_to_use, config)

                if scaling_decision is not None:
                    cpu_action, ram_action, new_cores, new_ram = determine_scaling_action(latest_metrics, scaling_decision, confidence, config)
                    logging.debug(f"Scaling decision for container {container_id}: CPU - {cpu_action}, RAM - {ram_action} | Confidence: {confidence:.2f}%")

                    if cpu_action != "No Scaling" or ram_action != "No Scaling":
                        logging.info(f"Applying scaling actions for container {container_id}: CPU - {cpu_action}, RAM - {ram_action} | Confidence: {confidence:.2f}%")
                        apply_scaling(container_id, new_cores, new_ram, config)
                    else:
                        logging.info(f"No scaling needed for container {container_id}. | Confidence: {confidence:.2f}%")
                else:
                    logging.warning(f"Skipping scaling for container {container_id} due to lack of prediction.")

            # Sleep until the next interval
            logging.info(f"Sleeping for {config.get('interval_seconds', 60)} seconds before the next run.")
            time.sleep(config.get("interval_seconds", 60))

    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        remove_lock_file(config.get("lock_file", "/tmp/lxc_autoscale_ml.lock"))
        logging.info("Script execution completed.")

if __name__ == "__main__":
    # Setup signal handlers to ensure graceful shutdown
    setup_signal_handlers()
    main()
