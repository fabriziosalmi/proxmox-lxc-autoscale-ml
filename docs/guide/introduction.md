# What is LXC AutoScale ML?

LXC AutoScale ML adjusts the CPU and memory allocated to Proxmox LXC
containers. It collects per-container metrics, trains an anomaly detection model
on each container's own history, and applies changes by running `pct` on the
host. Resizing CPU and memory with `pct set` does not restart the container.

## Key Features

### ML-Driven Autoscaling

The system uses an IsolationForest machine learning model to detect anomalies in resource usage patterns. When unusual activity is detected, the model evaluates whether scaling is needed based on:

- Current CPU and memory utilization
- Historical usage trends
- Configured thresholds and limits

### Incremental Scaling

Resources scale gradually to avoid instability:

- **CPU**: Adjusts by ±1 core per cycle (configurable)
- **RAM**: Adjusts by ±512 MB per cycle (configurable)

This prevents the system from jumping between minimum and maximum allocations.

### Concurrent configuration fetching

Before deciding, the model reads each container's current allocation from the
API. Those reads are issued concurrently, up to `api.max_concurrent` at a time
(10 by default), so a cycle does not grow linearly with the number of
containers. How much that saves depends on how quickly the API answers, which
depends on how quickly `pct config` returns on your host.

### Security

- **API key authentication**, off by default. When enabled, every endpoint
  except `/health/check` and `/metrics` requires a key, compared in constant
  time.
- **Per-IP rate limiting**, 120 requests per minute by default, with localhost
  exempt so the model is not throttled.
- **Input validation** on every parameter. Commands are handed to the kernel as
  argument lists and never go through a shell.

The API runs as root, because `pct` requires it, and binds to every interface by
default. See [Configuration](/reference/configuration) before exposing it.

### Fault Tolerance

The circuit breaker pattern automatically skips failed API endpoints, preventing cascading failures. The system recovers gracefully from crashes through automatic stale lock cleanup.

## Architecture Overview

LXC AutoScale ML consists of three main components:

| Component | Purpose | Service Name |
|-----------|---------|--------------|
| **API** | RESTful interface for scaling operations | `lxc_autoscale_api` |
| **Monitor** | Collects resource metrics from containers | `lxc_monitor` |
| **Model** | ML engine for scaling decisions | `lxc_autoscale_ml` |

### Data Flow

```
LXC Containers
      │
      ▼ (metrics collection)
┌─────────────┐
│   Monitor   │──▶ /var/log/lxc_metrics.json
└─────────────┘
      │
      ▼ (read metrics)
┌─────────────┐
│    Model    │──▶ Train IsolationForest
└─────────────┘    Detect anomalies
      │            Predict scaling needs
      ▼ (API calls)
┌─────────────┐
│     API     │──▶ Apply scaling actions
└─────────────┘
      │
      ▼
LXC Containers (scaled)
```

## Use Cases

### Dynamic Web Applications

Scale container resources during peak traffic hours and reduce them during off-peak periods.

### Development Environments

Automatically adjust resources based on build activity and test workloads.

### Database Servers

Respond to query load variations by scaling memory and CPU as needed.

### Batch Processing

Increase resources when batch jobs run and scale down after completion.

## Comparison with Manual Scaling

| Aspect | Manual Scaling | LXC AutoScale ML |
|--------|----------------|------------------|
| Response time | Minutes to hours | Seconds |
| Accuracy | Based on estimates | Based on real data |
| Consistency | Human-dependent | Automated |
| Overnight coverage | Requires on-call staff | Continuous |
| Resource efficiency | Often over-provisioned | Optimized |

## Next Steps

- [Getting Started](/guide/getting-started): Install and configure LXC AutoScale ML
- [Architecture](/guide/architecture): Understand the system design
- [Configuration](/reference/configuration): Customize scaling behavior
