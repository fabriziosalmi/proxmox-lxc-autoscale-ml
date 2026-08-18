# Troubleshooting

This guide helps diagnose and resolve common issues with LXC AutoScale ML.

## Quick Diagnostics

### Check All Services

```bash
systemctl status lxc_autoscale_api
systemctl status lxc_monitor
systemctl status lxc_autoscale_ml
```

### View Recent Logs

```bash
journalctl -u lxc_autoscale_ml -n 50 --no-pager
journalctl -u lxc_autoscale_api -n 50 --no-pager
journalctl -u lxc_monitor -n 50 --no-pager
```

### Test API Connectivity

```bash
curl http://localhost:5000/health/check
```

## Common Issues

### Container Not Scaling Down

**Symptom**: Containers remain at high resource allocation despite low usage.

**Possible causes**:

1. **Current resources not being fetched**

   Check if the API endpoint works:

   ```bash
   curl -H "X-API-Key: YOUR_KEY" \
     "http://localhost:5000/resource/lxc/config?lxc_id=104"
   ```

   If the API returns an error, restart the service:

   ```bash
   systemctl restart lxc_autoscale_api
   ```

2. **Thresholds too restrictive**

   Check current thresholds:

   ```bash
   grep threshold /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
   ```

   Default values:
   - `cpu_scale_down_threshold: 30` (CPU must be below 30%)
   - `ram_scale_down_threshold: 40` (RAM must be below 40%)

   Adjust if needed and restart:

   ```bash
   systemctl restart lxc_autoscale_ml
   ```

3. **Already at minimum resources**

   Check container limits:

   ```bash
   pct config 104 | grep -E "cores|memory"
   grep -E "min_cpu|min_ram" /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
   ```

### Container Jumps to Maximum Resources

**Symptom**: Resources jump directly to max values instead of incremental scaling.

**Diagnosis**:

```bash
grep -E "cpu_scale_step|ram_scale_step" /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
```

**Fix**: Ensure step sizes are configured:

```yaml
scaling:
  cpu_scale_step: 1        # Add/remove 1 core at a time
  ram_scale_step_mb: 512   # Add/remove 512 MB at a time
```

### No Scaling Happening

**Symptom**: Logs show "No scaling needed" even when resources are at extremes.

1. **Check metrics are being collected**

   ```bash
   ls -lh /var/log/lxc_metrics.json
   cat /var/log/lxc_metrics.json | jq '.[0]' | head -20
   ```

   If file is missing or old, restart the monitor:

   ```bash
   systemctl restart lxc_monitor
   ```

2. **Container in ignore list**

   ```bash
   grep -A5 "ignore_lxc" /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
   ```

3. **Insufficient historical data**

   Check data points:

   ```bash
   cat /var/log/lxc_metrics.json | jq 'length'
   ```

   The model needs at least 5-10 data points. Wait for more collection cycles.

### API Connection Errors

**Symptom**: Logs show "Error fetching config" or "API request failed"

**Diagnosis**:

```bash
# Check if API is listening
ss -tlnp | grep :5000

# Test connectivity
curl -v http://localhost:5000/health/check
```

**Fixes**:

```bash
# Restart API service
systemctl restart lxc_autoscale_api

# Check API logs
journalctl -u lxc_autoscale_api -n 100 --no-pager

# Verify API URL in config
grep api_url /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
```

### Configuration Validation Errors

**Symptom**: Service fails to start with config error messages.

**Common errors and fixes**:

| Error | Fix |
|-------|-----|
| `min_cpu_cores cannot be greater than max_cpu_cores` | Ensure `min_cpu_cores < max_cpu_cores` |
| `cpu_scale_down_threshold must be less than cpu_scale_up_threshold` | Adjust threshold values |
| Threshold not between 0-100 | Use percentage values (0-100) |

**Validate configuration syntax**:

```bash
python3 -c "import yaml; yaml.safe_load(open('/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml'))"
```

### Model Training Failures

**Symptom**: Logs show "Model training failed" or "Error during model training"

**Diagnosis**:

```bash
cat /var/log/lxc_metrics.json | jq '.[0] | to_entries | length'
```

**Fixes**:

```bash
# Validate JSON
jq empty /var/log/lxc_metrics.json

# If corrupted, reset metrics
mv /var/log/lxc_metrics.json /var/log/lxc_metrics.json.bak
systemctl restart lxc_monitor

# Check Python dependencies
pip3 list | grep -E "sklearn|pandas|numpy"
```

### Rate Limiting (429 Errors)

**Symptom**: API returns "Rate limit exceeded" errors.

**For external clients**:

The default limit is 120 requests per minute. Check remaining quota:

```bash
curl -I -H "X-API-Key: YOUR_KEY" http://proxmox:5000/routes
```

Look for headers:
```
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1703436789
```

**For internal services**:

Localhost requests bypass rate limiting. Ensure requests come from `127.0.0.1`:

```bash
curl http://127.0.0.1:5000/health/check
```

### Authentication Failures (401 Errors)

**Symptom**: API returns "Missing or invalid API key"

**Check API key configuration**:

```bash
grep -A2 "authentication" /etc/lxc_autoscale_ml/lxc_autoscale_api.yaml
```

**Verify header format**:

```bash
# Correct
curl -H "X-API-Key: your-key" http://localhost:5000/routes

# Alternative (query parameter)
curl -H "X-API-Key: your-key" http://localhost:5000/routes
```

### Lock File Issues

**Symptom**: Service reports "Lock file exists" on startup.

Version 2.0 includes automatic stale lock cleanup. If the issue persists:

```bash
# Check if process is running
cat /run/lxc_autoscale_ml.lock
ps -p $(cat /run/lxc_autoscale_ml.lock)

# If process not running, service auto-cleans
systemctl restart lxc_autoscale_ml

# Manual cleanup (if needed)
rm /run/lxc_autoscale_ml.lock
systemctl start lxc_autoscale_ml
```

### Circuit Breaker Open

**Symptom**: Logs show "Circuit breaker opened" or containers are skipped.

**Cause**: Too many consecutive API failures for a specific endpoint.

**Check status**:

```bash
grep "circuit breaker" /var/log/lxc_autoscale_ml.log
```

**Resolution**:

1. Verify API service is running:
   ```bash
   systemctl status lxc_autoscale_api
   ```

2. Circuit breaker resets automatically after timeout (default: 5 minutes)

3. Adjust settings if needed:
   ```yaml
   circuit_breaker:
     failure_threshold: 5   # Failures before opening
     timeout_seconds: 300   # Reset timeout
   ```

## Debug Mode

Enable detailed logging:

```yaml
# /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
logging:
  log_level: "DEBUG"
```

```bash
systemctl restart lxc_autoscale_ml
journalctl -u lxc_autoscale_ml -f
```

Debug output includes:
- Feature lists used for training
- Detailed threshold comparisons
- Anomaly detection details
- Step-by-step scaling calculations

## Health Check Script

```bash
#!/bin/bash
echo "=== LXC AutoScale Health Check ==="

echo -n "API Service: "
systemctl is-active lxc_autoscale_api && echo "OK" || echo "FAILED"

echo -n "ML Service: "
systemctl is-active lxc_autoscale_ml && echo "OK" || echo "FAILED"

echo -n "Monitor Service: "
systemctl is-active lxc_monitor && echo "OK" || echo "FAILED"

echo -n "API Health: "
curl -s http://localhost:5000/health/check | jq -r '.status' || echo "FAILED"

echo -n "Metrics File: "
if [ -f /var/log/lxc_metrics.json ]; then
  echo "OK ($(cat /var/log/lxc_metrics.json | jq 'length') entries)"
else
  echo "MISSING"
fi

echo ""
echo "Recent Scaling:"
grep "Successfully scaled" /var/log/lxc_autoscale_ml.log 2>/dev/null | tail -3
```

## Collecting Diagnostic Information

When reporting issues, collect this information:

```bash
#!/bin/bash
mkdir -p /tmp/diagnostics

# Service status
systemctl status lxc_autoscale_* > /tmp/diagnostics/service-status.txt 2>&1

# Logs
cp /var/log/lxc_autoscale_ml.log /tmp/diagnostics/ 2>/dev/null
journalctl -u lxc_autoscale_ml -n 200 > /tmp/diagnostics/ml-journal.txt 2>&1
journalctl -u lxc_autoscale_api -n 200 > /tmp/diagnostics/api-journal.txt 2>&1

# Configuration (sanitized - remove API key)
grep -v api_key /etc/lxc_autoscale_ml/*.yaml > /tmp/diagnostics/config.txt 2>/dev/null

# System info
pveversion > /tmp/diagnostics/pve-version.txt 2>&1
python3 --version > /tmp/diagnostics/python-version.txt 2>&1

# Create archive
tar czf /tmp/lxc-diagnostics-$(date +%Y%m%d).tar.gz -C /tmp diagnostics/
echo "Diagnostics: /tmp/lxc-diagnostics-$(date +%Y%m%d).tar.gz"
```

## Getting Help

- **GitHub Issues**: [Report a bug](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/issues)
- **Documentation**: Review the [Configuration Reference](/reference/configuration)
