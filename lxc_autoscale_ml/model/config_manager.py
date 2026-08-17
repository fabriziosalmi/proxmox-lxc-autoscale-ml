import yaml
import logging
import os


class ConfigError(Exception):
    pass


def load_config(config_path, default_config=None):
    if not os.path.exists(config_path):
        logging.error(f"Configuration file not found: {config_path}")
        raise ConfigError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path) as file:
            config = yaml.safe_load(file)
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML file: {e}")
        raise ConfigError(f"Error parsing YAML file: {e}") from e
    except OSError as e:
        logging.error(f"Unable to read configuration file {config_path}: {e}")
        raise ConfigError(f"Unable to read configuration file {config_path}: {e}") from e

    # Checked outside the try block: raising here would otherwise be swallowed
    # by the broad handler above and reported as an "unexpected" error.
    if config is None:
        logging.error(f"Configuration file is empty: {config_path}")
        raise ConfigError(f"Configuration file is empty: {config_path}")

    logging.info(f"Configuration loaded from {config_path}")

    if default_config:
        config = {**default_config, **config}
        logging.debug("Configuration merged with default values.")

    required_keys = ['log_file', 'interval_seconds', 'api']
    for key in required_keys:
        if key not in config:
            logging.error(f"Missing required configuration key: {key}")
            raise ConfigError(f"Missing required configuration key: {key}")

    if 'api_url' not in config['api']:
        logging.error("Missing required configuration key: api_url")
        raise ConfigError("Missing required configuration key: api_url")

    # Validate scaling configuration
    validate_scaling_config(config)

    logging.debug(f"Final configuration: {config}")
    return config


def validate_scaling_config(config):
    """
    Validate scaling configuration for logical consistency and required fields.

    Args:
        config (dict): Configuration dictionary to validate

    Raises:
        ConfigError: If configuration is invalid
    """
    if 'scaling' not in config:
        return  # Scaling config is optional

    scaling = config['scaling']

    # Validate min/max ranges
    if scaling.get('min_cpu_cores', 0) > scaling.get('max_cpu_cores', float('inf')):
        raise ConfigError("min_cpu_cores cannot be greater than max_cpu_cores")

    if scaling.get('min_ram_mb', 0) > scaling.get('max_ram_mb', float('inf')):
        raise ConfigError("min_ram_mb cannot be greater than max_ram_mb")

    # Validate thresholds are percentages (0-100) and numeric
    threshold_keys = ['cpu_scale_up_threshold', 'cpu_scale_down_threshold',
                     'ram_scale_up_threshold', 'ram_scale_down_threshold']

    for key in threshold_keys:
        if key in scaling:
            value = scaling[key]
            if not isinstance(value, (int, float)):
                raise ConfigError(f"{key} must be numeric, got {type(value).__name__}")
            if not (0 <= value <= 100):
                raise ConfigError(f"{key} must be between 0 and 100, got {value}")

    # Validate scale-down threshold is less than scale-up threshold
    if (scaling.get('cpu_scale_down_threshold', 0) >=
        scaling.get('cpu_scale_up_threshold', 100)):
        raise ConfigError("cpu_scale_down_threshold must be less than cpu_scale_up_threshold")

    if (scaling.get('ram_scale_down_threshold', 0) >=
        scaling.get('ram_scale_up_threshold', 100)):
        raise ConfigError("ram_scale_down_threshold must be less than ram_scale_up_threshold")

    # Validate step sizes are positive
    if scaling.get('cpu_scale_step', 1) <= 0:
        raise ConfigError("cpu_scale_step must be positive")

    if scaling.get('ram_scale_step_mb', 1) <= 0:
        raise ConfigError("ram_scale_step_mb must be positive")

    logging.info("Scaling configuration validated successfully")
