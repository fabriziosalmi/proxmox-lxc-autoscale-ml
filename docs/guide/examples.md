# Examples

This page provides practical examples for automating container management with LXC AutoScale ML.

## Cron Job Examples

### Dynamic CPU Scaling by Time of Day

Increase cores during business hours, reduce after hours:

```bash
# Increase to 8 cores at 8:00 AM
0 8 * * * curl -X POST http://proxmox:5000/scale/cores \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"lxc_id": 104, "cores": 8}'

# Decrease to 4 cores at 8:00 PM
0 20 * * * curl -X POST http://proxmox:5000/scale/cores \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"lxc_id": 104, "cores": 4}'
```

### Automated Memory Management

Adjust RAM based on workload patterns:

```bash
# Increase RAM at 9:00 AM
0 9 * * * curl -X POST http://proxmox:5000/scale/ram \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"lxc_id": 104, "memory": 8192}'

# Decrease RAM at 7:00 PM
0 19 * * * curl -X POST http://proxmox:5000/scale/ram \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"lxc_id": 104, "memory": 4096}'
```

### Daily Snapshot Creation

Create a snapshot at 6:00 AM daily:

```bash
0 6 * * * curl -X POST http://proxmox:5000/snapshot/create \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"lxc_id": 104, "snapshot_name": "daily_backup_'$(date +\%Y\%m\%d)'"}'
```

### Resource Monitoring and Logging

Log container status every hour:

```bash
0 * * * * curl -H "X-API-Key: YOUR_API_KEY" \
  "http://proxmox:5000/resource/lxc/status?lxc_id=104" \
  >> /var/log/container_104_status.log
```

Log node status every 5 minutes:

```bash
*/5 * * * * curl -H "X-API-Key: YOUR_API_KEY" \
  "http://proxmox:5000/resource/node/status?node_name=proxmox" \
  >> /var/log/node_status.log
```

### Automated Health Checks

Perform health check every 5 minutes:

```bash
*/5 * * * * curl -s http://proxmox:5000/health/check \
  || systemctl restart lxc_autoscale_api
```

## Shell Script Examples

### Batch Scale Multiple Containers

```bash
#!/bin/bash
# scale_containers.sh - Scale multiple containers to specified resources

API_KEY="your-api-key"
API_URL="http://localhost:5000"
CONTAINERS=(101 102 103 104 105)
CORES=4
MEMORY=4096

for VMID in "${CONTAINERS[@]}"; do
  echo "Scaling container $VMID..."

  curl -s -X POST "$API_URL/scale/cores" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "{\"lxc_id\": $VMID, \"cores\": $CORES}"

  curl -s -X POST "$API_URL/scale/ram" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "{\"lxc_id\": $VMID, \"memory\": $MEMORY}"

  echo "Container $VMID scaled to $CORES cores and $MEMORY MB RAM"
done
```

### Container Resource Report

```bash
#!/bin/bash
# container_report.sh - Generate resource usage report

API_KEY="your-api-key"
API_URL="http://localhost:5000"

echo "=== Container Resource Report ==="
echo "Generated: $(date)"
echo ""

# Get list of container IDs from Proxmox
for VMID in $(pct list | tail -n +2 | awk '{print $1}'); do
  RESPONSE=$(curl -s -H "X-API-Key: $API_KEY" \
    "$API_URL/resource/lxc/status?lxc_id=$VMID")

  if echo "$RESPONSE" | jq -e '.status == "success"' > /dev/null 2>&1; then
    NAME=$(pct config $VMID | grep hostname | awk '{print $2}')
    CPU=$(echo "$RESPONSE" | jq -r '.data.cpu // "N/A"')
    MEM=$(echo "$RESPONSE" | jq -r '.data.memory // "N/A"')

    printf "%-6s %-20s CPU: %-5s MEM: %s\n" "$VMID" "$NAME" "$CPU" "$MEM"
  fi
done
```

### Pre-Deployment Snapshot and Scale

```bash
#!/bin/bash
# deploy_prep.sh - Prepare container for deployment

API_KEY="your-api-key"
API_URL="http://localhost:5000"
VMID=$1
SNAPSHOT_NAME="pre_deploy_$(date +%Y%m%d_%H%M%S)"

if [ -z "$VMID" ]; then
  echo "Usage: $0 <lxc_id>"
  exit 1
fi

echo "Creating snapshot: $SNAPSHOT_NAME"
curl -s -X POST "$API_URL/snapshot/create" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{\"lxc_id\": $VMID, \"snapshot_name\": \"$SNAPSHOT_NAME\"}"

echo "Scaling up resources for deployment..."
curl -s -X POST "$API_URL/scale/cores" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{\"lxc_id\": $VMID, \"cores\": 8}"

curl -s -X POST "$API_URL/scale/ram" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{\"lxc_id\": $VMID, \"memory\": 16384}"

echo "Container $VMID ready for deployment"
echo "Rollback snapshot: $SNAPSHOT_NAME"
```

### Snapshot Cleanup Script

```bash
#!/bin/bash
# cleanup_snapshots.sh - Remove snapshots older than 7 days

API_KEY="your-api-key"
API_URL="http://localhost:5000"
VMID=$1
DAYS_OLD=7

if [ -z "$VMID" ]; then
  echo "Usage: $0 <lxc_id>"
  exit 1
fi

CUTOFF=$(date -d "$DAYS_OLD days ago" +%Y%m%d)

echo "Cleaning snapshots older than $DAYS_OLD days for container $VMID"

SNAPSHOTS=$(curl -s -H "X-API-Key: $API_KEY" \
  "$API_URL/snapshot/list?lxc_id=$VMID" | jq -r '.data[]?.name // empty')

for SNAP in $SNAPSHOTS; do
  # Extract date from snapshot name (assumes format: name_YYYYMMDD)
  SNAP_DATE=$(echo "$SNAP" | grep -oE '[0-9]{8}' | tail -1)

  if [ -n "$SNAP_DATE" ] && [ "$SNAP_DATE" -lt "$CUTOFF" ]; then
    echo "Removing old snapshot: $SNAP"
    # Note: Add snapshot delete endpoint call here when available
  fi
done
```

## Prometheus and Grafana Integration

### Prometheus Configuration

Add to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'lxc_autoscale'
    static_configs:
      - targets: ['proxmox:5000']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

### Useful PromQL Queries

**Scaling rate per hour, by resource:**

```promql
sum by (resource) (rate(lxc_autoscale_scaling_actions_total[1h])) * 3600
```

The `action` label is `set` for CPU and RAM and `increase` for storage; direction
is not recorded, so scale-up and scale-down cannot be told apart here. The
decision itself is in the model's log.

**Average API response time:**

```promql
rate(lxc_autoscale_api_request_duration_seconds_sum[5m])
/
rate(lxc_autoscale_api_request_duration_seconds_count[5m])
```

**Containers whose scaling keeps failing:**

```promql
sum by (container_id) (rate(lxc_autoscale_scaling_failures_total[15m])) > 0
```

**Total resources allocated across the fleet:**

```promql
sum(lxc_autoscale_container_cpu_cores)
sum(lxc_autoscale_container_memory_mb)
```

Container *usage* is not exported here: it is collected by the monitor, which
has no metrics endpoint. It is in `/var/log/lxc_metrics.json`.

## Alerting Examples

### Alertmanager Configuration

```yaml
groups:
  - name: lxc_autoscale
    rules:
      - alert: HighScalingRate
        expr: sum(rate(lxc_autoscale_scaling_actions_total[1h])) * 3600 > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High scaling activity detected"
          description: "More than 10 scaling actions per hour"

      - alert: AutoScaleAPIDown
        expr: up{job="lxc-autoscale-api"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "The AutoScale API is not responding"
          description: "API failures detected, circuit breaker is open"

      - alert: APIHighLatency
        expr: rate(lxc_autoscale_api_request_duration_seconds_sum[5m]) / rate(lxc_autoscale_api_request_duration_seconds_count[5m]) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High API latency"
          description: "Average API response time exceeds 1 second"
```

## Clone and Test Workflow

```bash
#!/bin/bash
# test_clone.sh - Create test clone, run tests, cleanup

API_KEY="your-api-key"
API_URL="http://localhost:5000"
SOURCE_VMID=$1
TEST_VMID=$((SOURCE_VMID + 1000))

if [ -z "$SOURCE_VMID" ]; then
  echo "Usage: $0 <source_lxc_id>"
  exit 1
fi

echo "Creating test clone..."
curl -s -X POST "$API_URL/clone/create" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{\"lxc_id\": $SOURCE_VMID, \"new_lxc_id\": $TEST_VMID, \"new_lxc_name\": \"test_clone\"}"

echo "Waiting for clone to be ready..."
sleep 30

echo "Run your tests here..."
# Add test commands

echo "Cleaning up test clone..."
curl -s -X DELETE "$API_URL/clone/delete" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{\"lxc_id\": $TEST_VMID}"

echo "Test workflow complete"
```

## Next Steps

- [Troubleshooting](/guide/troubleshooting): Resolve common issues
- [API Endpoints](/reference/api-endpoints): Complete API reference
- [Configuration](/reference/configuration): All configuration options
