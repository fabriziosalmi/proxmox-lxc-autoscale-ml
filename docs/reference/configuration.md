# Configuration Reference

Every option below exists in the shipped configuration files and is read by the
code. The YAML blocks are the files as installed, so what you see here is what
lands in `/etc/lxc_autoscale_ml/`.

::: tip Keeping this honest
`tests/test_config_contract.py` fails if a configuration file grows a key no
code reads, or if this page documents a key no configuration file has. Eleven
such keys existed before v1.3.0 -- including `dry_run`, which meant anyone
rehearsing a change with it was scaling for real.
:::

## Configuration files

| Component | Path | Service |
|-----------|------|---------|
| API | `/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml` | `lxc_autoscale_api` |
| Model | `/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml` | `lxc_autoscale_ml` |
| Monitor | `/etc/lxc_autoscale_ml/lxc_monitor.yaml` | `lxc_monitor` |

On upgrade the installer never overwrites an existing file; the shipped defaults
are written alongside it as `<name>.yaml.new`.


## API configuration

Read by the API service, which executes `pct` commands as root.

```yaml
# /etc/lxc_autoscale_ml/lxc_autoscale_api.yaml
# HTTP listener
server:
  # Address the API binds to. 0.0.0.0 keeps the historical behaviour and exposes
  # the API on every interface. The API runs as root and executes pct commands,
  # so bind it to 127.0.0.1 unless the ML service runs on a different host --
  # and enable authentication below if it does.
  host: "0.0.0.0"

  # TCP port the API listens on.
  port: 5000

lxc:
  # Name of the Proxmox node this API manages. Informational only: every pct
  # call is local, so this cannot point the API at a different node. Running it
  # against another host would need pvesh, which this project does not use.
  node: "proxmox"
  
  # Default storage location for LXC containers.
  default_storage: "local-lvm"  # Default storage location
  
  # Timeout for operations in seconds.
  timeout_seconds: 10

rate_limiting:
  # Enable or disable rate limiting globally
  enabled: true
  
  # Maximum number of requests allowed per client IP
  # Note: localhost (127.0.0.1) is always exempt for internal ML service
  max_requests_per_minute: 120  # Increased from 60 to handle multiple containers
  
  # Time window for rate limiting in seconds (default 60)
  time_window_seconds: 60

# Authentication Configuration
authentication:
  # Enable API key authentication for all endpoints (except /health/check and /metrics)
  enabled: false  # Set to true in production
  
  # List of valid API keys - CHANGE THESE IN PRODUCTION!
  # Generate secure keys with: python3 -c "import os; print(os.urandom(32).hex())"
  api_keys: []
    # Example:
    # - "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6"

logging:
  # Logging level that controls the verbosity of logs. Options include "DEBUG", "INFO", "WARNING", "ERROR", and "CRITICAL".
  level: "INFO"
  
  # Whether to enable log rotation to manage log file size.
  rotate: true
  
  # Maximum size of the log file in megabytes before it is rotated.
  max_log_size_mb: 100
  
  # Number of backup log files to keep. Older files are deleted when new ones are created.
  backup_count: 5
  
  # Format for log messages. Uses Python's logging format string.
  log_format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"  # Log format

  # Optional log file. When unset the API logs to stdout only, which systemd
  # captures in the journal (journalctl -u lxc_autoscale_api). When set, the
  # file is rotated using max_log_size_mb and backup_count above.
  # log_file: "/var/log/lxc_autoscale_api.log"

  # HTTP access and error logs are gunicorn's; see the gunicorn section below.

error_handling:
  # Whether to display stack traces in error messages.
  show_stack_traces: false
  
  # Whether to log errors to the error log file.
  log_errors: true
  
  # Whether to send notifications for critical errors.
  notify_on_critical_errors: false
  
  # List of email addresses to notify in case of critical errors.
  notification_recipients:
    # Email address to receive notifications.
    - "your-email@inbox.com"

gunicorn:
  # Number of worker *processes*. Keep this at 1.
  # Rate limiting and Prometheus metrics are held in process memory, so N
  # workers means N independent rate limiters (N times the configured limit)
  # and /metrics reporting only the worker that answered. Use threads below
  # for concurrency instead: the work here is waiting on pct, not CPU.
  workers: 1

  # Number of threads per worker.
  threads: 8 
  
  # Timeout for worker processes in seconds. Defines how long a worker can handle a request before being killed.
  timeout_seconds: 120 
  
  # Log level for Gunicorn, which affects the verbosity of logs.
  log_level: "info" 
  
  # Path to the file where Gunicorn access logs are written ("-" for stdout,
  # which systemd captures in the journal).
  access_log_file: "/var/log/lxc_autoscale_api_access.log"  
  
  # Path to the file where Gunicorn error logs are written.
  error_log_file: "/var/log/lxc_autoscale_api_error.log"
  
  # Whether to preload the application before forking worker processes. Reduces startup time but uses more memory.
  preload_app: true 
  
  # Time to wait before forcefully killing workers during a graceful restart.
  graceful_timeout_seconds: 30  
  
  # Requests a worker handles before being recycled. 0 disables it, which is
  # the default and is deliberate: the rate-limiter window and the Prometheus
  # counters live in worker memory, so recycling silently resets both -- and a
  # client's own rejected requests drove the recycle that cleared its window.
  # The limiter evicts idle clients itself, so recycling is not needed to bound
  # memory.
  max_requests: 0

  # Random spread on max_requests. Irrelevant while max_requests is 0.
  max_requests_jitter: 0

  # Access log format. Deliberately omits the query string: the default format
  # logs the whole request line, and this log is not a place for anything a
  # caller passes as a parameter.
  access_log_format: '%(h)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(D)sus'
```

## Model configuration

Read by the scaling loop.

```yaml
# /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
# =============================================================
#                      LXC AutoScale ML
#           Automated Container Scaling Configuration
# -------------------------------------------------------------
# This configuration file controls the behavior of the LXC 
# AutoScale ML script. It includes settings for logging, 
# model training, spike detection, scaling actions, API 
# interactions, and more.
#
# The script is designed to automatically scale LXC containers 
# based on real-time metrics, such as CPU usage, memory usage, 
# and other system indicators. The scaling decisions are made 
# using machine learning models, which can detect anomalies 
# and trends in the data.
#
# Author: Fabrizio Salmi - fabrizio.salmi@gmail.com
# Date: August 20, 2024
# =============================================================

# Logging Configuration
log_file: "/var/log/lxc_autoscale_ml.log"  # Path to the log file
log_level: "DEBUG"  # Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

# Lock File Configuration
lock_file: "/run/lxc_autoscale_ml.lock"  # Path to the lock file to prevent multiple instances

# Data File Configuration
data_file: "/var/log/lxc_metrics.json"  # Path to the metrics file containing container data produced by LXC AutoScale API

# Model Configuration
model:
  contamination: 0.05  # Contamination level for IsolationForest (fraction of outliers)
  n_estimators: 100  # Number of trees in IsolationForest
  max_samples: 64  # Number of samples to draw for training each tree
  random_state: 42  # Random seed for reproducibility

# Spike Detection Configuration
spike_detection:
  spike_threshold: 2  # Number of standard deviations for spike detection
  rolling_window: 5  # Window size for rolling mean and standard deviation

# Scaling Configuration
scaling:
  max_cpu_cores: 4  # Maximum number of CPU cores to maintain per container
  max_ram_mb: 8192  # Maximum RAM to maintain per container in MB
  min_cpu_cores: 2  # Minimum number of CPU cores to maintain per container
  min_ram_mb: 1024  # Minimum RAM to maintain per container in MB
  cpu_scale_step: 1  # Number of CPU cores to add/remove per scaling action
  ram_scale_step_mb: 512  # Amount of RAM in MB to add/remove per scaling action
  cpu_scale_up_threshold: 75  # CPU usage percentage to trigger scale-up
  cpu_scale_down_threshold: 30  # CPU usage percentage to trigger scale-down
  ram_scale_up_threshold: 75  # RAM usage percentage to trigger scale-up
  ram_scale_down_threshold: 30  # RAM usage percentage to trigger scale-down
  # Minimum confidence (0-100) required before a scaling action is applied.
  # 0 disables the check. Confidence is the distance of the prediction from the
  # model's decision boundary.
  min_confidence: 0

  dry_run: false  # If true, log scaling decisions without calling the API

# API Configuration
api:
  api_url: "http://127.0.0.1:5000"  # Base URL for the API used for scaling actions
  cores_endpoint: "/scale/cores"  # Endpoint for scaling CPU cores
  ram_endpoint: "/scale/ram"  # Endpoint for scaling RAM
  timeout_seconds: 5  # Per-request timeout when talking to the API

  # API key, sent as X-API-Key. REQUIRED if the API has
  # authentication.enabled: true -- without it every request is rejected with
  # 401 and autoscaling stops. Must match one of the API's authentication.api_keys.
  # api_key: "your-secret-api-key-here"
  max_concurrent: 10  # Maximum parallel config fetches

# Retry Logic for API Calls
retry_logic:
  max_retries: 3  # Maximum number of retries for API calls
  retry_delay: 2  # Delay between retries in seconds

# Interval Configuration
interval_seconds: 600  # Time interval between consecutive script runs in seconds

# Circuit Breaker for API calls
circuit_breaker:
  enabled: true  # Stop calling the API for a container after repeated failures
  failure_threshold: 3  # Consecutive failures before the circuit opens
  # How long the circuit stays open before retrying. This MUST be longer than
  # interval_seconds: the breaker is consulted once per container per cycle, so
  # a window shorter than the interval has always expired by the time it is
  # asked and blocks nothing. At the shipped 600s interval, 300s blocked zero
  # calls in ten consecutive failing cycles.
  timeout_seconds: 1800

# Ignored Containers
# Container IDs to exclude from autoscaling. An empty list scales everything.
# IDs are matched as strings, so [101, 102] and ["101", "102"] both work.
# Example: ignore_lxc: ["100", "999"]
# Note: 101 and 102 are commonly the first containers on a host, so do not
# ignore them out of habit.
ignore_lxc: []
```

## Monitor configuration

Read by the metrics collector.

```yaml
# /etc/lxc_autoscale_ml/lxc_monitor.yaml
logging:
  # Path to the file where log messages are written.
  log_file: "/var/log/lxc_monitor.log"
  
  # Maximum size of the log file before it is rotated (in bytes). Set to 5 MB here.
  log_max_bytes: 5242880  # 5 MB
  
  # Number of backup log files to keep. Older files are deleted as new ones are created.
  log_backup_count: 7
  
  # Logging level to determine the verbosity of log messages. Options include "DEBUG", "INFO", "WARNING", "ERROR", and "CRITICAL".
  log_level: "INFO"

monitoring:
  # Path to the file where metrics data is exported in JSON format.
  export_file: "/var/log/lxc_metrics.json"
  
  # Interval (in seconds) at which the monitoring checks are performed.
  check_interval: 60  # seconds
  
  # Flag to enable or disable swap memory monitoring.
  enable_swap: true
  
  # Flag to enable or disable network statistics monitoring.
  enable_network: true
  
  # Flag to enable or disable filesystem statistics monitoring.
  enable_filesystem: true
  
  # Flag to enable or disable parallel processing of monitoring tasks.
  parallel_processing: true  # Toggle for parallel processing
  
  # Maximum number of parallel workers to use if parallel_processing is enabled.
  max_workers: 8  # Max number of parallel workers if parallel_processing is enabled
  
  # List of device types to exclude from I/O statistics collection.
  excluded_devices: ['loop', 'dm-']  # Devices to exclude in I/O stats
  
  # Maximum number of retry attempts for transient failures.
  retry_limit: 3
  
  # Delay between retry attempts in seconds.
  retry_delay: 2

  # Timeout in seconds for each pct invocation. Without a bound, one wedged
  # container froze the whole collection cycle indefinitely: the process
  # neither exited nor errored, so systemd never restarted it and the metrics
  # file was never updated again.
  command_timeout: 30
  
  # Maximum number of metrics entries to keep in the export file (prevents unbounded growth).
  max_metrics_entries: 1000  # Keeps last 1000 data points (~16 hours at 60s intervals)
```

## Option reference

### API

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `server.host` | string | `0.0.0.0` | Address to bind. See the warning below. |
| `server.port` | integer | `5000` | TCP port |
| `lxc.node` | string | `proxmox` | Proxmox node name or IP |
| `lxc.default_storage` | string | `local-lvm` | Storage used for clones |
| `lxc.timeout_seconds` | integer | `10` | Timeout for each `pct`/`pvesh` call |
| `rate_limiting.enabled` | boolean | `true` | Enable per-IP rate limiting |
| `rate_limiting.max_requests_per_minute` | integer | `120` | Requests allowed per IP per window |
| `rate_limiting.time_window_seconds` | integer | `60` | Sliding window length |
| `authentication.enabled` | boolean | `false` | Require an API key |
| `authentication.api_keys` | list | `[]` | Accepted keys |
| `logging.level` | string | `INFO` | Minimum log level |
| `logging.log_format` | string | see file | Python logging format string |
| `logging.rotate` | boolean | `true` | Rotate `log_file` by size |
| `logging.max_log_size_mb` | integer | `100` | Rotation threshold |
| `logging.backup_count` | integer | `5` | Rotated files kept |
| `error_handling.show_stack_traces` | boolean | `false` | Include exception detail in error responses |
| `error_handling.log_errors` | boolean | `true` | Log handled errors |
| `error_handling.notify_on_critical_errors` | boolean | `false` | Call the notification hook on 5xx |
| `gunicorn.workers` | integer | `1` | Worker processes. See the warning below. |
| `gunicorn.threads` | integer | `8` | Threads per worker |
| `gunicorn.timeout_seconds` | integer | `120` | Worker timeout |
| `gunicorn.graceful_timeout_seconds` | integer | `30` | Grace period on restart |
| `gunicorn.max_requests` | integer | `0` | Requests before a worker is recycled. 0 disables it, deliberately: recycling resets the rate-limiter window and the Prometheus counters, and a client's own rejected requests drove the recycle that cleared its window. |
| `gunicorn.max_requests_jitter` | integer | `0` | Random spread on the above. Irrelevant while recycling is off. |
| `gunicorn.preload_app` | boolean | `true` | Load the app before forking |
| `gunicorn.log_level` | string | `info` | Gunicorn's own log level |

`logging.log_file` is commented out in the shipped file. Leave it that way to
log to stdout only, which systemd captures in the journal.

::: warning The API runs as root
It executes `pct` commands, so it has to. With the default
`server.host: 0.0.0.0` it is reachable on every interface with no
authentication. On the standard single-node layout, where the model runs beside
it, set `server.host` to `127.0.0.1`. If it must be reachable from another host,
enable `authentication` and put TLS in front of it.
:::

::: warning Keep gunicorn.workers at 1
The rate limiter's per-IP window and the Prometheus counters live in process
memory. Two worker processes means two independent rate limiters -- an effective
limit of twice the configured value -- and `/metrics` reporting only whichever
worker answered the scrape. The work here is waiting on `pct`, which releases
the GIL, so `gunicorn.threads` gives you concurrency without splitting that
state. Gunicorn logs a warning at startup if `workers` is above 1.
:::

### Model

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `log_file` | string | `/var/log/lxc_autoscale_ml.log` | Rotated at 10 MB, 5 backups kept |
| `log_level` | string | `DEBUG` | Minimum log level |
| `lock_file` | string | `/run/lxc_autoscale_ml.lock` | Single-instance lock. Keep it out of world-writable `/tmp`. |
| `data_file` | string | `/var/log/lxc_metrics.json` | Metrics file written by the monitor |
| `interval_seconds` | integer | `600` | Seconds between scaling cycles |
| `api.api_url` | string | `http://127.0.0.1:5000` | Base URL of the API |
| `api.cores_endpoint` | string | `/scale/cores` | CPU scaling endpoint |
| `api.ram_endpoint` | string | `/scale/ram` | RAM scaling endpoint |
| `api.timeout_seconds` | integer | `5` | Per-request timeout (`timeout` also accepted) |
| `api.max_concurrent` | integer | `10` | Parallel configuration fetches |
| `retry_logic.max_retries` | integer | `3` | Attempts per scaling request |
| `retry_logic.retry_delay` | integer | `2` | Seconds between attempts |
| `model.contamination` | float | `0.05` | Expected outlier fraction for IsolationForest |
| `model.n_estimators` | integer | `100` | Trees in the forest |
| `model.max_samples` | integer | `64` | Samples drawn per tree |
| `model.random_state` | integer | `42` | Random seed |
| `spike_detection.spike_threshold` | integer | `2` | Standard deviations that count as a spike |
| `spike_detection.rolling_window` | integer | `5` | Window for rolling mean and standard deviation |
| `scaling.max_cpu_cores` | integer | `4` | Ceiling per container |
| `scaling.min_cpu_cores` | integer | `2` | Floor per container |
| `scaling.max_ram_mb` | integer | `8192` | Ceiling per container |
| `scaling.min_ram_mb` | integer | `1024` | Floor per container |
| `scaling.cpu_scale_step` | integer | `1` | Cores added or removed per action |
| `scaling.ram_scale_step_mb` | integer | `512` | MB added or removed per action |
| `scaling.cpu_scale_up_threshold` | integer | `75` | CPU % above which to scale up |
| `scaling.cpu_scale_down_threshold` | integer | `30` | CPU % below which to scale down |
| `scaling.ram_scale_up_threshold` | integer | `75` | RAM % above which to scale up |
| `scaling.ram_scale_down_threshold` | integer | `30` | RAM % below which to scale down |
| `scaling.min_confidence` | integer | `0` | Confidence (0-100) required before acting; 0 disables the check |
| `scaling.dry_run` | boolean | `false` | Log decisions without calling the API |
| `circuit_breaker.enabled` | boolean | `true` | Stop calling the API for a container after repeated failures |
| `circuit_breaker.failure_threshold` | integer | `3` | Consecutive failures before the circuit opens |
| `circuit_breaker.timeout_seconds` | integer | `1800` | How long it stays open. Must exceed `interval_seconds`: the breaker is consulted once per container per cycle, so a shorter window has always expired by then and blocks nothing. The model warns at startup if it does not. |
| `ignore_lxc` | list | `[]` | Container IDs to skip. Matched as strings, so `[101]` and `["101"]` both work. |

On confidence: it is the distance of the prediction from the model's decision
boundary, mapped onto 0-100. It is not a probability. Before v1.3.0 the formula
produced roughly 50-150%, so it could not be compared against a percentage at
all -- which is why `min_confidence` now defaults to 0 rather than the 70 this
page used to claim.

### Monitor

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `logging.log_file` | string | `/var/log/lxc_monitor.log` | Rotated by size |
| `logging.log_max_bytes` | integer | `5242880` | Rotation threshold (5 MB) |
| `logging.log_backup_count` | integer | `7` | Rotated files kept |
| `logging.log_level` | string | `INFO` | Minimum log level |
| `monitoring.export_file` | string | `/var/log/lxc_metrics.json` | Where metrics are written |
| `monitoring.check_interval` | integer | `60` | Seconds between collection cycles |
| `monitoring.enable_swap` | boolean | `true` | Collect swap usage |
| `monitoring.enable_network` | boolean | `true` | Collect network counters |
| `monitoring.enable_filesystem` | boolean | `true` | Collect filesystem usage |
| `monitoring.parallel_processing` | boolean | `true` | Collect from containers concurrently |
| `monitoring.max_workers` | integer | `8` | Thread pool size when parallel |
| `monitoring.excluded_devices` | list | `['loop', 'dm-']` | Device prefixes skipped in I/O stats |
| `monitoring.retry_limit` | integer | `3` | Attempts per probe before giving up |
| `monitoring.retry_delay` | integer | `2` | Seconds between attempts |
| `monitoring.max_metrics_entries` | integer | `1000` | Cycles kept in the export file |

`monitoring.export_file` and the model's `data_file` must point at the same
path. That file is the only thing connecting the two services.

## Validation

The model checks its scaling configuration at startup and refuses to run on a
contradictory one:

| Rule | Error |
|------|-------|
| `min_cpu_cores > max_cpu_cores` | `min_cpu_cores cannot be greater than max_cpu_cores` |
| `min_ram_mb > max_ram_mb` | `min_ram_mb cannot be greater than max_ram_mb` |
| A threshold is not a number | `<key> must be numeric, got <type>` |
| A threshold is outside 0-100 | `<key> must be between 0 and 100, got <value>` |
| `cpu_scale_down_threshold >= cpu_scale_up_threshold` | `cpu_scale_down_threshold must be less than cpu_scale_up_threshold` |
| `ram_scale_down_threshold >= ram_scale_up_threshold` | `ram_scale_down_threshold must be less than ram_scale_up_threshold` |
| A step size is zero or negative | `<key> must be positive` |

`log_file`, `interval_seconds`, `api` and `api.api_url` are required; the rest
falls back to the defaults above.

To check a file parses at all:

```bash
python3 -c "import yaml; yaml.safe_load(open('/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml'))"
```

No output means valid YAML.

## Worked examples

### Cautious scaling

Waits longer before acting, and only acts on confident predictions:

```yaml
scaling:
  cpu_scale_up_threshold: 85
  cpu_scale_down_threshold: 20
  ram_scale_up_threshold: 90
  ram_scale_down_threshold: 25
  min_confidence: 80

interval_seconds: 900
```

### Responsive scaling

For development hosts, where a wrong decision costs little:

```yaml
scaling:
  cpu_scale_up_threshold: 60
  cpu_scale_down_threshold: 40
  ram_scale_up_threshold: 70
  ram_scale_down_threshold: 45
  min_confidence: 0

interval_seconds: 120
```

### Rehearsing a change

`dry_run` logs the decision it would have taken and calls nothing:

```yaml
scaling:
  dry_run: true
```

```
[dry_run] Would scale container 104: CPU - Scale Up (-> 4), RAM - No Scaling | Confidence: 62.40%
```

### Many containers

```yaml
api:
  max_concurrent: 15
  timeout_seconds: 10

circuit_breaker:
  failure_threshold: 3
  timeout_seconds: 600

interval_seconds: 600
```

## Applying changes

Each service reads its file once, at startup:

```bash
systemctl restart lxc_autoscale_api   # API changes
systemctl restart lxc_autoscale_ml    # Model changes
systemctl restart lxc_monitor         # Monitor changes
```

The API also reloads on `SIGHUP` (`systemctl reload lxc_autoscale_api`), which
restarts its workers without dropping the listening socket.
