# Prometheus Metrics Reference

LXC AutoScale ML exports Prometheus-compatible metrics at the `/metrics` endpoint.

## Accessing Metrics

```bash
curl http://localhost:5000/metrics
```

No authentication required.

## Available Metrics

### Scaling Actions

Track scaling operations performed by the system.

```
# HELP lxc_scaling_actions_total Total number of scaling actions
# TYPE lxc_scaling_actions_total counter
lxc_scaling_actions_total{container_id="104",action="scale_up",resource="cpu"} 15
lxc_scaling_actions_total{container_id="104",action="scale_down",resource="ram"} 8
lxc_scaling_actions_total{container_id="105",action="scale_up",resource="ram"} 3
```

**Labels:**

| Label | Values |
|-------|--------|
| `container_id` | LXC container ID |
| `action` | `scale_up`, `scale_down` |
| `resource` | `cpu`, `ram` |

### API Requests

Track API request counts and latency.

```
# HELP lxc_api_requests_total Total API requests
# TYPE lxc_api_requests_total counter
lxc_api_requests_total{endpoint="/scale/cores",method="POST",status="200"} 42
lxc_api_requests_total{endpoint="/scale/ram",method="POST",status="200"} 38
lxc_api_requests_total{endpoint="/health/check",method="GET",status="200"} 1250

# HELP lxc_api_request_duration_seconds API request duration
# TYPE lxc_api_request_duration_seconds histogram
lxc_api_request_duration_seconds_bucket{endpoint="/scale/cores",le="0.1"} 35
lxc_api_request_duration_seconds_bucket{endpoint="/scale/cores",le="0.5"} 42
lxc_api_request_duration_seconds_sum{endpoint="/scale/cores"} 5.25
lxc_api_request_duration_seconds_count{endpoint="/scale/cores"} 42
```

**Labels:**

| Label | Values |
|-------|--------|
| `endpoint` | API endpoint path |
| `method` | HTTP method |
| `status` | HTTP status code |

### Container Resources

Current resource allocation for containers.

```
# HELP lxc_container_cpu_cores CPU cores allocated
# TYPE lxc_container_cpu_cores gauge
lxc_container_cpu_cores{container_id="104"} 4
lxc_container_cpu_cores{container_id="105"} 2

# HELP lxc_container_memory_mb Memory allocated in MB
# TYPE lxc_container_memory_mb gauge
lxc_container_memory_mb{container_id="104"} 8192
lxc_container_memory_mb{container_id="105"} 4096

# HELP lxc_container_cpu_usage_percent CPU usage percentage
# TYPE lxc_container_cpu_usage_percent gauge
lxc_container_cpu_usage_percent{container_id="104"} 65.2

# HELP lxc_container_memory_usage_percent Memory usage percentage
# TYPE lxc_container_memory_usage_percent gauge
lxc_container_memory_usage_percent{container_id="104"} 78.5
```

**Labels:**

| Label | Values |
|-------|--------|
| `container_id` | LXC container ID |

### Circuit Breaker

Circuit breaker status for fault tolerance.

```
# HELP lxc_circuit_breaker_state Circuit breaker state (0=closed, 1=open)
# TYPE lxc_circuit_breaker_state gauge
lxc_circuit_breaker_state{endpoint="api_104"} 0
lxc_circuit_breaker_state{endpoint="api_105"} 1

# HELP lxc_circuit_breaker_failures Consecutive failures
# TYPE lxc_circuit_breaker_failures gauge
lxc_circuit_breaker_failures{endpoint="api_104"} 2
lxc_circuit_breaker_failures{endpoint="api_105"} 5
```

**Values:**

| State | Meaning |
|-------|---------|
| `0` | Closed (normal operation) |
| `1` | Open (requests blocked) |

### Model Predictions

ML model prediction counts.

```
# HELP lxc_model_predictions_total Total model predictions
# TYPE lxc_model_predictions_total counter
lxc_model_predictions_total{container_id="104",prediction="normal"} 120
lxc_model_predictions_total{container_id="104",prediction="anomaly"} 15
lxc_model_predictions_total{container_id="105",prediction="normal"} 118
lxc_model_predictions_total{container_id="105",prediction="anomaly"} 5
```

**Labels:**

| Label | Values |
|-------|--------|
| `container_id` | LXC container ID |
| `prediction` | `normal`, `anomaly` |

## Prometheus Configuration

Add to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'lxc_autoscale'
    static_configs:
      - targets: ['proxmox:5000']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

## Useful PromQL Queries

### Scaling Rate

**Scaling actions per hour:**

```promql
rate(lxc_scaling_actions_total[1h]) * 3600
```

**Scale up vs scale down ratio:**

```promql
sum(lxc_scaling_actions_total{action="scale_up"})
/
sum(lxc_scaling_actions_total{action="scale_down"})
```

### API Performance

**Average response time:**

```promql
rate(lxc_api_request_duration_seconds_sum[5m])
/
rate(lxc_api_request_duration_seconds_count[5m])
```

**Request rate per endpoint:**

```promql
rate(lxc_api_requests_total[5m])
```

**Error rate:**

```promql
sum(rate(lxc_api_requests_total{status=~"4..|5.."}[5m]))
/
sum(rate(lxc_api_requests_total[5m]))
```

### Resource Usage

**Containers with high CPU:**

```promql
lxc_container_cpu_usage_percent > 80
```

**Containers with high memory:**

```promql
lxc_container_memory_usage_percent > 90
```

**Total allocated CPU cores:**

```promql
sum(lxc_container_cpu_cores)
```

**Total allocated memory:**

```promql
sum(lxc_container_memory_mb)
```

### Circuit Breaker

**Open circuit breakers:**

```promql
count(lxc_circuit_breaker_state == 1)
```

**Containers with failed circuits:**

```promql
lxc_circuit_breaker_state == 1
```

### Model Predictions

**Anomaly rate per container:**

```promql
rate(lxc_model_predictions_total{prediction="anomaly"}[1h])
```

**Anomaly percentage:**

```promql
sum(lxc_model_predictions_total{prediction="anomaly"})
/
sum(lxc_model_predictions_total)
* 100
```

## Grafana Dashboard

### Example Panel Queries

**Scaling Activity (Graph):**

```promql
sum by (action, resource) (rate(lxc_scaling_actions_total[5m]))
```

**Container Resource Allocation (Table):**

```promql
lxc_container_cpu_cores
lxc_container_memory_mb
```

**API Latency (Heatmap):**

```promql
rate(lxc_api_request_duration_seconds_bucket[5m])
```

## Alerting Examples

### Alertmanager Rules

```yaml
groups:
  - name: lxc_autoscale_alerts
    rules:
      - alert: HighScalingRate
        expr: rate(lxc_scaling_actions_total[1h]) * 3600 > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High scaling activity"
          description: "More than 10 scaling actions per hour"

      - alert: CircuitBreakerOpen
        expr: lxc_circuit_breaker_state == 1
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Circuit breaker open"
          description: "Container {{ $labels.endpoint }} circuit breaker is open"

      - alert: HighAnomalyRate
        expr: >
          sum(rate(lxc_model_predictions_total{prediction="anomaly"}[1h]))
          /
          sum(rate(lxc_model_predictions_total[1h]))
          > 0.3
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High anomaly detection rate"
          description: "More than 30% of predictions are anomalies"

      - alert: APIHighLatency
        expr: >
          rate(lxc_api_request_duration_seconds_sum[5m])
          /
          rate(lxc_api_request_duration_seconds_count[5m])
          > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High API latency"
          description: "Average response time exceeds 1 second"
```

## Metrics Availability

Metrics are available only when `prometheus-client` is installed:

```bash
apt install python3-prometheus-client
# or
pip3 install prometheus-client
```

If not installed, the `/metrics` endpoint returns a message indicating Prometheus metrics are unavailable.
