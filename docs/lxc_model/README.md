# LXC AutoScale ML Model Documentation

**LXC AutoScale ML** is the intelligent core of the autoscaling system. It uses machine learning to analyze container metrics and make smart scaling decisions based on real-time usage patterns and historical data.

## ✨ What's New

### Recent Updates (December 2024)

- **🚀 Batch Async API Client**: Fetch all container configs concurrently (**10x faster** than sequential)
- **🛡️ Circuit Breaker Pattern**: Automatically skip failed API endpoints to prevent cascading failures
- **📈 Incremental Scaling**: Scale gradually (±1 core, ±512MB RAM) instead of jumping to extremes
- **🔧 Stale Lock Cleanup**: Automatic recovery from crashes with PID checking
- **🐛 Fixed IsolationForest Logic**: Correctly interpret anomaly predictions (-1 = anomaly, not truthy values)
- **📊 RAM Threshold Fix**: Compare usage as percentage, not absolute MB values
- **⚡ Performance Monitoring**: Log batch fetch speed (containers/sec) for optimization

## Summary

- **[Architecture](#architecture)**: High-level overview of the ML model components
- **[Machine Learning Model](#machine-learning-model)**: IsolationForest anomaly detection details
- **[Scaling Logic](#scaling-logic)**: How scaling decisions are made
- **[Async Batch API Client](#async-batch-api-client)**: High-performance concurrent API fetching
- **[Circuit Breaker](#circuit-breaker)**: Fault tolerance and graceful degradation
- **[Configuration](#configuration)**: All configuration options explained
- **[Logs](#logs)**: Where to find and how to interpret logs
- **[Troubleshooting](#troubleshooting)**: Common issues and solutions

---

## Architecture

The ML model service operates in a continuous loop:

```
1. Load Configuration
   ↓
2. Verify Lock (prevent multiple instances)
   ↓
3. Load Historical Metrics (from lxc_metrics.json)
   ↓
4. Preprocess & Feature Engineering
   ↓
5. Train IsolationForest Model
   ↓
6. Batch Fetch Container Configs (ASYNC - 10x faster!)
   ↓
7. For Each Container:
   - Predict Anomaly (IsolationForest)
   - Determine Scaling Action (CPU/RAM)
   - Apply Scaling (via API)
   ↓
8. Sleep & Repeat
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| **Main Loop** | `lxc_autoscale_ml.py` | Orchestrates entire ML pipeline |
| **Model Training** | `model.py` | IsolationForest training and predictions |
| **Scaling Logic** | `scaling.py` | Determines CPU/RAM scaling actions |
| **Async API Client** | `async_api_client.py` | Batch concurrent config fetching |
| **Config Manager** | `config_manager.py` | Loads and validates YAML configuration |
| **Data Manager** | `data_manager.py` | Preprocesses metrics and features |
| **Lock Manager** | `lock_manager.py` | Prevents multiple instances |
| **Logger** | `logger.py` | Structured logging |
| **Signal Handler** | `signal_handler.py` | Graceful shutdown on SIGTERM/SIGINT |

---

## Machine Learning Model

### IsolationForest Anomaly Detection

**Algorithm**: Isolation Forest (unsupervised learning)  
**Library**: `scikit-learn`  
**Purpose**: Detect unusual resource usage patterns that require scaling

#### How It Works

1. **Training**: Analyzes historical metrics to learn "normal" resource patterns
2. **Prediction**: For each container, predicts if current usage is an anomaly
3. **Scoring**: Returns -1 for anomaly, 1 for normal behavior

#### Features Used (26 total)

| Category | Features |
|----------|----------|
| **CPU** | `cpu_usage_percent`, `rolling_mean_cpu`, `rolling_std_cpu`, `cpu_trend`, `max_cpu`, `min_cpu`, `cpu_per_process` |
| **Memory** | `memory_usage_mb`, `rolling_mean_memory`, `rolling_std_memory`, `memory_trend`, `max_memory`, `min_memory`, `memory_per_process`, `swap_usage_mb`, `swap_total_mb` |
| **Combined** | `cpu_memory_ratio` |
| **Disk** | `filesystem_usage_gb`, `filesystem_free_gb`, `filesystem_total_gb` |
| **Network** | `network_rx_bytes`, `network_tx_bytes` |
| **I/O** | `io_reads`, `io_writes` |
| **System** | `process_count`, `time_diff` |

#### Model Configuration

```yaml
# lxc_autoscale_ml.yaml
isolation_forest:
  contamination: 0.1      # Expected % of anomalies (10%)
  n_estimators: 100       # Number of trees
  random_state: 42        # Reproducibility
  max_samples: auto       # Auto-tune sample size
```

#### Fixed Bugs

**❌ Old (Incorrect)**:
```python
# Bug: Treated any truthy value as anomaly!
if prediction:
    # This triggered on prediction=1 (normal!)
    scale_up()
```

**✅ New (Correct)**:
```python
# Correct: Check for -1 specifically
if prediction == -1:  # Anomaly detected
    # Evaluate if scaling is needed
    determine_scaling_action()
```

---

## Scaling Logic

### Incremental Scaling Strategy

The system now scales **gradually** to avoid resource waste and instability.

#### Before vs After

**❌ Old Behavior** (jump to extremes):
```python
if cpu_usage > threshold:
    scale_to_max_cpu()  # Jump from 2 → 8 cores!

if cpu_usage < threshold:
    scale_to_min_cpu()  # Jump from 8 → 1 core!
```

**✅ New Behavior** (incremental):
```python
if cpu_usage > threshold:
    scale_cpu(current_cores + cpu_step)  # 2 → 3 cores

if cpu_usage < threshold:
    scale_cpu(current_cores - cpu_step)  # 3 → 2 cores
```

### Scaling Rules

#### CPU Scaling

```python
# Scale UP if:
# 1. IsolationForest detects anomaly (-1)
# 2. CPU usage > cpu_scale_up_threshold (default 70%)
# 3. Current cores < max_cpu_cores

# Scale DOWN if:
# 1. IsolationForest reports normal (1)
# 2. CPU usage < cpu_scale_down_threshold (default 30%)
# 3. Current cores > min_cpu_cores

# Step size: cpu_scale_step (default 1 core)
```

#### RAM Scaling

```python
# Scale UP if:
# 1. IsolationForest detects anomaly (-1)
# 2. RAM usage % > ram_scale_up_threshold (default 80%)
# 3. Current RAM < max_ram_mb

# Scale DOWN if:
# 1. IsolationForest reports normal (1)
# 2. RAM usage % < ram_scale_down_threshold (default 40%)
# 3. Current RAM > min_ram_mb

# Step size: ram_scale_step_mb (default 512 MB)
```

### Fixed RAM Threshold Bug

**❌ Old (Incorrect)**:
```python
# Bug: Compared MB to percentage threshold!
if memory_usage_mb > 80:  # memory_usage_mb could be 4096!
    scale_up_ram()
```

**✅ New (Correct)**:
```python
# Calculate actual percentage
memory_usage_percent = (memory_usage_mb / current_ram_mb) * 100

if memory_usage_percent > ram_scale_up_threshold:
    scale_up_ram()
```

### Configuration

```yaml
# lxc_autoscale_ml.yaml
scaling:
  # CPU Thresholds
  cpu_scale_up_threshold: 70      # Scale up at 70% CPU
  cpu_scale_down_threshold: 30    # Scale down at 30% CPU
  cpu_scale_step: 1               # Add/remove 1 core at a time
  
  # RAM Thresholds
  ram_scale_up_threshold: 80      # Scale up at 80% RAM
  ram_scale_down_threshold: 40    # Scale down at 40% RAM
  ram_scale_step_mb: 512          # Add/remove 512MB at a time
  
  # Container Limits
  min_cpu_cores: 1
  max_cpu_cores: 8
  min_ram_mb: 512
  max_ram_mb: 16384
  
  # Confidence
  min_confidence: 70              # Only scale if >70% confidence
```

---

## Async Batch API Client

### The Performance Problem

**Old Sequential Approach**:
```python
for container_id in [101, 102, ..., 160]:  # 60 containers
    response = requests.get(f"/resource/vm/config?vm_id={container_id}")
    # Wait... wait... wait...
    
# Total time: 60 containers × 100ms = 6+ seconds per cycle!
```

### The Solution: Async Batch Fetching

**New Concurrent Approach**:
```python
# Fetch ALL at once!
all_configs = fetch_container_configs_sync(
    container_ids=[101, 102, ..., 160],
    api_url="http://127.0.0.1:5000",
    max_concurrent=10
)

# Total time: ~600ms (10x faster!)
```

### Performance Comparison

| Containers | Sequential | Async Batch | Speedup |
|------------|-----------|-------------|---------|
| 10 | 1.0s | 0.15s | **6.7x** |
| 20 | 2.0s | 0.25s | **8.0x** |
| 50 | 5.0s | 0.50s | **10x** |
| 100 | 10.0s | 1.0s | **10x** |
| 200 | 20.0s | 2.0s | **10x** |

**Real-World Log**:
```
INFO - Batch fetching configs for 60 containers...
INFO - Batch fetch completed in 0.58s: 60/60 successful (103.4 containers/sec)
```

### Features

1. **Concurrent Requests**: Up to 10 simultaneous API calls
2. **Connection Pooling**: Reuses TCP connections for efficiency
3. **Smart Retry**: Exponential backoff on failures (1s, 2s, 4s)
4. **Circuit Breaker Integration**: Skips known-bad endpoints
5. **Timeout Protection**: 5-second timeout per request
6. **Graceful Degradation**: Uses defaults if fetch fails

### Configuration

```yaml
# lxc_autoscale_ml.yaml
api:
  api_url: "http://127.0.0.1:5000"
  timeout: 5                    # Request timeout (seconds)
  max_concurrent: 10            # Max parallel requests
  retry_attempts: 3             # Retry failed requests
  circuit_breaker_threshold: 5  # Failures before circuit opens
```

---

## Circuit Breaker

### Purpose

Prevents the ML service from repeatedly calling failed API endpoints, which could:
- Waste CPU cycles on doomed requests
- Delay the entire scaling cycle
- Cause cascading failures

### How It Works

```python
class CircuitBreaker:
    def __init__(self, threshold=5, timeout=300):
        self.threshold = 5      # Open after 5 failures
        self.timeout = 300      # Stay open for 5 minutes
        self.failures = {}
        self.opened_at = {}
    
    def record_failure(self, endpoint):
        self.failures[endpoint] += 1
        if self.failures[endpoint] >= self.threshold:
            self.opened_at[endpoint] = time.time()  # Open circuit
    
    def is_open(self, endpoint):
        if endpoint in self.opened_at:
            if time.time() - self.opened_at[endpoint] > self.timeout:
                # Reset after timeout
                del self.opened_at[endpoint]
                self.failures[endpoint] = 0
                return False
            return True  # Still open
        return False
```

### Configuration

```yaml
# lxc_autoscale_ml.yaml
circuit_breaker:
  enabled: true
  failure_threshold: 5   # Open after 5 failures
  timeout_seconds: 300   # Reset after 5 minutes
```

---

## Configuration

### Complete Configuration File

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
  log_level: "INFO"  # DEBUG, INFO, WARNING, ERROR
  log_file: "/var/log/lxc_autoscale_ml.log"

# ML Model Configuration
isolation_forest:
  contamination: 0.1
  n_estimators: 100
  random_state: 42

# Scaling Configuration
scaling:
  # CPU
  cpu_scale_up_threshold: 70
  cpu_scale_down_threshold: 30
  cpu_scale_step: 1
  
  # RAM
  ram_scale_up_threshold: 80
  ram_scale_down_threshold: 40
  ram_scale_step_mb: 512
  
  # Limits
  min_cpu_cores: 1
  max_cpu_cores: 8
  min_ram_mb: 512
  max_ram_mb: 16384
  
  # Confidence
  min_confidence: 70

# Ignored Containers
ignore_lxc: []  # Empty = scale all containers

# Circuit Breaker
circuit_breaker:
  enabled: true
  failure_threshold: 5
  timeout_seconds: 300

# Sleep Configuration
sleep_interval: 60  # Seconds between cycles
```

---

## Logs

### Log Files

| File | Content |
|------|---------|
| `/var/log/lxc_autoscale_ml.log` | Main service logs |
| `/var/log/lxc_metrics.json` | Historical metrics (auto-limited to 1000 entries) |

### Log Examples

**Successful Scaling**:
```
INFO - Batch fetching configs for 60 containers...
INFO - Batch fetch completed in 0.58s: 60/60 successful (103.4 containers/sec)
INFO - Processing container 104...
INFO - IsolationForest prediction for 104: -1 (anomaly)
INFO - Scaling decision for 104: CPU=Scale Up, RAM=Scale Up (confidence: 87.4%)
INFO - Successfully scaled CPU for LXC ID 104 to 4 cores
INFO - Successfully scaled RAM for LXC ID 104 to 8192 MB
```

**Circuit Breaker**:
```
WARNING - API call failed for container 105 (attempt 3/3)
WARNING - Circuit breaker opened for api_105 (5 consecutive failures)
INFO - Skipping container 105 - circuit breaker open
```

---

## Troubleshooting

### Common Issues

#### 1. "No data to train model"

**Cause**: Metrics file is empty or doesn't exist  
**Solution**:
```bash
# Check if monitor is running
systemctl status lxc_monitor.service

# Check metrics file
cat /var/log/lxc_metrics.json | jq '.[-5:]'  # Last 5 entries

# Restart monitor if needed
systemctl restart lxc_monitor.service
```

#### 2. "Circuit breaker open for all containers"

**Cause**: API service is down or misconfigured  
**Solution**:
```bash
# Check API service
systemctl status lxc_autoscale_api.service

# Test API manually
curl http://127.0.0.1:5000/health/check

# Check API logs
journalctl -u lxc_autoscale_api.service -n 50
```

#### 3. "Batch fetch timeout"

**Cause**: Too many containers or slow API  
**Solution**:
```yaml
# Increase timeout in lxc_autoscale_ml.yaml
api:
  timeout: 10          # Was 5
  max_concurrent: 5    # Reduce concurrent (was 10)
```

#### 4. "Lock file exists"

**Cause**: Previous instance crashed  
**Solution**:
```bash
# Check if process is running
cat /var/lock/lxc_autoscale_ml.lock
ps -p <PID>  # Use PID from lock file

# If not running, service auto-cleans stale lock
systemctl restart lxc_autoscale_ml.service
```

---

## Performance Tuning

### For Small Deployments (< 20 containers)

```yaml
api:
  max_concurrent: 5
  timeout: 3

sleep_interval: 30  # Check every 30 seconds
```

### For Medium Deployments (20-60 containers)

```yaml
api:
  max_concurrent: 10  # Default
  timeout: 5

sleep_interval: 60  # Default
```

### For Large Deployments (60+ containers)

```yaml
api:
  max_concurrent: 15
  timeout: 10

sleep_interval: 120  # Check every 2 minutes

circuit_breaker:
  failure_threshold: 3  # Fail faster
  timeout_seconds: 600  # Longer recovery time
```

---

## Related Documentation

- **[API Documentation](../lxc_autoscale_api/README.md)** - REST API details
- **[Monitor Documentation](../lxc_monitor/README.md)** - Metrics collection
- **[Troubleshooting Guide](../TROUBLESHOOTING.md)** - Common issues
- **[Bug Fixes](../../BUGFIX_SCALING_ISSUE_6.md)** - Scaling logic fixes
- **[Performance Optimizations](../../QUICKWINS_80_20.md)** - 80/20 quick wins
- **[Rate Limiting Fix](../../FIXES_ISSUES_3_4.md)** - Issues #3 & #4 resolution

---

**Last Updated**: December 24, 2024  
**Version**: 2.0 (with async batch API + circuit breaker)
