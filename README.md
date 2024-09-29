# ✨ LXC AutoScale ML

**LXC AutoScale ML** is a resource management daemon specifically designed for Proxmox environments. It automatically monitor resources and adjusts CPU and memory allocations with no downtime based on real-time usage metrics and predefined thresholds with the help of a machine learning pipeline.

- **✅ Works with `Proxmox 8.2.4`**

![Platform](https://img.shields.io/badge/platform-Proxmox-green) ![Python Version](https://img.shields.io/badge/python-3.x-blue) ![Version](https://img.shields.io/badge/version-alpha-red)


![#alt](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/blob/main/docs/lxc_autoscale_ml.png?raw=true)



> _LXC AutoScale ML in action :)_
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

## 📚 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [System Requirements](#-system-requirements)
- [Installation](#️-installation)
- [Components Overview](#-components-overview)
  - [API Component](#1-api-component)
  - [Monitor Component](#2-monitor-component)
  - [Model Component](#3-model-component)
- [Usage and Control](#-usage-and-control)
- [Monitoring and Alerts](#-monitoring-and-alerts)
- [Documentation](#-documentation)
- [Uninstallation](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml?tab=readme-ov-file#%EF%B8%8F-uninstallation)
- [Contributing](#-contributing)
- [License](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/blob/main/LICENSE)

## 🎨 Overview

**LXC AutoScale ML** is a tool designed to manage LXC containers on Proxmox hosts using machine learning for automatic scaling. It dynamically adjusts container resources to maintain optimal performance and efficient resource utilization.

### 🚀 Key Features

- **Proxmox Integration**: Seamless integration with Proxmox hosts via API and CLI.
- **ML-Driven Autoscaling**: Utilizes machine learning models to predict and respond to resource demands.
- **Modular Architecture**: Components (API, Monitor, Model) designed to handle specific autoscaling tasks.
- **Customizable Policies**: Define custom scaling rules and thresholds.
- **Real-Time Monitoring and Logging**: Provides detailed logs for auditing and optimization.

## 📋 System Requirements

- **Proxmox Host**: Version 6.x or higher
- **Operating System**: Linux (Debian-based preferred)
- **Python**: Version 3.x
- **Dependencies**:
  ```bash
  git, python3-flask, python3-requests, python3-sklearn, python3-pandas, python3-numpy, python3-aiofiles
  ```

## 🛠️ Installation

To install **LXC AutoScale ML**, execute the following command:

```bash
curl -sSL https://raw.githubusercontent.com/fabriziosalmi/proxmox-lxc-autoscale-ml/main/install.sh | bash
```

### ⚠️ Prerequisites

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
> Just update the `/lib/systemd/system/lxcfs.service` file, execute `systemctl daemon-realod && systemctl restart lxcfs` and when you are ready to apply the fix restart the LXC containers.
> 
> _Tnx to No-Pen9082 to point me out to that. [Here](https://forum.proxmox.com/threads/lxc-containers-shows-hosts-load-average.45724/page-2) the Proxmox forum thread on the topic._


## 📦 Components Overview

### 1. API Component

The **API** provides RESTful endpoints for managing autoscaling services.

#### 📘 Features

- **Scaling Operations**: Trigger container scaling manually.
- **Configuration Management**: Dynamically update scaling configurations.
- **Monitoring and Health Checks**: Access real-time metrics and system status.
- **Audit Logging**: Logs all API interactions for security purposes.

#### 📋 API Endpoints

| Endpoint                   | Methods | Description                                             | Example                                                                                   |
|----------------------------|---------|---------------------------------------------------------|-------------------------------------------------------------------------------------------|
| `/scale/cores`             | POST    | Set the exact number of CPU cores for an LXC container.  | `curl -X POST http://proxmox:5000/scale/cores -H "Content-Type: application/json" -d '{"vm_id": 104, "cores": 4}'` |
| `/scale/ram`               | POST    | Set the exact amount of RAM for an LXC container.        | `curl -X POST http://proxmox:5000/scale/ram -H "Content-Type: application/json" -d '{"vm_id": 104, "memory": 4096}'` |
| `/scale/storage/increase`  | POST    | Increase the storage size of an LXC container's root filesystem. | `curl -X POST http://proxmox:5000/scale/storage/increase -H "Content-Type: application/json" -d '{"vm_id": 104, "disk_size": 2}'` |
| `/snapshot/create`         | POST    | Create a snapshot for an LXC container.                  | `curl -X POST http://proxmox:5000/snapshot/create -H "Content-Type: application/json" -d '{"vm_id": 104, "snapshot_name": "my_snapshot"}'` |
| `/snapshot/list`           | GET     | List all snapshots for an LXC container.                 | `curl -X GET "http://proxmox:5000/snapshot/list?vm_id=104"`                               |
| `/snapshot/rollback`       | POST    | Rollback to a specific snapshot.                        | `curl -X POST http://proxmox:5000/snapshot/rollback -H "Content-Type: application/json" -d '{"vm_id": 104, "snapshot_name": "my_snapshot"}'` |
| `/clone/create`            | POST    | Clone an LXC container.                                  | `curl -X POST http://proxmox:5000/clone/create -H "Content-Type: application/json" -d '{"vm_id": 104, "new_vm_id": 105, "new_vm_name": "cloned_container"}'` |
| `/clone/delete`            | DELETE  | Delete a cloned LXC container.                           | `curl -X DELETE http://proxmox:5000/clone/delete -H "Content-Type: application/json" -d '{"vm_id": 105}'` |
| `/resource/vm/status`      | GET     | Check the resource allocation and usage for an LXC container. | `curl -X GET "http://proxmox:5000/resource/vm/status?vm_id=104"`                        |
| `/resource/node/status`    | GET     | Check the resource usage of a specific node.             | `curl -X GET "http://proxmox:5000/resource/node/status?node_name=proxmox"`                |
| `/health/check`            | GET     | Perform a health check on the API server.                | `curl -X GET http://proxmox:5000/health/check`                                            |
| `/routes`                  | GET     | List all available routes.                               | `curl -X GET http://proxmox:5000/routes`                                                  |

### 2. Monitor Component

The **Monitor** service continuously tracks the performance and resource usage of LXC containers.

#### 📘 Features

- **Real-Time Metrics Collection**: Collects CPU, memory, disk, and network usage statistics.
- **Anomaly Detection**: Detects unusual patterns in resource usage.
- **Threshold Alerts**: Triggers alerts or scaling actions when predefined thresholds are exceeded.
- **Data Aggregation**: Aggregates metrics for analysis and reporting.

### 3. Model Component

The **Model** uses machine learning algorithms to analyze metrics and predict scaling needs.

#### 📘 Features

- **Anomaly Detection**: Uses `IsolationForest` to detect unusual usage patterns.
- **Predictive Scaling**: Forecasts when scaling actions are necessary.
- **Adaptive Learning**: Continuously refines predictions based on new data.
- **Customizable Models**: Supports various ML algorithms and configurations.

## 🔧 Usage and Control

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

### 📊 Monitoring and Alerts

- **Metrics Dashboard**: Integrate with tools like Grafana or Prometheus for visualization.
- **Alerting**: Configure alerts for critical events, such as spikes in CPU or memory usage.

## 📚 Documentation

For detailed documentation, including advanced usage, configuration options, and troubleshooting, please refer to the [Extended Documentation](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/blob/main/docs/README.md).

## 🛠️ Uninstallation

To uninstall **LXC AutoScale ML**, execute the following command:

```bash
curl -sSL https://raw.githubusercontent.com/fabriziosalmi/proxmox-lxc-autoscale-ml/main/uninstall.sh | bash
```

> [!WARNING]
> The uninstallation script will remove all related files and configurations.
> Ensure to back up any important data before proceeding.

## 📝 Contributing

We welcome contributions! Please follow these steps:

1. **Fork** the repository.
2. **Create** a new branch (`git checkout -b feature/your-feature`).
3. **Commit** your changes (`git commit -m 'Add your feature'`).
4. **Push** to the branch (`git push origin feature/your-feature`).
5. Open a **Pull Request**.

## 🛡️ License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.
