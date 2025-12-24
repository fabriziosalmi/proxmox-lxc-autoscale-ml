# LXC Monitor Documentation

**LXC Monitor** is a lightweight service that continuously collects resource metrics from LXC containers. It provides the historical data needed by the ML model to make intelligent scaling decisions.

## ✨ What's New

### Recent Updates (December 2024)

- **💾 Automatic Size Management**: Limits metrics file to 1000 entries to prevent memory issues
- **🔄 Smart Cleanup**: Automatically removes oldest entries when limit is reached
- **⚡ Performance**: Efficient JSON storage with optimized read/write operations
- **🛡️ Memory Protection**: Prevents OOM errors on long-running deployments

## Summary

- **[Overview](#overview)**: What the monitor does and why it's important
- **[Metrics Collected](#metrics-collected)**: Complete list of tracked metrics
- **[Configuration](#configuration)**: How to configure the monitor service
- **[Data Storage](#data-storage)**: How metrics are stored and managed
- **[Logs](#logs)**: Where to find and interpret monitor logs
- **[Troubleshooting](#troubleshooting)**: Common issues and solutions
- **[Performance](#performance)**: Optimization tips for different scales

---

## Overview

The LXC Monitor service runs continuously on your Proxmox host, collecting resource usage metrics from all running LXC containers. These metrics are stored in `/var/log/lxc_metrics.json` and used by the ML model to:

1. **Train the IsolationForest model** on historical patterns
2. **Detect anomalies** in current usage
3. **Make scaling decisions** based on trends

### How It Works

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
4. Check File Size (limit to 1000 entries)
   ↓
5. Sleep & Repeat
```

---

## Metrics Collected

### Per-Container Metrics

| Category | Metric | Unit | Description |
|----------|--------|------|-------------|
| **CPU** | `cpu_usage_percent` | % | Current CPU utilization |
| | `cpu_per_process` | % | CPU per running process |
| | `max_cpu` | % | Maximum CPU in collection window |
| | `min_cpu` | % | Minimum CPU in collection window |
| **Memory** | `memory_usage_mb` | MB | Current RAM usage |
| | `memory_per_process` | MB | RAM per running process |
| | `max_memory` | MB | Maximum RAM in collection window |
| | `min_memory` | MB | Minimum RAM in collection window |
| **Swap** | `swap_usage_mb` | MB | Current swap usage |
| | `swap_total_mb` | MB | Total swap available |
| **Disk** | `filesystem_usage_gb` | GB | Disk space used |
| | `filesystem_free_gb` | GB | Disk space free |
| | `filesystem_total_gb` | GB | Total disk capacity |
| **Network** | `network_rx_bytes` | Bytes | Total received bytes |
| | `network_tx_bytes` | Bytes | Total transmitted bytes |
| **I/O** | `io_reads` | Count | Total read operations |
| | `io_writes` | Count | Total write operations |
| **System** | `process_count` | Count | Number of running processes |
| | `timestamp` | ISO 8601 | Metric collection timestamp |
| | `container_id` | String | LXC container ID |

### Derived Metrics (Added by ML Model)

These are calculated from the raw metrics during feature engineering:

| Metric | Description |
|--------|-------------|
| `cpu_memory_ratio` | CPU % / Memory % |
| `rolling_mean_cpu` | 5-period moving average of CPU |
| `rolling_std_cpu` | 5-period standard deviation of CPU |
| `rolling_mean_memory` | 5-period moving average of memory |
| `rolling_std_memory` | 5-period standard deviation of memory |
| `cpu_trend` | Linear trend direction (up/down) |
| `memory_trend` | Linear trend direction (up/down) |
| `time_diff` | Seconds since last collection |

---

## Configuration

### Configuration File

**Location**: `/etc/lxc_autoscale_ml/lxc_monitor.yaml`

```yaml
# Metrics Configuration
metrics:
  output_file: "/var/log/lxc_metrics.json"
  max_entries: 1000                    # NEW: Limit file size
  collection_interval: 10              # Seconds between collections

# Logging Configuration
logging:
  log_level: "INFO"                    # DEBUG, INFO, WARNING, ERROR
  log_file: "/var/log/lxc_monitor.log"

# Container Filter
containers:
  ignore_stopped: true                 # Only collect from running containers
  ignore_templates: true               # Skip template containers
  
# Performance
performance:
  batch_size: 10                       # Containers to process per batch
  timeout: 5                           # Timeout per container (seconds)
```

### Service Configuration

**Systemd Unit**: `/lib/systemd/system/lxc_monitor.service`

```ini
[Unit]
Description=LXC Monitor Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/lxc_autoscale_ml/lxc_monitor/lxc_monitor.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

---

## Data Storage

### Metrics File Format

**File**: `/var/log/lxc_metrics.json`  
**Format**: JSON array with one object per collection

**Example Entry**:
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

### Size Management (NEW!)

**Problem Solved**: Old behavior allowed unlimited file growth, causing:
- Memory exhaustion (OOM errors)
- Slow model training
- Disk space issues

**Solution**: Automatic size limiting to 1000 entries

#### How It Works

```python
def limit_metrics_file_size(file_path, max_entries=1000):
    """Keep only the most recent max_entries in the metrics file."""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        if len(data) > max_entries:
            # Keep only most recent entries
            data = data[-max_entries:]
            
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            logging.info(f"Trimmed metrics file to {max_entries} entries")
    except Exception as e:
        logging.error(f"Failed to limit metrics file size: {e}")
```

#### Benefits

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Max file size** | Unlimited | ~2MB (1000 entries) | Bounded |
| **Memory usage** | Growing | Stable | No OOM |
| **Model training time** | Increasing | Constant | Predictable |
| **Disk I/O** | Linear growth | Constant | Efficient |

#### Configuration

```yaml
# lxc_monitor.yaml
metrics:
  max_entries: 1000  # Adjust based on needs

# Guidelines:
# - Small deployments (< 10 containers): 500 entries
# - Medium deployments (10-50 containers): 1000 entries (default)
# - Large deployments (50+ containers): 1500 entries
```

---

## Logs

### Log Files

| File | Content |
|------|---------|
| `/var/log/lxc_monitor.log` | Monitor service logs |
| `/var/log/lxc_metrics.json` | Collected metrics (max 1000 entries) |

### Log Examples

**Normal Operation**:
```
INFO - LXC Monitor started
INFO - Found 12 running containers
INFO - Collecting metrics from container 101...
INFO - Collecting metrics from container 102...
...
INFO - Collected metrics for 12 containers in 0.4s
INFO - Metrics file size: 987 entries
INFO - Sleeping for 10 seconds...
```

**Size Limiting**:
```
INFO - Collected metrics for 15 containers
WARNING - Metrics file has 1023 entries (limit: 1000)
INFO - Trimmed metrics file to 1000 entries (removed 23 oldest)
```

**Errors**:
```
ERROR - Failed to collect metrics from container 105: Connection timeout
WARNING - Container 106 is stopped, skipping
ERROR - Failed to parse metrics: Invalid JSON in lxc_metrics.json
```

### Log Rotation

```bash
# /etc/logrotate.d/lxc_monitor
/var/log/lxc_monitor.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 640 root adm
    sharedscripts
    postrotate
        systemctl reload lxc_monitor.service > /dev/null 2>&1 || true
    endscript
}
```

---

## Troubleshooting

### Common Issues

#### 1. "Metrics file not found"

**Cause**: Monitor service not running or permissions issue  
**Solution**:
```bash
# Check service status
systemctl status lxc_monitor.service

# Check file permissions
ls -la /var/log/lxc_metrics.json

# Create file if needed
touch /var/log/lxc_metrics.json
chmod 644 /var/log/lxc_metrics.json

# Restart service
systemctl restart lxc_monitor.service
```

#### 2. "Metrics file too large / OOM error"

**Cause**: Old version without size limiting  
**Solution**: Update to latest version (automatically limits to 1000 entries)
```bash
cd /usr/local/bin/lxc_autoscale_ml
git pull
systemctl restart lxc_monitor.service

# Manually trim if needed
jq '.[-1000:]' /var/log/lxc_metrics.json > /tmp/metrics_trimmed.json
mv /tmp/metrics_trimmed.json /var/log/lxc_metrics.json
```

#### 3. "No metrics for container X"

**Cause**: Container stopped, template, or permission issue  
**Solution**:
```bash
# Check container status
pct status 104

# Check if ignored in config
grep "ignore" /etc/lxc_autoscale_ml/lxc_monitor.yaml

# Test manual collection
pct exec 104 -- cat /proc/stat
```

#### 4. "Collection taking too long"

**Cause**: Too many containers or slow network  
**Solution**:
```yaml
# Increase batch size and timeout
performance:
  batch_size: 20     # Was 10
  timeout: 10        # Was 5
  
# Or increase collection interval
metrics:
  collection_interval: 30  # Was 10
```

#### 5. "Invalid JSON in metrics file"

**Cause**: Corrupted file (e.g., service crashed during write)  
**Solution**:
```bash
# Validate JSON
jq '.' /var/log/lxc_metrics.json

# If corrupted, restore from backup or start fresh
mv /var/log/lxc_metrics.json /var/log/lxc_metrics.json.corrupt
echo "[]" > /var/log/lxc_metrics.json

# Restart service
systemctl restart lxc_monitor.service
```

---

## Performance

### Collection Speed

**Typical Performance**:
- 10 containers: ~0.2s
- 50 containers: ~1.0s
- 100 containers: ~2.0s

### Optimization Tips

#### For Small Deployments (< 20 containers)

```yaml
metrics:
  collection_interval: 5   # More frequent
  max_entries: 500         # Less history needed

performance:
  batch_size: 10           # Default
  timeout: 3               # Shorter timeout
```

#### For Medium Deployments (20-60 containers)

```yaml
metrics:
  collection_interval: 10  # Default
  max_entries: 1000        # Default

performance:
  batch_size: 10           # Default
  timeout: 5               # Default
```

#### For Large Deployments (60+ containers)

```yaml
metrics:
  collection_interval: 30  # Less frequent
  max_entries: 1500        # More history for ML

performance:
  batch_size: 20           # Larger batches
  timeout: 10              # Longer timeout
```

### Memory Usage

| Configuration | Memory Usage |
|---------------|--------------|
| 500 entries × 10 containers | ~1 MB |
| 1000 entries × 50 containers | ~10 MB |
| 1500 entries × 100 containers | ~30 MB |

---

## Integration with ML Model

The monitor is designed to work seamlessly with the ML model:

1. **Collects metrics** every 10 seconds (configurable)
2. **Stores in JSON** at `/var/log/lxc_metrics.json`
3. **ML model reads** this file periodically
4. **Trains IsolationForest** on historical data
5. **Makes predictions** on current usage
6. **Triggers scaling** via API

### Data Flow

```
LXC Container
   ↓ (metrics)
LXC Monitor
   ↓ (JSON file)
lxc_metrics.json
   ↓ (read)
ML Model
   ↓ (predictions)
Scaling Decisions
   ↓ (API calls)
LXC AutoScale API
   ↓ (apply)
LXC Container (scaled)
```

---

## Monitoring the Monitor

### Health Checks

```bash
# Check service is running
systemctl is-active lxc_monitor.service

# Check recent logs
journalctl -u lxc_monitor.service -n 50

# Check metrics file age
stat /var/log/lxc_metrics.json

# Check metrics file size
ls -lh /var/log/lxc_metrics.json

# Count entries
jq 'length' /var/log/lxc_metrics.json

# Check last collection timestamp
jq '.[-1].timestamp' /var/log/lxc_metrics.json
```

### Automated Monitoring Script

```bash
#!/bin/bash
# /usr/local/bin/check_lxc_monitor.sh

# Check if service is running
if ! systemctl is-active --quiet lxc_monitor.service; then
    echo "CRITICAL: lxc_monitor service is not running"
    exit 2
fi

# Check metrics file age (should update every 10 seconds)
if [ $(find /var/log/lxc_metrics.json -mmin +1 | wc -l) -gt 0 ]; then
    echo "WARNING: Metrics file is stale (>1 minute old)"
    exit 1
fi

# Check file size (should be < 5MB)
SIZE=$(stat -f%z /var/log/lxc_metrics.json 2>/dev/null || stat -c%s /var/log/lxc_metrics.json)
if [ $SIZE -gt 5242880 ]; then
    echo "WARNING: Metrics file is too large (${SIZE} bytes)"
    exit 1
fi

echo "OK: lxc_monitor is healthy"
exit 0
```

---

## Related Documentation

- **[API Documentation](../lxc_autoscale_api/README.md)** - REST API details
- **[Model Documentation](../lxc_model/README.md)** - ML model and scaling logic
- **[Troubleshooting Guide](../TROUBLESHOOTING.md)** - Common issues
- **[Quick Wins](../../QUICKWINS_80_20.md)** - Performance optimizations

---

**Last Updated**: December 24, 2024  
**Version**: 2.0 (with automatic size management)
