"""Gunicorn configuration for the AutoScale API.

The systemd unit used to run Flask's development server, which is
single-threaded, has no request queueing and prints a warning on every start
that it must not be used in production. The `gunicorn` section of
lxc_autoscale_api.yaml described a production setup that nothing read.

Settings come from that same YAML file so there is one place to configure the
service.

On worker count
---------------
The default is one worker with several threads, not several worker processes.
Two pieces of state in this API live in process memory:

* the rate limiter's per-IP sliding window (rate_limiting.py), and
* the Prometheus counters (metrics.py).

With N worker processes each holds its own copy, so the effective rate limit
becomes N times the configured one and /metrics reports whatever the worker
that happened to serve the request has seen. The work here is waiting on `pct`,
which releases the GIL, so threads give the concurrency without splitting that
state. Raising `workers` above 1 is supported but logs a warning at startup.
"""
import multiprocessing
import os

import yaml

CONFIG_PATH = os.environ.get(
    "LXC_AUTOSCALE_API_CONFIG", "/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml"
)

try:
    with open(CONFIG_PATH) as config_file:
        _config = yaml.safe_load(config_file) or {}
except OSError:
    _config = {}

_server = _config.get("server", {})
_gunicorn = _config.get("gunicorn", {})

bind = "{}:{}".format(
    _server.get("host", "0.0.0.0"),  # noqa: S104 - configurable; see server.host in the YAML
    _server.get("port", 5000),
)

# The API modules are deployed flat and import each other by bare name, so the
# directory holding them has to be importable. Deriving it from this file means
# the service does not silently depend on the unit's WorkingDirectory.
chdir = os.path.dirname(os.path.abspath(__file__))
pythonpath = chdir

wsgi_app = "lxc_autoscale_api:app"

workers = _gunicorn.get("workers", 1)
threads = _gunicorn.get("threads", min(8, (multiprocessing.cpu_count() or 1) * 2))

timeout = _gunicorn.get("timeout_seconds", 120)
graceful_timeout = _gunicorn.get("graceful_timeout_seconds", 30)
preload_app = _gunicorn.get("preload_app", True)

# Recycle workers periodically as a backstop against slow leaks.
max_requests = _gunicorn.get("max_requests", 500)
max_requests_jitter = _gunicorn.get("max_requests_jitter", 50)

loglevel = _gunicorn.get("log_level", "info")
accesslog = _gunicorn.get("access_log_file", "-")
errorlog = _gunicorn.get("error_log_file", "-")


def on_starting(server):
    if workers > 1:
        server.log.warning(
            "gunicorn.workers is %s. Rate limiting and Prometheus metrics are "
            "per-process, so the effective rate limit is %s times the "
            "configured value and /metrics only reports the worker that served "
            "the request. Prefer workers: 1 with more threads.",
            workers, workers,
        )
