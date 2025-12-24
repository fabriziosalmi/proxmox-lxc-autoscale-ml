# Troubleshooting Guide - LXC AutoScale ML

This guide helps diagnose and resolve common issues with the LXC AutoScale ML system.

## 🔍 Quick Diagnostics

### Check Service Status
```bash
# Check all services
systemctl status lxc_autoscale_api
systemctl status lxc_autoscale_ml
systemctl status lxc_monitor

# View recent logs
journalctl -u lxc_autoscale_ml -n 50 --no-pager
journalctl -u lxc_autoscale_api -n 50 --no-pager
```

### Check Log Files
```bash
# Model service logs
tail -f /var/log/lxc_autoscale_ml.log

# API service logs
tail -f /var/log/lxc_autoscale_api.log

# Monitor logs
tail -f /var/log/lxc_metrics.json
```

### Test API Connectivity
```bash
# Check API is running
curl http://localhost:5000/health/check

# Get container configuration
curl http://localhost:5000/resource/vm/config?vm_id=113

# List available routes
curl http://localhost:5000/routes
```

---

## ⚠️ Common Issues

### 1. Container Not Scaling Down

**Symptom:** Containers remain at high resource allocation despite low usage.

**Possible Causes:**

#### A. Current resources not being fetched
```bash
# Check if API endpoint works
curl http://localhost:5000/resource/vm/config?vm_id=YOUR_CONTAINER_ID

# Expected output:
{
  "data": {
    "vm_id": "113",
    "cores": 8,
    "memory_mb": 20480
  },
  "message": "Successfully retrieved configuration for VM 113",
  "status": "success"
}
```

**Fix:** If API returns an error, restart the API service:
```bash
systemctl restart lxc_autoscale_api
```

#### B. Thresholds too restrictive
```bash
# Check current thresholds
cat /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml | grep threshold
```

**Default thresholds:**
- `cpu_scale_down_threshold: 30` - CPU must be below 30% to scale down
- `ram_scale_down_threshold: 30` - RAM must be below 30% to scale down

**Fix:** Adjust thresholds if needed:
```yaml
# In /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
scaling:
  cpu_scale_down_threshold: 40  # Scale down when CPU < 40%
  ram_scale_down_threshold: 40  # Scale down when RAM < 40%
```

Then restart:
```bash
systemctl restart lxc_autoscale_ml
```

#### C. Already at minimum resources
Check if container is at configured minimum:
```bash
# View current config
pct config YOUR_CONTAINER_ID | grep -E "cores|memory"
```

Compare with minimums in config:
```bash
grep -E "min_cpu_cores|min_ram_mb" /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
```

### 2. Container Only Scales to Maximum

**Symptom:** Resources jump directly to max values instead of incremental scaling.

**Diagnosis:**
```bash
# Check for incremental step configuration
grep -E "cpu_scale_step|ram_scale_step" /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
```

**Fix:** Ensure step sizes are configured:
```yaml
scaling:
  cpu_scale_step: 1              # Add/remove 1 core at a time
  ram_scale_step_mb: 512         # Add/remove 512MB at a time
```

**Verify fix version:**
```bash
# Check if the bug fix is applied
grep -A5 "current_cores + cpu_step" /usr/local/bin/lxc_autoscale_ml/scaling.py
```

Should show incremental logic, not `min(total_cores, max_cpu_cores)`.

### 3. No Scaling Happening at All

**Symptom:** Logs show "No scaling needed" even when resources are at extremes.

#### A. Check metrics are being collected
```bash
# Verify metrics file exists and is recent
ls -lh /var/log/lxc_metrics.json
cat /var/log/lxc_metrics.json | jq '.[0]' | head -20
```

**Fix:** If file is missing or old, restart monitor:
```bash
systemctl restart lxc_monitor
```

#### B. Container in ignore list
```bash
# Check if container is ignored
grep -A5 "ignore_lxc" /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
```

**Fix:** Remove container from ignore list if needed.

#### C. Insufficient historical data
```bash
# Check how many data points exist
cat /var/log/lxc_metrics.json | jq 'length'
```

The model needs at least 5-10 data points. Wait for more collection cycles (default: 60 seconds per cycle).

### 4. API Connection Errors

**Symptom:** Logs show "Error fetching config" or "API request failed"

**Diagnosis:**
```bash
# Check if API is listening
netstat -tlnp | grep :5000

# Check if API service is running
systemctl status lxc_autoscale_api

# Test from localhost
curl -v http://localhost:5000/health/check
```

**Fixes:**

```bash
# Restart API service
systemctl restart lxc_autoscale_api

# Check API logs for errors
journalctl -u lxc_autoscale_api -n 100 --no-pager

# Verify API URL in config matches
grep api_url /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
```

### 5. Configuration Validation Errors

**Symptom:** Service fails to start with config error messages.

**Common errors:**

#### "min_cpu_cores cannot be greater than max_cpu_cores"
```yaml
# Fix in /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
scaling:
  min_cpu_cores: 2
  max_cpu_cores: 8  # Must be >= min_cpu_cores
```

#### "cpu_scale_down_threshold must be less than cpu_scale_up_threshold"
```yaml
scaling:
  cpu_scale_down_threshold: 30   # Must be less than scale_up
  cpu_scale_up_threshold: 75
```

#### Threshold not between 0-100
```yaml
scaling:
  cpu_scale_up_threshold: 75     # Must be 0-100 (percentage)
  ram_scale_up_threshold: 75     # Must be 0-100 (percentage)
```

**Validate config:**
```bash
# Test config syntax
python3 -c "import yaml; yaml.safe_load(open('/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml'))"

# Restart service after fixing
systemctl restart lxc_autoscale_ml
```

### 6. Model Training Failures

**Symptom:** Logs show "Model training failed" or "Error during model training"

**Diagnosis:**
```bash
# Check for sufficient data
cat /var/log/lxc_metrics.json | jq '.[0] | to_entries | length'

# Check for data format issues
cat /var/log/lxc_metrics.json | jq '.[0]' | head
```

**Fixes:**

```bash
# Ensure metrics file is valid JSON
jq empty /var/log/lxc_metrics.json

# If corrupted, backup and restart monitor
mv /var/log/lxc_metrics.json /var/log/lxc_metrics.json.bak
systemctl restart lxc_monitor

# Check Python dependencies
pip3 list | grep -E "sklearn|pandas|numpy"
```

### 7. RAM Usage Shows Incorrect Values

**Symptom:** RAM thresholds don't match actual usage patterns.

**After bug fix**, RAM is compared as percentage, not absolute MB.

**Verify:**
```bash
# Check logs for RAM percentage calculation
grep "Memory usage:" /var/log/lxc_autoscale_ml.log | tail -5
```

Should show: `Memory usage: 497MB (2.4%)` not just `Memory usage: 497MB`

**If old behavior:**
```bash
# Update to latest version
cd /tmp
git clone https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml.git
cp proxmox-lxc-autoscale-ml/lxc_autoscale_ml/model/scaling.py /usr/local/bin/lxc_autoscale_ml/
systemctl restart lxc_autoscale_ml
```

---

## 🔧 Advanced Diagnostics

### Enable DEBUG Logging

```yaml
# In /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
log_level: "DEBUG"
```

```bash
systemctl restart lxc_autoscale_ml
tail -f /var/log/lxc_autoscale_ml.log
```

Debug output includes:
- Feature lists used for training
- Detailed threshold comparisons
- Anomaly detection details
- Step-by-step scaling calculations

### Test Scaling Manually

```bash
# Scale CPU manually
curl -X POST http://localhost:5000/scale/cores \
  -H "Content-Type: application/json" \
  -d '{"vm_id": 113, "cores": 4}'

# Scale RAM manually
curl -X POST http://localhost:5000/scale/ram \
  -H "Content-Type: application/json" \
  -d '{"vm_id": 113, "memory": 4096}'

# Verify changes
pct config 113 | grep -E "cores|memory"
```

### Dry Run Mode

Test scaling decisions without making changes:

```yaml
# In /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
scaling:
  dry_run: true
```

```bash
systemctl restart lxc_autoscale_ml
# Watch logs to see scaling decisions without applying them
tail -f /var/log/lxc_autoscale_ml.log
```

### Check IsolationForest Model

```bash
# View model training details in logs
grep "IsolationForest\|Features used" /var/log/lxc_autoscale_ml.log | tail -20

# Check contamination setting (fraction of outliers expected)
grep contamination /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
```

Default: `contamination: 0.05` (5% of data expected to be anomalies)

---

## 📊 Monitoring Best Practices

### Regular Health Checks

```bash
#!/bin/bash
# Save as /usr/local/bin/lxc-autoscale-health.sh

echo "=== LXC AutoScale Health Check ==="
echo ""

echo "Service Status:"
systemctl is-active lxc_autoscale_api && echo "✅ API Running" || echo "❌ API Down"
systemctl is-active lxc_autoscale_ml && echo "✅ ML Running" || echo "❌ ML Down"
systemctl is-active lxc_monitor && echo "✅ Monitor Running" || echo "❌ Monitor Down"
echo ""

echo "API Health:"
curl -s http://localhost:5000/health/check | jq . || echo "❌ API Not Responding"
echo ""

echo "Recent Metrics:"
if [ -f /var/log/lxc_metrics.json ]; then
    echo "✅ Metrics file exists"
    echo "Data points: $(cat /var/log/lxc_metrics.json | jq 'length')"
    echo "Latest timestamp: $(cat /var/log/lxc_metrics.json | jq -r '.[-1] | to_entries | .[0].value.timestamp')"
else
    echo "❌ Metrics file missing"
fi
echo ""

echo "Recent Scaling Actions:"
grep "Successfully scaled" /var/log/lxc_autoscale_ml.log | tail -5
```

```bash
chmod +x /usr/local/bin/lxc-autoscale-health.sh
/usr/local/bin/lxc-autoscale-health.sh
```

---

## 🆘 Getting Help

### Collect Diagnostic Information

```bash
#!/bin/bash
# Create diagnostic bundle

OUTFILE="lxc-autoscale-diagnostics-$(date +%Y%m%d-%H%M%S).tar.gz"

mkdir -p /tmp/diagnostics
cd /tmp/diagnostics

# Collect logs
cp /var/log/lxc_autoscale_ml.log .
cp /var/log/lxc_autoscale_api.log .
cp /var/log/lxc_metrics.json .

# Collect configs (sanitized)
cp /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml .

# System info
systemctl status lxc_autoscale_* > service-status.txt
pip3 list > python-packages.txt
pveversion > pve-version.txt

# Create archive
cd /tmp
tar czf "$OUTFILE" diagnostics/
rm -rf diagnostics/

echo "Diagnostic bundle created: /tmp/$OUTFILE"
echo "Please attach this file when reporting issues."
```

### Report an Issue

When reporting issues on GitHub, include:
1. Diagnostic bundle from above
2. Description of expected vs actual behavior
3. Container IDs affected
4. Any recent configuration changes
5. Output of health check script

**GitHub Issues:** https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/issues

---

## 📚 Additional Resources

- [Main README](../README.md)
- [API Documentation](lxc_autoscale_api/README.md)
- [Model Documentation](lxc_model/README.md)
- [Monitor Documentation](lxc_monitor/README.md)
- [Bug Fix Documentation](../BUGFIX_SCALING_ISSUE_6.md)
