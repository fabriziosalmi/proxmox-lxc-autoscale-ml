# Basic Usage

This guide covers day-to-day usage of LXC AutoScale ML.

## Service Management

### Check Status

```bash
systemctl status lxc_autoscale_api
systemctl status lxc_monitor
systemctl status lxc_autoscale_ml
```

### Start Services

```bash
systemctl start lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

### Stop Services

```bash
systemctl stop lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

### Restart Services

```bash
systemctl restart lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

## Monitoring Scaling Activity

### View Real-Time Logs

```bash
journalctl -u lxc_autoscale_ml -f
```

Example output showing a scaling decision:

```
INFO - Batch fetching configs for 12 containers...
INFO - Batch fetch completed in 0.15s: 12/12 successful
INFO - Processing container 104...
INFO - IsolationForest prediction for 104: -1 (anomaly)
INFO - Scaling decision for 104: CPU=Scale Up (confidence: 87.4%)
INFO - Successfully scaled CPU for LXC ID 104 to 4 cores
INFO - Sleeping for 60 seconds before the next run.
```

### Check Recent Scaling Actions

```bash
grep "Successfully scaled" /var/log/lxc_autoscale_ml.log | tail -20
```

## API Usage

### Health Check

```bash
curl http://localhost:5000/health/check
```

### List Available Routes

```bash
curl -H "X-API-Key: YOUR_API_KEY" http://localhost:5000/routes
```

### Get Container Status

```bash
curl -H "X-API-Key: YOUR_API_KEY" \
  "http://localhost:5000/resource/vm/status?vm_id=104"
```

### Get Container Configuration

```bash
curl -H "X-API-Key: YOUR_API_KEY" \
  "http://localhost:5000/resource/vm/config?vm_id=104"
```

### Manual CPU Scaling

```bash
curl -X POST http://localhost:5000/scale/cores \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"vm_id": 104, "cores": 4}'
```

### Manual RAM Scaling

```bash
curl -X POST http://localhost:5000/scale/ram \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"vm_id": 104, "memory": 4096}'
```

## Checking Metrics

### View Current Metrics

```bash
cat /var/log/lxc_metrics.json | jq '.[-1]'
```

### Count Metrics Entries

```bash
cat /var/log/lxc_metrics.json | jq 'length'
```

### View Metrics for Specific Container

```bash
cat /var/log/lxc_metrics.json | jq '.[] | select(.container_id == "104")' | tail -20
```

## Excluding Containers

To exclude containers from autoscaling, edit `/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml`:

```yaml
ignore_lxc:
  - "101"
  - "102"
  - "999"
```

Restart the service:

```bash
systemctl restart lxc_autoscale_ml
```

## Adjusting Thresholds

Edit `/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml`:

```yaml
scaling:
  cpu_scale_up_threshold: 80    # Scale up at 80% CPU
  cpu_scale_down_threshold: 20  # Scale down at 20% CPU
  ram_scale_up_threshold: 85    # Scale up at 85% RAM
  ram_scale_down_threshold: 30  # Scale down at 30% RAM
```

Restart the service:

```bash
systemctl restart lxc_autoscale_ml
```

## Prometheus Metrics

Access Prometheus metrics (no authentication required):

```bash
curl http://localhost:5000/metrics
```

Example metrics:

```
# Scaling actions
lxc_scaling_actions_total{container_id="104",action="scale_up",resource="cpu"} 15

# API requests
lxc_api_requests_total{endpoint="/scale/cores",method="POST",status="200"} 42

# Container resources
lxc_container_cpu_cores{container_id="104"} 4
lxc_container_memory_mb{container_id="104"} 8192
```

## Debug Mode

Enable debug logging for troubleshooting:

Edit `/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml`:

```yaml
logging:
  log_level: "DEBUG"
```

Restart and view detailed logs:

```bash
systemctl restart lxc_autoscale_ml
journalctl -u lxc_autoscale_ml -f
```

## Testing Configuration

### Dry Run Mode

Test scaling decisions without applying changes:

```yaml
scaling:
  dry_run: true
```

The logs show scaling decisions without executing them.

### Validate Configuration

```bash
python3 -c "import yaml; yaml.safe_load(open('/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml'))"
```

If the command produces no output, the YAML is valid.

## Common Tasks

### Reset Metrics History

```bash
echo "[]" > /var/log/lxc_metrics.json
systemctl restart lxc_monitor
```

### Clear Lock File

If the service fails to start due to a stale lock:

```bash
rm /var/lock/lxc_autoscale_ml.lock
systemctl start lxc_autoscale_ml
```

::: tip
Version 2.0 includes automatic stale lock cleanup. Manual removal is rarely needed.
:::

### View Rate Limit Status

Check the rate limit headers in API responses:

```bash
curl -I -H "X-API-Key: YOUR_API_KEY" http://localhost:5000/routes
```

```
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 118
X-RateLimit-Reset: 1703436789
```

## Next Steps

- [Examples](/guide/examples): Automation recipes and cron jobs
- [Troubleshooting](/guide/troubleshooting): Resolve common issues
- [Configuration](/reference/configuration): All configuration options
