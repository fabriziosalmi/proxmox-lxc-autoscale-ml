# Monitor Component

The Monitor component collects resource metrics from LXC containers and stores them for the ML model.

## Overview

| Property | Value |
|----------|-------|
| Service | `lxc_monitor` |
| Configuration | `/etc/lxc_autoscale_ml/lxc_monitor.yaml` |
| Output File | `/var/log/lxc_metrics.json` |
| Log File | `/var/log/lxc_monitor.log` |

## Features

- **Real-time Metrics Collection**: CPU, memory, disk, network, I/O
- **Automatic Size Management**: Limits file to 1000 entries
- **Efficient Storage**: Optimized JSON with automatic cleanup
- **Memory Protection**: Prevents OOM on long-running deployments

## Processing Loop

```
1. Scan for Running Containers
   ↓
2. For Each Container:
   - Collect CPU usage (%)
   - Collect memory usage (MB)
   - Collect swap usage (MB)
   - Collect disk usage (GB)
   - Collect network stats (bytes)
   - Collect I/O stats (reads/writes)
   - Collect process count
   ↓
3. Append to Metrics File
   ↓
4. Check File Size (limit to max_entries)
   ↓
5. Sleep & Repeat
```

## Metrics Collected

### Per-Container Metrics

| Category | Metric | Unit | Description |
|----------|--------|------|-------------|
| **CPU** | `cpu_usage_percent` | % | Current CPU utilization |
| | `cpu_per_process` | % | CPU per running process |
| | `max_cpu` | % | Maximum CPU in window |
| | `min_cpu` | % | Minimum CPU in window |
| **Memory** | `memory_usage_mb` | MB | Current RAM usage |
| | `memory_per_process` | MB | RAM per running process |
| | `max_memory` | MB | Maximum RAM in window |
| | `min_memory` | MB | Minimum RAM in window |
| **Swap** | `swap_usage_mb` | MB | Current swap usage |
| | `swap_total_mb` | MB | Total swap available |
| **Disk** | `filesystem_usage_gb` | GB | Disk space used |
| | `filesystem_free_gb` | GB | Disk space free |
| | `filesystem_total_gb` | GB | Total disk capacity |
| **Network** | `network_rx_bytes` | Bytes | Total received bytes |
| | `network_tx_bytes` | Bytes | Total transmitted bytes |
| **I/O** | `io_reads` | Count | Total read operations |
| | `io_writes` | Count | Total write operations |
| **System** | `process_count` | Count | Number of processes |
| | `timestamp` | ISO 8601 | Collection timestamp |
| | `container_id` | String | LXC container ID |

### Derived Metrics

The ML model calculates these additional features:

| Metric | Description |
|--------|-------------|
| `cpu_memory_ratio` | CPU % / Memory % |
| `rolling_mean_cpu` | 5-period moving average |
| `rolling_std_cpu` | 5-period standard deviation |
| `rolling_mean_memory` | 5-period moving average |
| `rolling_std_memory` | 5-period standard deviation |
| `cpu_trend` | Linear trend direction |
| `memory_trend` | Linear trend direction |
| `time_diff` | Seconds since last collection |

## Metrics File Format

**Location:** `/var/log/lxc_metrics.json`

**Format:** JSON array with one object per collection

**Example entry:**

```json
{
  "timestamp": "2024-12-24T13:07:56.123456",
  "container_id": "104",
  "cpu_usage_percent": 45.2,
  "memory_usage_mb": 2048,
  "swap_usage_mb": 0,
  "swap_total_mb": 512,
  "filesystem_usage_gb": 8.5,
  "filesystem_free_gb": 11.5,
  "filesystem_total_gb": 20.0,
  "network_rx_bytes": 123456789,
  "network_tx_bytes": 987654321,
  "io_reads": 45123,
  "io_writes": 89456,
  "process_count": 87,
  "max_cpu": 52.1,
  "min_cpu": 38.7,
  "max_memory": 2156,
  "min_memory": 1987,
  "cpu_per_process": 0.52,
  "memory_per_process": 23.5
}
```

## Size Management

### Problem Solved

Unlimited file growth caused:
- Memory exhaustion (OOM errors)
- Slow model training
- Disk space issues

### Solution

Automatic size limiting to 1000 entries (configurable).

### Configuration

```yaml
metrics:
  max_entries: 1000
```

**Guidelines:**

| Deployment Size | Recommended `max_entries` |
|-----------------|---------------------------|
| Small (< 10 containers) | 500 |
| Medium (10-50 containers) | 1000 (default) |
| Large (50+ containers) | 1500 |

### Impact

| Metric | Before | After |
|--------|--------|-------|
| Max file size | Unlimited | ~2 MB |
| Memory usage | Growing | Stable |
| Model training time | Increasing | Constant |

## Configuration Reference

```yaml
# /etc/lxc_autoscale_ml/lxc_monitor.yaml

# Metrics Configuration
metrics:
  output_file: "/var/log/lxc_metrics.json"
  max_entries: 1000
  collection_interval: 10  # Seconds

# Logging Configuration
logging:
  log_level: "INFO"
  log_file: "/var/log/lxc_monitor.log"

# Container Filter
containers:
  ignore_stopped: true
  ignore_templates: true

# Performance
performance:
  batch_size: 10
  timeout: 5
```

## Log Examples

**Normal operation:**

```
INFO - LXC Monitor started
INFO - Found 12 running containers
INFO - Collecting metrics from container 101...
INFO - Collecting metrics from container 102...
INFO - Collected metrics for 12 containers in 0.4s
INFO - Metrics file size: 987 entries
INFO - Sleeping for 10 seconds...
```

**Size limiting:**

```
INFO - Collected metrics for 15 containers
WARNING - Metrics file has 1023 entries (limit: 1000)
INFO - Trimmed metrics file to 1000 entries (removed 23 oldest)
```

**Errors:**

```
ERROR - Failed to collect metrics from container 105: Connection timeout
WARNING - Container 106 is stopped, skipping
ERROR - Failed to parse metrics: Invalid JSON in lxc_metrics.json
```

## Performance Tuning

### Small Deployments (< 20 containers)

```yaml
metrics:
  collection_interval: 5   # More frequent
  max_entries: 500

performance:
  batch_size: 10
  timeout: 3
```

### Medium Deployments (20-60 containers)

```yaml
metrics:
  collection_interval: 10  # Default
  max_entries: 1000

performance:
  batch_size: 10
  timeout: 5
```

### Large Deployments (60+ containers)

```yaml
metrics:
  collection_interval: 30  # Less frequent
  max_entries: 1500

performance:
  batch_size: 20
  timeout: 10
```

## Log Rotation

Create `/etc/logrotate.d/lxc_monitor`:

```
/var/log/lxc_monitor.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 640 root adm
    sharedscripts
    postrotate
        systemctl reload lxc_monitor > /dev/null 2>&1 || true
    endscript
}
```

## Monitoring the Monitor

### Health Checks

```bash
# Check service
systemctl is-active lxc_monitor

# Check file age
stat /var/log/lxc_metrics.json

# Count entries
cat /var/log/lxc_metrics.json | jq 'length'

# Check last timestamp
cat /var/log/lxc_metrics.json | jq '.[-1].timestamp'
```

### Automated Check Script

```bash
#!/bin/bash

if ! systemctl is-active --quiet lxc_monitor; then
    echo "CRITICAL: lxc_monitor is not running"
    exit 2
fi

if [ $(find /var/log/lxc_metrics.json -mmin +1 | wc -l) -gt 0 ]; then
    echo "WARNING: Metrics file is stale"
    exit 1
fi

echo "OK: lxc_monitor is healthy"
exit 0
```

## Troubleshooting

### Metrics File Not Found

```bash
# Check service
systemctl status lxc_monitor

# Create file if needed
touch /var/log/lxc_metrics.json
chmod 644 /var/log/lxc_metrics.json
echo "[]" > /var/log/lxc_metrics.json

# Restart service
systemctl restart lxc_monitor
```

### OOM Errors

Update to latest version (automatic size limiting) or manually trim:

```bash
jq '.[-1000:]' /var/log/lxc_metrics.json > /tmp/metrics.json
mv /tmp/metrics.json /var/log/lxc_metrics.json
```

### Invalid JSON

```bash
# Validate
jq empty /var/log/lxc_metrics.json

# If corrupted, reset
mv /var/log/lxc_metrics.json /var/log/lxc_metrics.json.corrupt
echo "[]" > /var/log/lxc_metrics.json
systemctl restart lxc_monitor
```

## Next Steps

- [Model Component](/components/model): ML engine
- [Configuration Reference](/reference/configuration): All settings
- [Troubleshooting](/guide/troubleshooting): Common issues
