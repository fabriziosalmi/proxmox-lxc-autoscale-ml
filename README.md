# LXC AutoScale ML

**LXC AutoScale ML** adjusts the CPU and memory allocated to Proxmox LXC
containers. It collects per-container metrics, trains an anomaly detection model
on each container's own history, and applies changes through `pct` on the host.
Resizing CPU and memory with `pct set` does not restart the container.

Three systemd services, sharing nothing but a metrics file on disk.

**Developed and tested on Proxmox VE 8 (Debian 12).**

![Platform](https://img.shields.io/badge/platform-Proxmox%20VE%208-green) ![Python Version](https://img.shields.io/badge/python-3.10--3.12-blue) ![License](https://img.shields.io/badge/license-MIT-blue)

![LXC AutoScale ML Architecture](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/blob/main/docs/lxc_autoscale_ml.png?raw=true)

**Example output** (a scaling cycle, from the actual log format strings):
```
2026-08-18 13:07:56,393 [INFO] Data loaded successfully from /var/log/lxc_metrics.json.
2026-08-18 13:07:56,399 [INFO] Data preprocessed successfully.
2026-08-18 13:07:56,416 [INFO] Feature engineering, spike detection, and trend detection completed.
2026-08-18 13:07:56,549 [INFO] IsolationForest model training completed.
2026-08-18 13:07:56,549 [INFO] Processing containers for scaling decisions...
2026-08-18 13:07:56,551 [INFO] Batch fetching configs for 12 containers...
2026-08-18 13:07:56,974 [INFO] Batch fetch completed in 0.42s: 12/12 successful (28.6 containers/sec)
2026-08-18 13:07:56,600 [INFO] Applying scaling actions for container 104: CPU - Scale Up, RAM - No Scaling | Confidence: 87.41%
2026-08-18 13:07:57,257 [INFO] Successfully scaled CPU for LXC ID 104 to 4 CPU units.
2026-08-18 13:07:57,300 [INFO] No scaling needed for container 105. | Confidence: 12.80%
2026-08-18 13:07:57,916 [INFO] Sleeping for 600 seconds before the next run.
```

With `scaling.dry_run: true`, the action line reads instead:

```
2026-08-18 13:07:56,600 [INFO] [dry_run] Would scale container 104: CPU - Scale Up (-> 4), RAM - No Scaling (-> None) | Confidence: 87.41%
```

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Components Overview](#components-overview)
- [Usage and Control](#usage-and-control)
- [Monitoring and Alerts](#monitoring-and-alerts)
- [Documentation](#documentation)
- [Uninstallation](#uninstallation)
- [Contributing](#contributing)
- [License](#license)

## Overview

A monitor writes container metrics to a JSON file, a model reads that file and
decides whether anything should change, and an API carries the decision out by
running `pct`. Each runs as its own systemd service.

### What it does

- **Learns per container.** An IsolationForest is trained on each container's
  own history, so "unusual" is relative to that container rather than a fixed
  rule.
- **Moves in steps, within limits.** Scaling adds or removes one configured
  step at a time, between a floor and a ceiling you set.
- **Fetches configurations concurrently**, with a bounded concurrency limit, so
  a cycle does not grow linearly with the number of containers.
- **Backs off from a failing API.** After repeated failures a circuit breaker
  stops calling it for that container until a timeout expires.
- **Can rehearse.** `dry_run: true` logs the decision it would have taken and
  calls nothing.
- **Exports Prometheus metrics** at `/metrics` — request, scaling and container
  allocation series.
- **Optional API authentication**: API keys, per-IP rate limiting and input
  validation on every endpoint. Authentication is off by default.

### What it does not do

- It does not resize disks automatically; `/scale/storage/increase` exists but
  nothing calls it on its own.
- It does not migrate containers between nodes.
- Per-container I/O statistics come from `/proc/diskstats`, which is not
  namespaced, so they reflect the host's disks rather than the container's.

## System Requirements

- **Proxmox host**: VE 8 (Debian 12). Developed and tested there.
- **Operating system**: Debian-based Linux
- **Python**: 3.10 to 3.12. Proxmox VE 9 ships 3.13, which the pinned
  `numpy`, `pandas` and `scikit-learn` do not yet support — the API and the
  monitor run there, the model does not.
- **Dependencies**:
  ```bash
  git, python3-flask, python3-requests, python3-sklearn, python3-pandas, 
  python3-numpy, python3-aiofiles, python3-yaml, python3-psutil, 
  python3-aiohttp, python3-prometheus-client (optional)
  ```

> **Note**: All dependencies are automatically installed by the installation script and listed in `requirements.txt`.

## Installation

To install **LXC AutoScale ML**, execute the following command:

```bash
curl -sSL https://raw.githubusercontent.com/fabriziosalmi/proxmox-lxc-autoscale-ml/main/install.sh | bash
```

### Prerequisites

- **Root or Sudo Privileges**: Ensure the command is executed with appropriate privileges.
- **Internet Access**: Required on the Proxmox server for downloading files and packages.

**The installation script will:**

1. **Verify System Requirements**: Ensures all necessary packages and dependencies are present.
2. **Download & Set Up**: Retrieves the required files and configures services.
3. **Enable Services**: Starts the API, monitoring, and ML model services.

> [!IMPORTANT]
> You need to check your `/lib/systemd/system/lxcfs.service` file for the presence of the `-l` option which makes `loadavg` retrieval working as expected. Here the required configuration:
>
> ```
> [Unit]
> Description=FUSE filesystem for LXC
> ConditionVirtualization=!container
> Before=lxc.service
> Documentation=man:lxcfs(1)
> 
> [Service]
> OOMScoreAdjust=-1000
> ExecStartPre=/bin/mkdir -p /var/lib/lxcfs
> # ExecStart=/usr/bin/lxcfs /var/lib/lxcfs
> ExecStart=/usr/bin/lxcfs /var/lib/lxcfs -l
> KillMode=process
> Restart=on-failure
> ExecStopPost=-/bin/fusermount -u /var/lib/lxcfs
> Delegate=yes
> ExecReload=/bin/kill -USR1 $MAINPID
>
> [Install]
> WantedBy=multi-user.target
> ```
> 
> Just update the `/lib/systemd/system/lxcfs.service` file, execute `systemctl daemon-reload && systemctl restart lxcfs` and when you are ready to apply the fix restart the LXC containers.
> 
> _Tnx to No-Pen9082 to point me out to that. [Here](https://forum.proxmox.com/threads/lxc-containers-shows-hosts-load-average.45724/page-2) the Proxmox forum thread on the topic._


## Components Overview

### 1. API Component

An HTTP interface over the `pct` command line. It runs as root under gunicorn,
because `pct` requires it.

- **Scaling, snapshot and clone operations**, each validated before a command is
  built. Commands are passed to the kernel as argument lists, never through a
  shell.
- **API key authentication**, off by default, exempting `/health/check` and
  `/metrics`. Keys are compared in constant time.
- **Per-IP rate limiting**, 120 requests per minute by default, with localhost
  exempt so the model is not throttled.
- **Prometheus metrics** at `/metrics`: request counts and durations, scaling
  actions and failures, and per-container CPU and memory allocation.
- **A health check that can fail.** `/health/check` probes `pct` and the
  configured node, and returns 503 when either is broken.

#### API Endpoints

| Endpoint                   | Methods | Description                                             | Example                                                                                   |
|----------------------------|---------|---------------------------------------------------------|-------------------------------------------------------------------------------------------|
| `/scale/cores`             | POST    | Set the exact number of CPU cores for an LXC container.  | `curl -X POST http://proxmox:5000/scale/cores -H "Content-Type: application/json" -d '{"lxc_id": 104, "cores": 4}'` |
| `/scale/ram`               | POST    | Set the exact amount of RAM for an LXC container.        | `curl -X POST http://proxmox:5000/scale/ram -H "Content-Type: application/json" -d '{"lxc_id": 104, "memory": 4096}'` |
| `/scale/storage/increase`  | POST    | Increase the storage size of an LXC container's root filesystem. | `curl -X POST http://proxmox:5000/scale/storage/increase -H "Content-Type: application/json" -d '{"lxc_id": 104, "disk_size": 2}'` |
| `/snapshot/create`         | POST    | Create a snapshot for an LXC container.                  | `curl -X POST http://proxmox:5000/snapshot/create -H "Content-Type: application/json" -d '{"lxc_id": 104, "snapshot_name": "my_snapshot"}'` |
| `/snapshot/list`           | GET     | List all snapshots for an LXC container.                 | `curl -X GET "http://proxmox:5000/snapshot/list?lxc_id=104"`                               |
| `/snapshot/rollback`       | POST    | Rollback to a specific snapshot.                        | `curl -X POST http://proxmox:5000/snapshot/rollback -H "Content-Type: application/json" -d '{"lxc_id": 104, "snapshot_name": "my_snapshot"}'` |
| `/clone/create`            | POST    | Clone an LXC container.                                  | `curl -X POST http://proxmox:5000/clone/create -H "Content-Type: application/json" -d '{"lxc_id": 104, "new_lxc_id": 105, "new_lxc_name": "cloned_container"}'` |
| `/clone/delete`            | DELETE  | Delete a cloned LXC container.                           | `curl -X DELETE http://proxmox:5000/clone/delete -H "Content-Type: application/json" -d '{"lxc_id": 105}'` |
| `/resource/lxc/status`      | GET     | Check the resource allocation and usage for an LXC container. | `curl -X GET "http://proxmox:5000/resource/lxc/status?lxc_id=104"`                        |
| `/resource/lxc/config`      | GET     | Get the current CPU and RAM allocation of an LXC container. | `curl -X GET "http://proxmox:5000/resource/lxc/config?lxc_id=104"`                        |
| `/resource/node/status`    | GET     | Check the resource usage of a specific node.             | `curl -X GET "http://proxmox:5000/resource/node/status?node_name=proxmox"`                |
| `/resource/cluster/status` | GET     | Check the status of the Proxmox cluster.                 | `curl -X GET http://proxmox:5000/resource/cluster/status`                                 |
| `/health/check`            | GET     | Perform a health check on the API server.                | `curl -X GET http://proxmox:5000/health/check`                                            |
| `/metrics`                 | GET     | Export Prometheus metrics for monitoring.                | `curl -X GET http://proxmox:5000/metrics`                                                 |
| `/routes`                  | GET     | List all available routes.                               | `curl -X GET http://proxmox:5000/routes`                                                  |

> **Naming**: container IDs are `lxc_id` and the resource paths are
> `/resource/lxc/*`. The older `vm_id` and `/resource/vm/*` spellings are
> deprecated but still accepted, so existing scripts keep working.
> Every endpoint takes its parameters from a JSON body or the query string.

> **Security**: authentication is **off** in the shipped configuration and the
> API binds to every interface, so out of the box anything that can reach port
> 5000 can resize, snapshot and destroy containers — as root. Set
> `server.host: 127.0.0.1` unless the model runs on another host; if it does,
> enable `authentication`, set a matching `api.api_key` in the model config, and
> put TLS in front. See [Configuration](docs/reference/configuration.md).
>
> Authentication is by the `X-API-Key` header only. The `?api_key=` form was
> removed in 1.4.0 because it wrote the key into the access log.

### 2. Monitor Component

Reads figures out of each running container and appends them to a JSON file. It
makes no decisions; it only records.

- **Per-container CPU, memory, swap, process count, I/O, network and filesystem
  usage**, gathered with `pct exec`.
- **CPU as usage over the interval**, computed by differencing two `/proc/stat`
  readings. A single reading would give the container's average since boot.
- **Concurrent collection** across containers, with a per-probe retry. One
  unreachable container does not cost the cycle.
- **A bounded file**: the newest 1000 cycles are kept, written through a
  temporary file and renamed into place so a crash cannot truncate it.

Note that `/proc/diskstats` is not namespaced, so the I/O figures reflect the
host's disks rather than the container's.

### 3. Model Component

Reads the metrics file, decides what should change, and asks the API to do it.

- **IsolationForest**, retrained each cycle on the full history in the file, to
  flag samples that are unusual for that container.
- **Threshold comparison** against the latest sample decides the direction;
  resources then move by one configured step, bounded by a floor and a ceiling.
- **`min_confidence`** can require the prediction to sit a given distance from
  the model's decision boundary before anything is applied. Confidence is that
  distance mapped onto 0-100, not a probability.
- **Concurrent configuration fetches** with a bounded concurrency limit and
  exponential backoff on server errors.
- **A circuit breaker** that stops calling the API for a container after
  repeated failures until a timeout expires.
- **`dry_run`** logs the decision it would have taken and calls nothing.
- **A single-instance lock** created with `O_EXCL`, with stale locks from a
  crashed process detected by PID and reclaimed.

It reacts to the newest sample rather than forecasting future demand, and
IsolationForest is the only model it supports.

## Usage and Control

Manage the autoscaling services with the following commands:

- **Check Status**:
  ```bash
  systemctl status lxc_autoscale_api.service
  systemctl status lxc_monitor.service
  systemctl status lxc_autoscale_ml.service
  ```

- **Start/Stop Services**:
  ```bash
  systemctl start lxc_autoscale_api.service
  systemctl stop lxc_monitor.service
  systemctl restart lxc_autoscale_ml.service
  ```

### Monitoring and Alerts

- **Prometheus Metrics**: Native Prometheus metrics export at `/metrics` endpoint
  - Scaling actions counter
  - Request counts and durations, labelled by the matched route
  - Scaling actions and failures, by container and resource
  - Per-container CPU and memory allocation
- **Alerting**: see the [metrics reference](docs/reference/metrics.md) for
  worked alert rules.
- **Batch fetch timing** is logged each cycle (`Batch fetch completed in ...`).

#### Example Prometheus queries

```promql
# Scaling actions per hour, by resource
sum by (resource) (rate(lxc_autoscale_scaling_actions_total[1h])) * 3600

# Containers whose scaling keeps failing
sum by (container_id) (rate(lxc_autoscale_scaling_failures_total[15m])) > 0

# Average API response time
rate(lxc_autoscale_api_request_duration_seconds_sum[5m])
  / rate(lxc_autoscale_api_request_duration_seconds_count[5m])

# Total CPU and memory allocated across the fleet
sum(lxc_autoscale_container_cpu_cores)
sum(lxc_autoscale_container_memory_mb)
```

## Documentation

Full documentation is on the [documentation site](./docs/), or build it locally:

```bash
cd docs
npm install
npm run dev
```

### Quick Links

| Section | Description |
|---------|-------------|
| [Getting Started](./docs/guide/getting-started.md) | Installation and initial setup |
| [Architecture](./docs/guide/architecture.md) | System design and data flow |
| [Configuration](./docs/reference/configuration.md) | All configuration options |
| [API Reference](./docs/reference/api-endpoints.md) | Complete API documentation |
| [Troubleshooting](./docs/guide/troubleshooting.md) | Common issues and solutions |
| [Changelog](./CHANGELOG.md) | Version history |

### Component Documentation

| Component | Description |
|-----------|-------------|
| [API](./docs/components/api.md) | RESTful interface for scaling operations |
| [Model](./docs/components/model.md) | ML engine and scaling logic |
| [Monitor](./docs/components/monitor.md) | Metrics collection service |

## Uninstallation

To uninstall **LXC AutoScale ML**, execute the following command:

```bash
curl -sSL https://raw.githubusercontent.com/fabriziosalmi/proxmox-lxc-autoscale-ml/main/uninstall.sh | bash
```

> [!WARNING]
> The uninstallation script will remove all related files and configurations.
> Ensure to back up any important data before proceeding.

## Contributing

We welcome contributions! Please follow these steps:

1. **Fork** the repository.
2. **Create** a new branch (`git checkout -b feature/your-feature`).
3. **Commit** your changes (`git commit -m 'Add your feature'`).
4. **Push** to the branch (`git push origin feature/your-feature`).
5. Open a **Pull Request**.

## Others projects

If You like my projects, you may also like these ones:

- [caddy-waf](https://github.com/fabriziosalmi/caddy-waf) Caddy WAF (Regex Rules, IP and DNS filtering, Rate Limiting, GeoIP, Tor, Anomaly Detection) 
- [patterns](https://github.com/fabriziosalmi/patterns) Automated OWASP CRS and Bad Bot Detection for Nginx, Apache, Traefik and HaProxy
- [blacklists](https://github.com/fabriziosalmi/blacklists) Hourly updated domains blacklist 
- [proxmox-vm-autoscale](https://github.com/fabriziosalmi/proxmox-vm-autoscale) Automatically scale virtual machines resources on Proxmox hosts 
- [UglyFeed](https://github.com/fabriziosalmi/UglyFeed) Retrieve, aggregate, filter, evaluate, rewrite and serve RSS feeds using Large Language Models for fun, research and learning purposes 
- [proxmox-lxc-autoscale](https://github.com/fabriziosalmi/proxmox-lxc-autoscale) Automatically scale LXC containers resources on Proxmox hosts 
- [DevGPT](https://github.com/fabriziosalmi/DevGPT) Code togheter, right now! GPT powered code assistant to build project in minutes
- [websites-monitor](https://github.com/fabriziosalmi/websites-monitor) Websites monitoring via GitHub Actions (expiration, security, performances, privacy, SEO)
- [caddy-mib](https://github.com/fabriziosalmi/caddy-mib) Track and ban client IPs generating repetitive errors on Caddy 
- [zonecontrol](https://github.com/fabriziosalmi/zonecontrol) Cloudflare Zones Settings Automation using GitHub Actions 
- [lws](https://github.com/fabriziosalmi/lws) linux (containers) web services
- [cf-box](https://github.com/fabriziosalmi/cf-box) cf-box is a set of Python tools to play with API and multiple Cloudflare accounts.
- [limits](https://github.com/fabriziosalmi/limits) Automated rate limits implementation for web servers 
- [dnscontrol-actions](https://github.com/fabriziosalmi/dnscontrol-actions) Automate DNS updates and rollbacks across multiple providers using DNSControl and GitHub Actions 
- [csv-anonymizer](https://github.com/fabriziosalmi/csv-anonymizer) CSV fuzzer/anonymizer
- [iamnotacoder](https://github.com/fabriziosalmi/iamnotacoder) AI code generation and improvement


## Disclaimer

> [!CAUTION]
> I am not responsible for any potential damage or issues that may arise from using this tool. 

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.
