import requests
import logging
import time
import sys
import pandas as pd

# Ensure all modules in the lxc_autoscale_ml directory are accessible
sys.path.append('/usr/local/bin/lxc_autoscale_ml')

# Import custom modules
from logger import setup_logging
from lock_manager import create_lock_file, remove_lock_file
from config_manager import load_config
from model import train_anomaly_models, predict_anomalies
from signal_handler import setup_signal_handlers

def determine_scaling_action(latest_metrics, scaling_decision, confidence, config):
    """
    Determine CPU and RAM scaling actions based on usage metrics and thresholds.
    
    This function evaluates container resource usage against configured thresholds
    and determines whether to scale up, scale down, or maintain current resources.
    Scaling is performed incrementally using configured step sizes.
    
    Args:
        latest_metrics (pd.Series): Container metrics including:
            - cpu_usage_percent: Current CPU usage as percentage
            - memory_usage_mb: Current RAM usage in MB
            - current_cores: Current CPU core allocation
            - current_ram_mb: Current RAM allocation in MB
        scaling_decision (int): IsolationForest prediction (-1=anomaly, 1=normal)
        confidence (float): Prediction confidence percentage (0-100)
        config (dict): Configuration containing 'scaling' section with thresholds
    
    Returns:
        tuple: (cpu_action, ram_action, new_cores, new_ram)
            - cpu_action (str): "Scale Up", "Scale Down", or "No Scaling"
            - ram_action (str): "Scale Up", "Scale Down", or "No Scaling"
            - new_cores (int): Target CPU cores after scaling (or None)
            - new_ram (int): Target RAM in MB after scaling (or None)
    """
    cpu_action = "No Scaling"
    ram_action = "No Scaling"
    new_cores = None
    new_ram = None
    
    cpu_usage = latest_metrics["cpu_usage_percent"]
    memory_usage_mb = latest_metrics["memory_usage_mb"]
    current_ram_mb = latest_metrics.get("current_ram_mb", config["scaling"].get("min_ram_mb", 1024))

    # Calculate RAM usage as percentage for threshold comparison
    memory_usage_percent = (memory_usage_mb / current_ram_mb) * 100 if current_ram_mb > 0 else 0

    logging.debug(f"CPU usage: {cpu_usage}% | Memory usage: {memory_usage_mb}MB ({memory_usage_percent:.1f}%) | Confidence: {confidence}%")

    thresholds = config["scaling"]

    # IsolationForest returns -1 for anomalies (outliers), 1 for normal points
    # Anomalies (-1) indicate unusual resource patterns that may need scaling
    if scaling_decision == -1:
        logging.debug("Anomaly detected. Evaluating for potential scaling based on thresholds.")
    
    # Check threshold-based scaling
    if cpu_usage > thresholds["cpu_scale_up_threshold"]:
        cpu_action = "Scale Up"
        logging.debug(f"CPU usage {cpu_usage}% exceeds the scale-up threshold.")
    elif cpu_usage < thresholds["cpu_scale_down_threshold"]:
        cpu_action = "Scale Down"
        logging.debug(f"CPU usage {cpu_usage}% is below the scale-down threshold.")
    
    if memory_usage_percent > thresholds["ram_scale_up_threshold"]:
        ram_action = "Scale Up"
        logging.debug(f"Memory usage {memory_usage_percent:.1f}% exceeds the scale-up threshold.")
    elif memory_usage_percent < thresholds["ram_scale_down_threshold"]:
        ram_action = "Scale Down"
        logging.debug(f"Memory usage {memory_usage_percent:.1f}% is below the scale-down threshold.")

    # Get current resources from the container
    current_cores = latest_metrics.get("current_cores", thresholds.get("min_cpu_cores", 2))
    current_ram = latest_metrics.get("current_ram_mb", thresholds.get("min_ram_mb", 1024))
    
    # Calculate incremental scaling steps
    cpu_step = thresholds.get("cpu_scale_step", 1)  # Scale by 1 core at a time by default
    ram_step = thresholds.get("ram_scale_step_mb", 512)  # Scale by 512MB at a time by default
    
    # Ensure scaling stays within limits with incremental changes
    if cpu_action == "Scale Up":
        new_cores = min(current_cores + cpu_step, thresholds["max_cpu_cores"])
    elif cpu_action == "Scale Down":
        new_cores = max(current_cores - cpu_step, thresholds["min_cpu_cores"])
    
    if ram_action == "Scale Up":
        new_ram = min(current_ram + ram_step, thresholds["max_ram_mb"])
    elif ram_action == "Scale Down":
        new_ram = max(current_ram - ram_step, thresholds["min_ram_mb"])

    logging.debug(f"Final scaling actions: CPU -> {cpu_action}, RAM -> {ram_action} | Confidence: {confidence}%")
    return cpu_action, ram_action, new_cores, new_ram




def apply_scaling(lxc_id, new_cores, new_ram, config):
    """
    Apply CPU and/or RAM scaling changes to a container via the API.
    
    Makes POST requests to the scaling API endpoints with retry logic.
    Both CPU and RAM scaling are attempted independently.
    
    Args:
        lxc_id (str): Container ID to scale
        new_cores (int): Target CPU cores (None to skip CPU scaling)
        new_ram (int): Target RAM in MB (None to skip RAM scaling)
        config (dict): Configuration containing API settings and retry logic
    
    Returns:
        None
    """
    max_retries = config.get("retry_logic", {}).get("max_retries", 3)
    retry_delay = config.get("retry_logic", {}).get("retry_delay", 2)
    base_url = config["api"]["api_url"]
    cores_endpoint = config["api"].get("cores_endpoint", "/scale/cores")
    ram_endpoint = config["api"].get("ram_endpoint", "/scale/ram")

    def perform_request(url, data, resource_type):
        resource_key = "cores" if resource_type == "CPU" else "memory"
        for attempt in range(max_retries):
            try:
                response = requests.post(url, json=data)
                response.raise_for_status()
                logging.info(f"Successfully scaled {resource_type} for LXC ID {lxc_id} to {data[resource_key]} {resource_type} units.")
                return True
            except requests.RequestException as e:
                if response.status_code == 500:
                    logging.error(f"Server error (500) encountered on attempt {attempt + 1} to scale {resource_type} for LXC ID {lxc_id}. Aborting further attempts.")
                    break  # Skip further retries for 500 errors
                logging.error(f"Attempt {attempt + 1} failed to scale {resource_type} for LXC ID {lxc_id}: {e}")
                if attempt < max_retries - 1:
                    logging.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logging.error(f"Scaling {resource_type} for LXC ID {lxc_id} failed after {max_retries} attempts.")
                    return False
        return False

    if new_cores is not None:
        cpu_data = {"lxc_id": lxc_id, "cores": new_cores}
        cpu_url = f"{base_url}{cores_endpoint}"
        if not perform_request(cpu_url, cpu_data, "CPU"):
            logging.error(f"Scaling operation aborted for LXC ID {lxc_id} due to CPU scaling failure.")

    if new_ram is not None:
        ram_data = {"lxc_id": lxc_id, "memory": new_ram}
        ram_url = f"{base_url}{ram_endpoint}"
        if not perform_request(ram_url, ram_data, "RAM"):
            logging.error(f"Scaling operation aborted for LXC ID {lxc_id} due to RAM scaling failure.")
