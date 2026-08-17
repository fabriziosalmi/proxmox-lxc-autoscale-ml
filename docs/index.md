---
layout: home

hero:
  name: LXC AutoScale ML
  text: Automatic resource scaling for Proxmox LXC containers
  tagline: Collects per-container metrics, learns what normal looks like, and adjusts CPU and memory through the Proxmox CLI
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
  - title: Anomaly-based decisions
    details: An IsolationForest model is trained on each container's own history, so what counts as unusual is learned per container rather than fixed in advance.
  - title: Threshold scaling with limits
    details: Resources move by a configured step at a time, between a floor and a ceiling you set, rather than jumping to either extreme.
  - title: Concurrent config fetching
    details: Container configurations are read in parallel with a bounded concurrency limit, so a cycle does not grow linearly with the number of containers.
  - title: Optional API authentication
    details: API key authentication, per-IP rate limiting and input validation on every endpoint. Authentication is off by default and has to be enabled.
  - title: Circuit breaker
    details: After repeated failures the model stops calling the API for that container for a configurable period, instead of retrying on every cycle.
  - title: Prometheus metrics
    details: The API exports request, scaling and container allocation metrics at /metrics. Only metrics something actually populates are declared.
---

## Quick start

Install on your Proxmox host:

```bash
curl -sSL https://raw.githubusercontent.com/fabriziosalmi/proxmox-lxc-autoscale-ml/main/install.sh | bash
```

Check the three services:

```bash
systemctl status lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

Before letting it act on anything, set `dry_run: true` in
`/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml` and read the log for a few cycles.
It will report the decisions it would have taken without calling the API.

## Requirements

| Requirement | Version |
|-------------|---------|
| Proxmox VE | 8.x (Debian 12). Developed and tested there. |
| Python | 3.10 to 3.12 |
| Operating system | Debian-based Linux |

Proxmox VE 9 ships Python 3.13, which the pinned `numpy`, `pandas` and
`scikit-learn` do not yet support. The API and the monitor run there; the model
does not.

## How it works

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

1. **Monitor** reads CPU, memory, I/O, network and filesystem figures from every
   running container and appends them to a JSON file.
2. **Model** trains an IsolationForest on that history, compares the latest
   sample against configured thresholds, and decides whether to scale.
3. **API** carries the decision out by running `pct` on the host.

The three run as separate systemd services and only share the metrics file.

## Status

See the [changelog](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/blob/main/CHANGELOG.md).
v1.3.0 fixed three defects that each broke the scaling loop end to end, so
versions before it did not autoscale. If you are running one, upgrade.

## License

Released under the [MIT License](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/blob/main/LICENSE).
