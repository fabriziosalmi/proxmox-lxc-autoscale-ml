---
layout: home

hero:
  name: LXC AutoScale ML
  text: ML-Powered Autoscaling for Proxmox
  tagline: Automatically adjust LXC container resources based on real-time usage and machine learning predictions
  image:
    src: /lxc_autoscale_ml.png
    alt: LXC AutoScale ML
  actions:
    - theme: brand
      text: Get Started
      link: /guide/getting-started
    - theme: alt
      text: View on GitHub
      link: https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml

features:
  - icon: 🤖
    title: ML-Driven Autoscaling
    details: Uses IsolationForest anomaly detection to predict resource demands and make intelligent scaling decisions based on historical patterns.
  - icon: ⚡
    title: High Performance
    details: Batch async API client provides 10x faster configuration fetching. Handles 60+ containers with minimal latency.
  - icon: 🔒
    title: Enterprise Security
    details: API key authentication, rate limiting with localhost bypass, and comprehensive input validation on all endpoints.
  - icon: 🛡️
    title: Fault Tolerant
    details: Circuit breaker pattern prevents cascading failures. Automatic recovery from crashes with stale lock cleanup.
  - icon: 📊
    title: Prometheus Metrics
    details: Native metrics export for comprehensive observability. Track scaling actions, API requests, and container resources.
  - icon: 🔧
    title: Incremental Scaling
    details: Gradual resource adjustment prevents instability. Scale by configurable step sizes instead of jumping to extremes.
---

## Quick Start

Install LXC AutoScale ML on your Proxmox host:

```bash
curl -sSL https://raw.githubusercontent.com/fabriziosalmi/proxmox-lxc-autoscale-ml/main/install.sh | bash
```

Check service status:

```bash
systemctl status lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

## System Requirements

| Requirement | Version |
|-------------|---------|
| Proxmox VE | 6.x or higher (tested on 8.2.4) |
| Python | 3.x |
| Operating System | Linux (Debian-based) |

## How It Works

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Monitor   │────▶│    Model    │────▶│     API     │
│  (Metrics)  │     │ (ML Engine) │     │  (Actions)  │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
  Collect CPU,       Train model,        Apply scaling
  RAM, disk,         detect anomalies,   decisions to
  network stats      predict needs       containers
```

1. **Monitor** collects resource metrics from all running LXC containers
2. **Model** trains an IsolationForest model and predicts scaling needs
3. **API** executes scaling actions on the Proxmox host

## License

LXC AutoScale ML is released under the [MIT License](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/blob/main/LICENSE).
