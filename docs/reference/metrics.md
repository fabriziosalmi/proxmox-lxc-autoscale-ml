# Metrics Reference

The API exposes Prometheus metrics at `/metrics`. The endpoint needs no
authentication.

```bash
curl http://proxmox:5000/metrics
```

If `prometheus-client` is not installed the endpoint answers `501` with an
explanatory message rather than failing.

::: tip Everything listed here is populated
Only metrics the API process itself can fill are declared. Earlier releases also
advertised model-prediction, circuit-breaker and container-usage metrics, but
those values live in the ML service and the monitor, which do not serve a
`/metrics` endpoint — so they were exported permanently empty. They will come
back together with an exporter in those processes.
:::

## Request metrics

Recorded for every request, including ones rejected by validation, rate limiting
or authentication.

```
# HELP lxc_autoscale_api_requests_total Total API requests
# TYPE lxc_autoscale_api_requests_total counter
lxc_autoscale_api_requests_total{method="GET",endpoint="/resource/lxc/config",status="200"} 412
lxc_autoscale_api_requests_total{method="POST",endpoint="/scale/cores",status="400"} 3

# HELP lxc_autoscale_api_request_duration_seconds API request duration in seconds
# TYPE lxc_autoscale_api_request_duration_seconds histogram
lxc_autoscale_api_request_duration_seconds_bucket{method="GET",endpoint="/resource/lxc/config",le="0.1"} 380
```

| Label | Values |
|-------|--------|
| `method` | HTTP method |
| `endpoint` | The matched route, e.g. `/resource/lxc/config` |
| `status` | HTTP status code |

::: warning
`endpoint` is the matched route rather than the request path, so a fleet of
containers cannot turn every request into a new time series.
:::

## Scaling metrics

```
# HELP lxc_autoscale_scaling_actions_total Total scaling actions performed
# TYPE lxc_autoscale_scaling_actions_total counter
lxc_autoscale_scaling_actions_total{container_id="104",resource="cpu",action="set"} 27
lxc_autoscale_scaling_actions_total{container_id="104",resource="ram",action="set"} 12

# HELP lxc_autoscale_scaling_failures_total Total scaling action failures
# TYPE lxc_autoscale_scaling_failures_total counter
lxc_autoscale_scaling_failures_total{container_id="105",resource="cpu",reason="unknown"} 2
```

| Label | Values |
|-------|--------|
| `container_id` | LXC container ID |
| `resource` | `cpu`, `ram` or `storage` |
| `action` | `set` or `increase` |
| `reason` | Failure reason, `unknown` when unclassified |

## Container allocation

Updated whenever `/resource/lxc/config` is queried — which the ML service does
once per container per cycle, so these track the fleet automatically.

```
# HELP lxc_autoscale_container_cpu_cores Current CPU cores allocated
# TYPE lxc_autoscale_container_cpu_cores gauge
lxc_autoscale_container_cpu_cores{container_id="104"} 4

# HELP lxc_autoscale_container_memory_mb Current memory allocated in MB
# TYPE lxc_autoscale_container_memory_mb gauge
lxc_autoscale_container_memory_mb{container_id="104"} 4096
```

## Prometheus scrape configuration

```yaml
scrape_configs:
  - job_name: lxc-autoscale-api
    static_configs:
      - targets: ['proxmox:5000']
    scrape_interval: 30s
```

## Useful queries

**Request rate by endpoint:**

```promql
sum by (endpoint) (rate(lxc_autoscale_api_requests_total[5m]))
```

**Error rate:**

```promql
sum(rate(lxc_autoscale_api_requests_total{status=~"5.."}[5m]))
  / sum(rate(lxc_autoscale_api_requests_total[5m]))
```

**95th percentile latency:**

```promql
histogram_quantile(
  0.95,
  sum by (le, endpoint) (rate(lxc_autoscale_api_request_duration_seconds_bucket[5m]))
)
```

**Scaling actions per hour:**

```promql
sum by (resource) (rate(lxc_autoscale_scaling_actions_total[1h])) * 3600
```

**Containers whose scaling keeps failing:**

```promql
sum by (container_id) (rate(lxc_autoscale_scaling_failures_total[15m])) > 0
```

**Total allocated CPU and memory across the fleet:**

```promql
sum(lxc_autoscale_container_cpu_cores)
sum(lxc_autoscale_container_memory_mb)
```

## Alerting examples

```yaml
groups:
  - name: lxc-autoscale
    rules:
      - alert: AutoScaleAPIDown
        expr: up{job="lxc-autoscale-api"} == 0
        for: 5m
        annotations:
          summary: The AutoScale API is not responding

      - alert: ScalingFailures
        expr: sum(rate(lxc_autoscale_scaling_failures_total[15m])) > 0
        for: 15m
        annotations:
          summary: Scaling actions are failing

      - alert: AutoScaleAPIErrors
        expr: |
          sum(rate(lxc_autoscale_api_requests_total{status=~"5.."}[10m]))
            / sum(rate(lxc_autoscale_api_requests_total[10m])) > 0.05
        for: 10m
        annotations:
          summary: More than 5% of API requests are failing

      - alert: AutoScaleAPIUnhealthy
        expr: probe_http_status_code{instance=~".*:5000/health/check"} == 503
        for: 5m
        annotations:
          summary: The API health check reports unhealthy
```

## Health check

`/health/check` is separate from `/metrics` and probes the things the API needs
in order to work at all:

```bash
curl http://proxmox:5000/health/check
```

```json
{
  "status": "healthy",
  "checks": {
    "lxc_commands": { "ok": true, "detail": "ok" }
  }
}
```

It answers `200` when healthy and `503` when any check fails, so it can be used
directly as a systemd or load balancer probe.
