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

            # Iterate over each container and make scaling decisions
            for container_id in df["container_id"].unique():
                container_data = df[df["container_id"] == container_id]
                latest_metrics = container_data.iloc[-1].copy()

                # Fetch current CPU and RAM configuration from API with retry logic
                latest_metrics["current_cores"] = config["scaling"]["min_cpu_cores"]
                latest_metrics["current_ram_mb"] = config["scaling"]["min_ram_mb"]
                
                # Check circuit breaker before attempting API call
                api_key = f"api_{container_id}"
                if api_circuit_breaker.is_open(api_key):
                    logging.warning(f"Circuit breaker open for container {container_id}, using defaults")
                else:
                    try:
                        import requests
                        api_url = config["api"]["api_url"]
                        max_retries = 3
                        retry_delay = 1
                        
                        for attempt in range(max_retries):
                            try:
                                response = requests.get(
                                    f"{api_url}/resource/vm/config?vm_id={container_id}", 
                                    timeout=5
                                )
                                if response.status_code == 200:
                                    vm_config = response.json().get("data", {})
                                    latest_metrics["current_cores"] = vm_config.get("cores", config["scaling"]["min_cpu_cores"])
                                    latest_metrics["current_ram_mb"] = vm_config.get("memory_mb", config["scaling"]["min_ram_mb"])
                                    logging.debug(f"Container {container_id} current config: {vm_config.get('cores')} cores, {vm_config.get('memory_mb')} MB RAM")
                                    api_circuit_breaker.record_success(api_key)
                                    break
                                elif response.status_code >= 500 and attempt < max_retries - 1:
                                    logging.warning(f"API server error (attempt {attempt + 1}/{max_retries}), retrying...")
                                    time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                                else:
                                    logging.warning(f"Could not fetch config for container {container_id} (status {response.status_code}), using defaults")
                                    if response.status_code >= 500:
                                        api_circuit_breaker.record_failure(api_key)
                                    break
                            except requests.RequestException as e:
                                if attempt < max_retries - 1:
                                    logging.warning(f"API request failed (attempt {attempt + 1}/{max_retries}): {e}, retrying...")
                                    time.sleep(retry_delay * (2 ** attempt))
                                else:
                                    logging.warning(f"API request failed after {max_retries} attempts: {e}, using defaults")
                                    api_circuit_breaker.record_failure(api_key)
                    except Exception as e:
                        logging.warning(f"Error fetching config for container {container_id}: {e}, using defaults")
                        api_circuit_breaker.record_failure(api_key)

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
