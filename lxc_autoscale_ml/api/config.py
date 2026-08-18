import logging
import os
from logging.handlers import RotatingFileHandler

import yaml
from flask import Flask

DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

def load_config(config_file=None):
    """Load the API configuration.

    `or {}` throughout, because a section written but left empty parses to
    None, and `.get(key, default)` returns that stored None rather than the
    default -- which surfaced as a raw HTML 500 on every request. The gunicorn
    config, the monitor and the model config loader all already guarded this;
    only this file did not.
    """
    config_file = config_file or os.environ.get(
        "LXC_AUTOSCALE_API_CONFIG", "/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml")
    with open(config_file) as file:
        return yaml.safe_load(file) or {}

def configure_logging(logging_config):
    """
    Apply the `logging` section of the config file.

    Without a `log_file` the API logs to stdout only, which systemd captures in
    the journal. With one, the file is rotated according to `max_log_size_mb`
    and `backup_count` -- nothing else in the project rotates it.
    """
    level = getattr(logging, str(logging_config.get('level', 'INFO')).upper(), logging.INFO)
    log_format = logging_config.get('log_format', DEFAULT_LOG_FORMAT)

    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(log_format)

    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    log_file = logging_config.get('log_file')
    if log_file:
        if logging_config.get('rotate', True):
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=int(logging_config.get('max_log_size_mb', 100)) * 1024 * 1024,
                backupCount=int(logging_config.get('backup_count', 5)),
            )
        else:
            file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

def create_app(config=None):
    app = Flask(__name__)

    if config is None:
        config = load_config()

    configure_logging(config.get('logging') or {})

    lxc_config = (config.get('lxc') or {})
    app.config['LXC_NODE'] = lxc_config.get('node')
    app.config['DEFAULT_STORAGE'] = lxc_config.get('default_storage')
    app.config['TIMEOUT'] = lxc_config.get('timeout_seconds', 30)

    # Load the rate limiting configuration
    app.config['RATE_LIMITING'] = (config.get('rate_limiting') or {})

    # Load authentication configuration
    app.config['AUTHENTICATION'] = (config.get('authentication') or {'enabled': False})

    # Listen address. Defaults match the historical hard-coded values.
    app.config['SERVER'] = (config.get('server') or {})

    # Flask settings
    app.secret_key = os.urandom(24)
    app.config['DEBUG'] = False
    app.config['LOGGING'] = (config.get('logging') or {})
    app.config['ERROR_HANDLING'] = (config.get('error_handling') or {})

    return app
