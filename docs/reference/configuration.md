# Configuration Reference

This page documents all configuration options for LXC AutoScale ML.

## Configuration Files

| Component | Path |
|-----------|------|
| API | `/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml` |
| Model | `/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml` |
| Monitor | `/etc/lxc_autoscale_ml/lxc_monitor.yaml` |

## API Configuration

### Complete Reference

```yaml
# /etc/lxc_autoscale_ml/lxc_autoscale_api.yaml

# Server Configuration
server:
  host: "0.0.0.0"          # Bind address
  port: 5000               # Listen port

# Authentication
authentication:
  enabled: true            # Enable API key authentication
  api_key: "your-key"      # API key (change this!)

# Rate Limiting
rate_limiting:
  enabled: true            # Enable rate limiting
  max_requests_per_minute: 120  # Max requests per IP
  time_window_seconds: 60  # Sliding window duration

# Logging
logging:
  log_level: "INFO"        # DEBUG, INFO, WARNING, ERROR
  log_file: "/var/log/autoscaleapi.log"
  access_log: "/var/log/autoscaleapi_access.log"
  error_log: "/var/log/autoscaleapi_error.log"
```

### API Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `server.host` | string | `0.0.0.0` | Network interface to bind |
| `server.port` | integer | `5000` | TCP port number |
| `authentication.enabled` | boolean | `true` | Require API key |
| `authentication.api_key` | string | - | Secret API key |
| `rate_limiting.enabled` | boolean | `true` | Enable rate limits |
| `rate_limiting.max_requests_per_minute` | integer | `120` | Request limit per IP |
| `rate_limiting.time_window_seconds` | integer | `60` | Window duration |
| `logging.log_level` | string | `INFO` | Minimum log level |

## Model Configuration

### Complete Reference

```yaml
# /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml

# API Configuration
api:
  api_url: "http://127.0.0.1:5000"  # API base URL
  timeout: 5               # Request timeout (seconds)
  max_concurrent: 10       # Max parallel requests
  retry_attempts: 3        # Retry failed requests

# Data Configuration
data:
  metrics_file: "/var/log/lxc_metrics.json"

# Logging Configuration
logging:
  log_level: "INFO"        # DEBUG, INFO, WARNING, ERROR
  log_file: "/var/log/lxc_autoscale_ml.log"

# IsolationForest Configuration
isolation_forest:
  contamination: 0.1       # Expected anomaly fraction
  n_estimators: 100        # Number of trees
  random_state: 42         # Random seed
  max_samples: "auto"      # Samples per tree

# Scaling Configuration
scaling:
  # CPU Thresholds (percentage)
  cpu_scale_up_threshold: 70
  cpu_scale_down_threshold: 30
  cpu_scale_step: 1        # Cores to add/remove

  # RAM Thresholds (percentage)
  ram_scale_up_threshold: 80
  ram_scale_down_threshold: 40
  ram_scale_step_mb: 512   # MB to add/remove

  # Resource Limits
  min_cpu_cores: 1
  max_cpu_cores: 8
  min_ram_mb: 512
  max_ram_mb: 16384

  # Confidence
  min_confidence: 70       # Minimum confidence to scale

  # Testing
  dry_run: false           # Log decisions without executing

# Ignored Containers
ignore_lxc: []             # List of container IDs to skip

# Circuit Breaker
circuit_breaker:
  enabled: true
  failure_threshold: 5     # Failures before opening
  timeout_seconds: 300     # Time before reset

# Sleep Configuration
sleep_interval: 60         # Seconds between cycles
```

### Model Options

#### API Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `api.api_url` | string | `http://127.0.0.1:5000` | API base URL |
| `api.timeout` | integer | `5` | Request timeout in seconds |
| `api.max_concurrent` | integer | `10` | Maximum parallel requests |
| `api.retry_attempts` | integer | `3` | Retry count for failures |

#### IsolationForest Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `isolation_forest.contamination` | float | `0.1` | Expected anomaly ratio (0.0-0.5) |
| `isolation_forest.n_estimators` | integer | `100` | Number of trees |
| `isolation_forest.random_state` | integer | `42` | Random seed |
| `isolation_forest.max_samples` | string/int | `auto` | Samples per tree |

#### Scaling Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `scaling.cpu_scale_up_threshold` | integer | `70` | CPU % to trigger scale up |
| `scaling.cpu_scale_down_threshold` | integer | `30` | CPU % to trigger scale down |
| `scaling.cpu_scale_step` | integer | `1` | CPU cores per scaling action |
| `scaling.ram_scale_up_threshold` | integer | `80` | RAM % to trigger scale up |
| `scaling.ram_scale_down_threshold` | integer | `40` | RAM % to trigger scale down |
| `scaling.ram_scale_step_mb` | integer | `512` | RAM MB per scaling action |
| `scaling.min_cpu_cores` | integer | `1` | Minimum CPU cores |
| `scaling.max_cpu_cores` | integer | `8` | Maximum CPU cores |
| `scaling.min_ram_mb` | integer | `512` | Minimum RAM (MB) |
| `scaling.max_ram_mb` | integer | `16384` | Maximum RAM (MB) |
| `scaling.min_confidence` | integer | `70` | Minimum scaling confidence |
| `scaling.dry_run` | boolean | `false` | Test mode (no actual scaling) |

#### Circuit Breaker Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `circuit_breaker.enabled` | boolean | `true` | Enable circuit breaker |
| `circuit_breaker.failure_threshold` | integer | `5` | Failures before opening |
| `circuit_breaker.timeout_seconds` | integer | `300` | Reset timeout |

#### Other Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `ignore_lxc` | list | `[]` | Container IDs to exclude |
| `sleep_interval` | integer | `60` | Seconds between cycles |

## Monitor Configuration

### Complete Reference

```yaml
# /etc/lxc_autoscale_ml/lxc_monitor.yaml

# Metrics Configuration
metrics:
  output_file: "/var/log/lxc_metrics.json"
  max_entries: 1000        # Max entries in file
  collection_interval: 10  # Seconds between collections

# Logging Configuration
logging:
  log_level: "INFO"        # DEBUG, INFO, WARNING, ERROR
  log_file: "/var/log/lxc_monitor.log"

# Container Filter
containers:
  ignore_stopped: true     # Skip stopped containers
  ignore_templates: true   # Skip template containers

# Performance
performance:
  batch_size: 10           # Containers per batch
  timeout: 5               # Timeout per container
```

### Monitor Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `metrics.output_file` | string | `/var/log/lxc_metrics.json` | Metrics output path |
| `metrics.max_entries` | integer | `1000` | Maximum entries to keep |
| `metrics.collection_interval` | integer | `10` | Collection interval (seconds) |
| `containers.ignore_stopped` | boolean | `true` | Skip stopped containers |
| `containers.ignore_templates` | boolean | `true` | Skip template containers |
| `performance.batch_size` | integer | `10` | Containers per batch |
| `performance.timeout` | integer | `5` | Timeout per container |

## Configuration Validation

The model validates configuration on startup. Common validation rules:

| Rule | Error Message |
|------|---------------|
| `min_cpu_cores > max_cpu_cores` | "min_cpu_cores cannot be greater than max_cpu_cores" |
| `min_ram_mb > max_ram_mb` | "min_ram_mb cannot be greater than max_ram_mb" |
| `cpu_scale_down_threshold >= cpu_scale_up_threshold` | "cpu_scale_down_threshold must be less than cpu_scale_up_threshold" |
| Threshold outside 0-100 | "threshold must be between 0 and 100" |

### Validate Configuration Syntax

```bash
python3 -c "import yaml; yaml.safe_load(open('/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml'))"
```

If there's no output, the YAML is valid.

## Example Configurations

### Conservative Scaling

Slower, more cautious scaling for production:

```yaml
scaling:
  cpu_scale_up_threshold: 85
  cpu_scale_down_threshold: 20
  ram_scale_up_threshold: 90
  ram_scale_down_threshold: 30
  min_confidence: 80

sleep_interval: 120
```

### Aggressive Scaling

Faster response for development environments:

```yaml
scaling:
  cpu_scale_up_threshold: 60
  cpu_scale_down_threshold: 40
  ram_scale_up_threshold: 70
  ram_scale_down_threshold: 50
  min_confidence: 60

sleep_interval: 30
```

### Large Deployment

Optimized for 60+ containers:

```yaml
api:
  max_concurrent: 15
  timeout: 10

circuit_breaker:
  failure_threshold: 3
  timeout_seconds: 600

sleep_interval: 120
```

## Applying Configuration Changes

After modifying configuration files, restart the relevant service:

```bash
# API changes
systemctl restart lxc_autoscale_api

# Model changes
systemctl restart lxc_autoscale_ml

# Monitor changes
systemctl restart lxc_monitor
```
