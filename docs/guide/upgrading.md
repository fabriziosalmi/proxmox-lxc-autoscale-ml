# Upgrading

This guide covers upgrading LXC AutoScale ML from previous versions.

## Upgrade from 1.x to 2.0

Version 2.0 introduces significant improvements including batch async API, enhanced security, and critical bug fixes.

### Step 1: Backup Configuration

```bash
cp /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml.backup
cp /etc/lxc_autoscale_ml/lxc_autoscale_api.yaml /etc/lxc_autoscale_ml/lxc_autoscale_api.yaml.backup
cp /etc/lxc_autoscale_ml/lxc_monitor.yaml /etc/lxc_autoscale_ml/lxc_monitor.yaml.backup
```

### Step 2: Stop Services

```bash
systemctl stop lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

### Step 3: Install New Dependencies

```bash
apt install -y python3-aiohttp
# Optional: apt install -y python3-prometheus-client
```

### Step 4: Update Application Files

```bash
cd /tmp
git clone https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml.git
cp -r lxc-autoscale-ml/lxc_autoscale_ml/* /usr/local/bin/lxc_autoscale_ml/
```

### Step 5: Update Configuration

Add new settings to `/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml`:

```yaml
authentication:
  enabled: true
  api_keys:
    - "your-secret-key-here"  # Generate with: openssl rand -hex 32

rate_limiting:
  enabled: true
  max_requests_per_minute: 120  # Increased from 60
  time_window_seconds: 60
```

Add new settings to `/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml`:

```yaml
scaling:
  cpu_scale_step: 1           # NEW: Incremental scaling
  ram_scale_step_mb: 512      # NEW: Incremental scaling

ignore_lxc: []                # CHANGED: Was ["101", "102"]

circuit_breaker:              # NEW section
  enabled: true
  failure_threshold: 5
  timeout_seconds: 300
```

Add new settings to `/etc/lxc_autoscale_ml/lxc_monitor.yaml`:

```yaml
monitoring:
  max_metrics_entries: 1000   # NEW: bounds the metrics file
```

### Step 6: Start Services

```bash
systemctl start lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

### Step 7: Verify Upgrade

```bash
# Check services are running
systemctl status lxc_autoscale_api lxc_autoscale_ml lxc_monitor

# Test API with authentication
curl -H "X-API-Key: your-secret-key-here" http://127.0.0.1:5000/health/check

# Monitor logs for batch fetch
journalctl -u lxc_autoscale_ml -f | grep "Batch fetch"
```

## Breaking Changes in 2.0

### API Authentication Required

All endpoints except `/health/check` and `/metrics` now require authentication.

**Before (1.x):**

```bash
curl http://proxmox:5000/resource/lxc/status?lxc_id=104
```

**After (2.0):**

```bash
curl -H "X-API-Key: your-key" http://proxmox:5000/resource/lxc/status?lxc_id=104
```

### Default Ignore List Changed

The default `ignore_lxc` list is now empty. Previously, containers 101 and 102 were ignored by default.

**Action required:** Review your `ignore_lxc` setting and add any containers you want to exclude from scaling.

### Rate Limit Increased

The default rate limit increased from 60 to 120 requests per minute. Localhost requests are now exempt from rate limiting.

## Update Scripts and Automation

If you have scripts calling the API, update them to include authentication:

```bash
# Old
curl -X POST http://proxmox:5000/scale/cores \
  -H "Content-Type: application/json" \
  -d '{"lxc_id": 104, "cores": 4}'

# New
curl -X POST http://proxmox:5000/scale/cores \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"lxc_id": 104, "cores": 4}'
```

## Rollback Procedure

If you need to rollback to version 1.x:

```bash
# Stop services
systemctl stop lxc_autoscale_api lxc_monitor lxc_autoscale_ml

# Restore configuration
cp /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml.backup /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
cp /etc/lxc_autoscale_ml/lxc_autoscale_api.yaml.backup /etc/lxc_autoscale_ml/lxc_autoscale_api.yaml

# Restore old application files from your backup or re-download 1.x release

# Start services
systemctl start lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

## Verify Performance Improvements

After upgrading, you should see significant performance improvements in the logs:

```
# Before (1.x) - Sequential fetching
INFO - Fetching config for container 101...
INFO - Fetching config for container 102...
# Takes ~6 seconds for 60 containers

# After (2.0) - Batch async fetching
INFO - Batch fetching configs for 60 containers...
INFO - Batch fetch completed in 0.58s: 60/60 successful (103.4 containers/sec)
```

## Next Steps

- [Configuration](/reference/configuration): Review all new configuration options
