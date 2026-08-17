# Model Component

The Model component is the ML engine that analyzes container metrics and makes scaling decisions.

## Overview

| Property | Value |
|----------|-------|
| Service | `lxc_autoscale_ml` |
| Configuration | `/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml` |
| Log File | `/var/log/lxc_autoscale_ml.log` |
| Lock File | `/var/lock/lxc_autoscale_ml.lock` |

## Features

- **IsolationForest ML Model**: Anomaly detection for resource usage
- **Incremental Scaling**: Gradual resource adjustment
- **Batch Async API Client**: 10x faster configuration fetching
- **Circuit Breaker**: Fault tolerance for API failures
- **Stale Lock Cleanup**: Automatic recovery from crashes

## Processing Loop

```
1. Load Configuration
   ↓
2. Verify Lock (prevent multiple instances)
   ↓
3. Load Historical Metrics
   ↓
4. Preprocess & Feature Engineering
   ↓
5. Train IsolationForest Model
   ↓
6. Batch Fetch Container Configs (async)
   ↓
7. For Each Container:
   - Predict anomaly
   - Determine scaling action
   - Apply scaling via API
   ↓
8. Sleep & Repeat
```

## IsolationForest Model

### Algorithm

IsolationForest is an unsupervised machine learning algorithm for anomaly detection. It works by randomly selecting a feature and randomly selecting a split value. Anomalies are easier to isolate and require fewer splits.

### Prediction Values

| Value | Meaning |
|-------|---------|
| -1 | Anomaly (unusual resource usage) |
| 1 | Normal behavior |

### Features Used (26 total)

| Category | Features |
|----------|----------|
| CPU | `cpu_usage_percent`, `rolling_mean_cpu`, `rolling_std_cpu`, `cpu_trend`, `max_cpu`, `min_cpu`, `cpu_per_process` |
| Memory | `memory_usage_mb`, `rolling_mean_memory`, `rolling_std_memory`, `memory_trend`, `max_memory`, `min_memory`, `memory_per_process`, `swap_usage_mb`, `swap_total_mb` |
| Combined | `cpu_memory_ratio` |
| Disk | `filesystem_usage_gb`, `filesystem_free_gb`, `filesystem_total_gb` |
| Network | `network_rx_bytes`, `network_tx_bytes` |
| I/O | `io_reads`, `io_writes` |
| System | `process_count`, `time_diff` |

### Configuration

```yaml
isolation_forest:
  contamination: 0.1      # Expected anomaly percentage (10%)
  n_estimators: 100       # Number of trees
  random_state: 42        # Reproducibility
  max_samples: auto       # Auto-tune sample size
```

## Scaling Logic

### Incremental Scaling

Resources scale gradually to avoid instability.

**CPU Scaling:**

```
Scale UP if:
  - IsolationForest detects anomaly (-1)
  - CPU usage > cpu_scale_up_threshold (default 70%)
  - Current cores < max_cpu_cores

Scale DOWN if:
  - IsolationForest reports normal (1)
  - CPU usage < cpu_scale_down_threshold (default 30%)
  - Current cores > min_cpu_cores

Step size: cpu_scale_step (default 1 core)
```

**RAM Scaling:**

```
Scale UP if:
  - IsolationForest detects anomaly (-1)
  - RAM usage % > ram_scale_up_threshold (default 80%)
  - Current RAM < max_ram_mb

Scale DOWN if:
  - IsolationForest reports normal (1)
  - RAM usage % < ram_scale_down_threshold (default 40%)
  - Current RAM > min_ram_mb

Step size: ram_scale_step_mb (default 512 MB)
```

### Configuration

```yaml
scaling:
  # CPU Thresholds
  cpu_scale_up_threshold: 70
  cpu_scale_down_threshold: 30
  cpu_scale_step: 1

  # RAM Thresholds
  ram_scale_up_threshold: 80
  ram_scale_down_threshold: 40
  ram_scale_step_mb: 512

  # Limits
  min_cpu_cores: 1
  max_cpu_cores: 8
  min_ram_mb: 512
  max_ram_mb: 16384

  # Confidence
  min_confidence: 70  # 0 (the default) disables confidence gating
```

## Async Batch API Client

### Performance Improvement

| Containers | Sequential | Async Batch | Speedup |
|------------|-----------|-------------|---------|
| 10 | 1.0s | 0.15s | 6.7x |
| 20 | 2.0s | 0.25s | 8.0x |
| 50 | 5.0s | 0.50s | 10x |
| 100 | 10.0s | 1.0s | 10x |

### Features

- Concurrent requests (up to 10 simultaneous)
- Connection pooling
- Exponential backoff retry (1s, 2s, 4s)
- 5-second timeout per request
- Graceful degradation on failures

### Configuration

```yaml
api:
  api_url: "http://127.0.0.1:5000"
  timeout: 5
  max_concurrent: 10
  retry_attempts: 3
```

## Circuit Breaker

Prevents cascading failures when API endpoints fail repeatedly.

### States

```
CLOSED ──failures──▶ OPEN ──timeout──▶ HALF-OPEN
   ▲                                       │
   └───────────success────────────────────┘
```

| State | Behavior |
|-------|----------|
| CLOSED | Normal operation, requests pass through |
| OPEN | All requests fail fast, no API calls |
| HALF-OPEN | After timeout, test one request |

### Configuration

```yaml
circuit_breaker:
  enabled: true
  failure_threshold: 5   # Open after 5 failures
  timeout_seconds: 300   # Reset after 5 minutes
```

## Lock Management

The service uses a lock file to prevent multiple instances from running simultaneously.

### Stale Lock Cleanup

Version 2.0 automatically cleans up stale locks:

1. Check if lock file exists
2. Read PID from lock file
3. Verify process is running with `os.kill(pid, 0)`
4. If process not running, remove stale lock
5. Create new lock with current PID

## Configuration Reference

```yaml
# /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml

# API Configuration
api:
  api_url: "http://127.0.0.1:5000"
  timeout: 5
  max_concurrent: 10
  retry_attempts: 3

# Data Configuration
data:
  metrics_file: "/var/log/lxc_metrics.json"

# Logging Configuration
logging:
  log_level: "INFO"
  log_file: "/var/log/lxc_autoscale_ml.log"

# ML Model Configuration
isolation_forest:
  contamination: 0.1
  n_estimators: 100
  random_state: 42

# Scaling Configuration
scaling:
  cpu_scale_up_threshold: 70
  cpu_scale_down_threshold: 30
  cpu_scale_step: 1
  ram_scale_up_threshold: 80
  ram_scale_down_threshold: 40
  ram_scale_step_mb: 512
  min_cpu_cores: 1
  max_cpu_cores: 8
  min_ram_mb: 512
  max_ram_mb: 16384
  min_confidence: 70  # 0 (the default) disables confidence gating

# Ignored Containers
ignore_lxc: []

# Circuit Breaker
circuit_breaker:
  enabled: true
  failure_threshold: 5
  timeout_seconds: 300

# Sleep Configuration
sleep_interval: 60
```

## Log Examples

**Successful scaling:**

```
INFO - Batch fetching configs for 60 containers...
INFO - Batch fetch completed in 0.58s: 60/60 successful (103.4 containers/sec)
INFO - Processing container 104...
INFO - IsolationForest prediction for 104: -1 (anomaly)
INFO - Scaling decision for 104: CPU=Scale Up, RAM=Scale Up (confidence: 87.4%)
INFO - Successfully scaled CPU for LXC ID 104 to 4 cores
INFO - Successfully scaled RAM for LXC ID 104 to 8192 MB
```

**Circuit breaker activation:**

```
WARNING - API call failed for container 105 (attempt 3/3)
WARNING - Circuit breaker opened for api_105 (5 consecutive failures)
INFO - Skipping container 105 - circuit breaker open
```

## Troubleshooting

### No Data to Train Model

```bash
# Check if monitor is running
systemctl status lxc_monitor

# Check metrics file
cat /var/log/lxc_metrics.json | jq '.[-5:]'
```

### Circuit Breaker Open for All Containers

```bash
# Check API service
systemctl status lxc_autoscale_api

# Test API
curl http://127.0.0.1:5000/health/check
```

### Lock File Exists Error

```bash
# Check if process is running
cat /var/lock/lxc_autoscale_ml.lock
ps -p $(cat /var/lock/lxc_autoscale_ml.lock)

# If not running, restart service (auto-cleans stale lock)
systemctl restart lxc_autoscale_ml
```

## Next Steps

- [Monitor Component](/components/monitor): Metrics collection
- [Configuration Reference](/reference/configuration): All settings
- [Troubleshooting](/guide/troubleshooting): Common issues
