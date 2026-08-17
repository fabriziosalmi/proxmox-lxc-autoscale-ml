import os
import yaml
from flask import Flask

def load_config(config_file='/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml'):
    with open(config_file) as file:
        config = yaml.safe_load(file)
    return config

def create_app(config=None):
    app = Flask(__name__)

    if config is None:
        config = load_config()

    lxc_config = config.get('lxc', {})
    app.config['LXC_NODE'] = lxc_config.get('node')
    app.config['DEFAULT_STORAGE'] = lxc_config.get('default_storage')
    app.config['TIMEOUT'] = lxc_config.get('timeout_seconds', 30)

    # Load the rate limiting configuration
    app.config['RATE_LIMITING'] = config.get('rate_limiting', {})

    # Load authentication configuration
    app.config['AUTHENTICATION'] = config.get('authentication', {'enabled': False})

    # Listen address. Defaults match the historical hard-coded values.
    app.config['SERVER'] = config.get('server', {})

    # Flask settings
    app.secret_key = os.urandom(24)
    app.config['DEBUG'] = False
    app.config['LOGGING'] = config.get('logging', {})
    app.config['ERROR_HANDLING'] = config.get('error_handling', {})

    return app
