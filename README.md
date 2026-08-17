# LXC AutoScale ML

**LXC AutoScale ML** is a resource management daemon for Proxmox environments. It monitors LXC container resources and adjusts CPU and memory allocations with zero downtime, using machine learning to predict resource demands.

**Tested with Proxmox VE 8.2.4**

![Platform](https://img.shields.io/badge/platform-Proxmox-green) ![Python Version](https://img.shields.io/badge/python-3.x-blue) ![License](https://img.shields.io/badge/license-MIT-blue)

![LXC AutoScale ML Architecture](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/blob/main/docs/lxc_autoscale_ml.png?raw=true)

**Example output:**
```
2024-08-20 13:07:56,393 [INFO] Data loaded successfully from /var/log/lxc_metrics.json.
2024-08-20 13:07:56,399 [INFO] Data preprocessed successfully.
2024-08-20 13:07:56,416 [INFO] Feature engineering, spike detection, and trend detection completed.
2024-08-20 13:07:56,417 [INFO] Features used for training: ['cpu_memory_ratio', 'cpu_per_process', 'cpu_trend', 'cpu_usage_percent', 'filesystem_free_gb', 'filesystem_total_gb', 'filesystem_usage_gb', 'io_reads', 'io_writes', 'max_cpu', 'max_memory', 'memory_per_process', 'memory_trend', 'memory_usage_mb', 'min_cpu', 'min_memory', 'network_rx_bytes', 'network_tx_bytes', 'process_count', 'rolling_mean_cpu', 'rolling_mean_memory', 'rolling_std_cpu', 'rolling_std_memory', 'swap_total_mb', 'swap_usage_mb', 'time_diff']
2024-08-20 13:07:56,549 [INFO] IsolationForest model training completed.
2024-08-20 13:07:56,549 [INFO] Processing containers for scaling decisions...
2024-08-20 13:07:56,600 [INFO] Applying scaling actions for container 104: CPU - Scale Up, RAM - Scale Up | Confidence: 87.41%
2024-08-20 13:07:57,257 [INFO] Successfully scaled CPU for LXC ID 104 to 4 CPU units.
2024-08-20 13:07:57,916 [INFO] Successfully scaled RAM for LXC ID 104 to 8192 RAM units.
2024-08-20 13:07:57,916 [INFO] Sleeping for 60 seconds before the next run.
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

LXC AutoScale ML manages LXC containers on Proxmox hosts using machine learning for automatic scaling. It dynamically adjusts container resources to maintain optimal performance and efficient resource utilization.

### Key Features

- **Proxmox Integration**: Seamless integration with Proxmox hosts via API and CLI.
- **ML-Driven Autoscaling**: Utilizes IsolationForest machine learning model to detect anomalies and predict resource demands.
- **High-Performance Async API**: Batch async requests provide **10x faster** config fetching for large-scale deployments (60+ containers).
- **Enterprise Security**: API key authentication, rate limiting with localhost bypass, input validation on all endpoints.
- **Circuit Breaker Pattern**: Automatic fault tolerance and graceful degradation for API failures.
- **Modular Architecture**: Components (API, Monitor, Model) designed to handle specific autoscaling tasks.
- **Customizable Policies**: Define custom scaling rules, thresholds, and step sizes.
- **Real-Time Monitoring**: Prometheus metrics export for comprehensive observability.
- **Smart Resource Management**: Incremental scaling (no more jumping to max/min), stale lock cleanup, metrics file size limiting.
- **Production-Ready**: Comprehensive error handling, detailed logging, and troubleshooting guides.

## System Requirements

- **Proxmox Host**: Version 6.x or higher (tested on 8.2.4)
- **Operating System**: Linux (Debian-based preferred)
- **Python**: Version 3.x
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

The **API** provides RESTful endpoints for managing autoscaling services with enterprise-grade security and performance.

#### Features

- **Scaling Operations**: Trigger container scaling manually or via automation.
- **Configuration Management**: Dynamically update scaling configurations.
- **Security Features**:
  - **API Key Authentication**: Secure all endpoints (except health checks and metrics)
  - **Rate Limiting**: 120 requests/minute with localhost bypass for internal services
  - **Input Validation**: Comprehensive validation on all parameters
- **Monitoring and Health Checks**: 
  - Real-time metrics and system status
  - **Prometheus Metrics Export**: Track scaling actions, API requests, resource usage
- **Audit Logging**: Complete logs of all API interactions for security and debugging.
- **High Performance**: Handles 60+ containers with ease via optimized async operations.

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
| `/resource/lxc/config`      | GET     | Get min/max resource limits for an LXC container. | `curl -X GET "http://proxmox:5000/resource/lxc/config?lxc_id=104"`                        |
| `/resource/node/status`    | GET     | Check the resource usage of a specific node.             | `curl -X GET "http://proxmox:5000/resource/node/status?node_name=proxmox"`                |
| `/health/check`            | GET     | Perform a health check on the API server.                | `curl -X GET http://proxmox:5000/health/check`                                            |
| `/metrics`                 | GET     | Export Prometheus metrics for monitoring.                | `curl -X GET http://proxmox:5000/metrics`                                                 |
| `/routes`                  | GET     | List all available routes.                               | `curl -X GET http://proxmox:5000/routes`                                                  |

> **Security Note**: Use `X-API-Key` header for authenticated requests. See [API Documentation](docs/lxc_autoscale_api/README.md) for details.

### 2. Monitor Component

The **Monitor** service continuously tracks the performance and resource usage of LXC containers.

#### Features

- **Real-Time Metrics Collection**: Collects CPU, memory, disk, and network usage statistics.
- **Anomaly Detection**: Detects unusual patterns in resource usage.
- **Threshold Alerts**: Triggers alerts or scaling actions when predefined thresholds are exceeded.
- **Data Aggregation**: Aggregates metrics for analysis and reporting.
- **Automatic Size Management**: Limits metrics file to 1000 entries to prevent memory issues.
- **Efficient Storage**: Optimized JSON storage with automatic cleanup of old data.

### 3. Model Component

The **Model** uses machine learning algorithms to analyze metrics and make intelligent scaling decisions.

#### Features

- **IsolationForest ML Model**: Detects anomalies in resource usage patterns with high accuracy.
- **Incremental Scaling**: Scales resources gradually (±1 core, ±512MB RAM) instead of jumping to extremes.
- **Predictive Scaling**: Forecasts when scaling actions are necessary based on historical data.
- **Adaptive Learning**: Continuously refines predictions based on new data.
- **High-Performance Async API Client**: Fetches all container configs concurrently (**10x faster** than sequential).
- **Circuit Breaker Pattern**: Automatically skips failed API endpoints to prevent cascading failures.
- **Smart Resource Management**:
  - Stale lock cleanup with PID checking
  - Graceful degradation on API errors
  - Automatic retry with exponential backoff
- **Configurable Models**: Supports various ML algorithms and custom thresholds.
- **Production-Ready**: Comprehensive error handling and detailed logging.

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
  - API request/response metrics  
  - Container resource gauges
  - Circuit breaker status
  - Model prediction accuracy
- **Metrics Dashboard**: Integrate with tools like Grafana for visualization.
- **Alerting**: Configure alerts for critical events, such as spikes in CPU or memory usage.
- **Performance Monitoring**: Track batch API performance (containers/sec) in service logs.

#### Example Prometheus Queries

```promql
# Total scaling actions in last hour
rate(lxc_scaling_actions_total[1h])

# Containers scaled up vs down
lxc_scaling_actions_total{action="scale_up"} / lxc_scaling_actions_total{action="scale_down"}

# Average API response time
rate(lxc_api_request_duration_seconds_sum[5m]) / rate(lxc_api_request_duration_seconds_count[5m])
```

## Documentation

For comprehensive documentation, visit the **[Documentation Site](./docs/)** or build it locally:

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
| [Changelog](./docs/changelog.md) | Version history |

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
- [blacklists](https://github.com/fabriziosalmi/blacklists) Hourly updated domains blacklist 🚫 
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
