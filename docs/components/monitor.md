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
4. Trim to max_metrics_entries
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
  "timestamp": "2026-08-18T13:07:56.123456+00:00",
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
monitoring:
  max_metrics_entries: 1000
```

Each entry is one collection cycle covering every running container, so the
file's size depends on how many containers you have as well as on this number.
The model retrains from the whole file each cycle, so this also bounds how long
training takes.

The oldest entries are dropped once the limit is reached, and the file is
written through a temporary file and renamed into place, so an interrupted write
cannot truncate it.

## Configuration Reference

```yaml
# /etc/lxc_autoscale_ml/lxc_monitor.yaml

logging:
  log_file: "/var/log/lxc_monitor.log"
  log_max_bytes: 5242880   # rotate at 5 MB
  log_backup_count: 7
  log_level: "INFO"

monitoring:
  export_file: "/var/log/lxc_metrics.json"
  check_interval: 60       # seconds between cycles
  enable_swap: true
  enable_network: true
  enable_filesystem: true
  parallel_processing: true
  max_workers: 8
  excluded_devices: ['loop', 'dm-']
  retry_limit: 3
  retry_delay: 2
  max_metrics_entries: 1000
```

Stopped containers are skipped because `pct list` is filtered on the status
column; there is no separate setting for it. The full list of options is in the
[configuration reference](/reference/configuration).

## Log Examples

**Normal operation:**

```
INFO - Starting new metrics collection cycle.
INFO - Collecting metrics for container: 101
INFO - Collecting metrics for container: 102
INFO - Metrics successfully exported to /var/log/lxc_metrics.json (987 entries)
INFO - Waiting for 60 seconds before the next cycle.
```

**Size limiting:**

```
INFO - Rotated metrics: removed 23 old entries, keeping last 1000
INFO - Metrics successfully exported to /var/log/lxc_metrics.json (1000 entries)
```

**A container that cannot be reached:**

```
WARNING - Attempt 1 failed for get_container_cpu_usage with error: ...
ERROR - All 3 attempts failed for get_container_cpu_usage.
ERROR - Failed to collect metrics for container 105: ...
```

One unreachable container does not cost the cycle; the rest are still written.

**Errors:**

```
ERROR - Failed to collect metrics from container 105: Connection timeout
WARNING - Container 106 is stopped, skipping
ERROR - Failed to parse metrics: Invalid JSON in lxc_metrics.json
```

## Performance Tuning

Three settings matter here: how often a cycle runs, how many containers are
probed at once, and how much history is kept.

### Few containers (under 20)

```yaml
monitoring:
  check_interval: 30       # more frequent samples
  max_workers: 8
  max_metrics_entries: 500
```

### Medium (20 to 60 containers)

```yaml
monitoring:
  check_interval: 60       # default
  max_workers: 8
  max_metrics_entries: 1000
```

### Many containers (60 and above)

```yaml
monitoring:
  check_interval: 120      # less frequent, each cycle costs more
  max_workers: 16
  max_metrics_entries: 1500
```

`check_interval` should not be shorter than a cycle actually takes; the log line
`Metrics successfully exported ...` tells you how long that is on your host.
`max_workers` bounds how many `pct exec` calls run at once, so raising it costs
host CPU during collection.

## Log Rotation

Create `/etc/logrotate.d/lxc-autoscale-api`:

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
