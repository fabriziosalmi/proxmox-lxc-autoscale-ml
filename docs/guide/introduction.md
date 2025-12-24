# What is LXC AutoScale ML?

LXC AutoScale ML is a resource management daemon for Proxmox environments. It monitors LXC container resource usage and automatically adjusts CPU and memory allocations with zero downtime, using machine learning to predict resource demands.

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

### High-Performance Architecture

The batch async API client fetches container configurations concurrently, providing **10x faster** performance compared to sequential requests. A deployment with 60 containers completes configuration fetching in approximately 0.6 seconds.

### Enterprise Security

- **API Key Authentication**: All sensitive endpoints require authentication
- **Rate Limiting**: 120 requests per minute with automatic localhost bypass
- **Input Validation**: Comprehensive parameter validation prevents injection attacks

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
