# ✨ LXC AutoScale ML

![Platform](https://img.shields.io/badge/platform-Proxmox-green) ![Python Version](https://img.shields.io/badge/python-3.x-blue) ![Version](https://img.shields.io/badge/version-alpha-red)

## 🎨 Overview

**LXC AutoScale ML** is a sophisticated tool dedicated to managing LXC containers on Proxmox hosts, providing automatic scaling based on machine learning algorithms. It leverages Python's powerful data science libraries and provides an API-driven approach to dynamically adjust container resources according to real-time usage patterns, ensuring optimal performance and efficient resource allocation.

### 🚀 Key Features

- **Proxmox Host Integration**: Directly interfaces with Proxmox hosts, utilizing APIs and command-line tools for seamless LXC container management.
- **Machine Learning-Driven Autoscaling**: Uses advanced machine learning models to predict and respond to resource demands.
- **Modular Architecture**: Divided into three primary components: API, Monitor, and Model, each designed to handle specific aspects of autoscaling.
- **Customizable Policies**: Define custom scaling rules and thresholds based on your environment's unique needs.
- **Comprehensive Monitoring and Logging**: Real-time monitoring and detailed logs for auditing, debugging, and performance optimization.

## 📋 System Requirements

Before installing **LXC AutoScale ML**, ensure that your environment meets the following requirements:

- **Proxmox Host**: Version 6.x or higher.
- **Operating System**: Linux (Debian-based distributions preferred).
- **Python**: Version 3.x.
- **Required Packages**:
  - `git`
  - `python3-flask`
  - `python3-requests`
  - `python3-sklearn`
  - `python3-pandas`
  - `python3-numpy`

## 🛠️ Installation

To install **LXC AutoScale ML**, execute the following command on your Proxmox host:

```bash
curl -sSL https://raw.githubusercontent.com/fabriziosalmi/proxmox-lxc-autoscale-ml/main/install.sh | bash
```

This installation script performs the following tasks:

1. **System Check**: Verifies that all necessary software packages and dependencies are installed.
2. **Download and Setup**: Retrieves the required files from the repository and configures the necessary directories and services.
3. **Service Configuration**: Enables and starts all relevant services to handle API requests, monitor container metrics, and execute machine learning models.

### ⚠️ Prerequisites

- Run the installation command with root or sudo privileges to ensure all configurations and installations are applied correctly.
- Ensure your Proxmox server has internet access to download necessary files and packages.

## 📦 Components Overview

**LXC AutoScale ML** consists of three main components:

1. **API**: The backend service that provides endpoints for scaling operations, configuration management, and monitoring.
2. **Monitor**: A dedicated service that tracks container performance metrics and triggers scaling decisions.
3. **Model**: Machine learning models that analyze data and predict the optimal scaling actions to maintain performance and resource efficiency.

### 1. API Component

The **API** component is the central control unit of **LXC AutoScale ML**. It exposes various RESTful endpoints to manage and interact with the autoscaling services.

#### 📘 Key Features of the API

- **Scaling Operations**: Endpoints to manually trigger upscaling or downscaling of containers based on predefined rules.
- **Configuration Management**: APIs to dynamically update scaling configurations, such as thresholds, policies, and container groups.
- **Monitoring and Health Checks**: Provides real-time metrics and health information for LXC containers.
- **Audit Logging**: Logs all API interactions for security and auditing purposes.

#### 📋 API Endpoints

| Endpoint                      | Method | Description                                                      |
|-------------------------------|--------|------------------------------------------------------------------|
| `/api/v1/scale/up`            | POST   | Trigger upscaling of a specific container or group of containers. |
| `/api/v1/scale/down`          | POST   | Trigger downscaling of a specific container or group.             |
| `/api/v1/config/update`       | PUT    | Update the scaling configuration dynamically.                    |
| `/api/v1/monitor/metrics`     | GET    | Fetch real-time metrics for all monitored containers.            |
| `/api/v1/health`              | GET    | Check the health status of the API and connected services.        |

#### 🔧 API Configuration

The API configuration is stored in `lxc_autoscale_api.yaml`, located in `/etc/lxc_autoscale_ml/`. The configuration file includes parameters such as:

- **API Port**: Port number for the API server.
- **Authentication**: Credentials for accessing the API endpoints.
- **Scaling Policies**: Rules and thresholds for container scaling.

```yaml
api:
  port: 8080
  auth:
    username: "admin"
    password: "password"
scaling_policies:
  default_cpu_threshold: 75
  default_memory_threshold: 80
  cooldown_period: 300
```

### 2. Monitor Component

The **Monitor** component is a background service that continuously monitors the performance and resource utilization of LXC containers on the Proxmox host.

#### 📘 Key Features of the Monitor

- **Real-Time Metrics Collection**: Captures CPU, memory, disk, and network usage statistics from each container.
- **Anomaly Detection**: Identifies unusual patterns in resource usage, such as spikes in CPU or memory consumption.
- **Threshold Alerts**: Triggers alerts or scaling actions when resource utilization exceeds predefined thresholds.
- **Data Aggregation**: Aggregates metrics data over time for analysis and reporting.

#### 🔧 Monitor Configuration

The monitor configuration is stored in `lxc_monitor.yaml`, located in `/etc/lxc_autoscale_ml/`. Configuration parameters include:

- **Polling Interval**: Time interval for collecting metrics data (in seconds).
- **Alert Thresholds**: Thresholds for triggering alerts or scaling actions.
- **Logging Level**: Defines the verbosity of logs generated by the monitor.

```yaml
monitor:
  polling_interval: 60
  alert_thresholds:
    cpu: 85
    memory: 90
  logging:
    level: INFO
    path: "/var/log/lxc_autoscale_ml/monitor.log"
```

#### 📊 Real-Time Metrics and Alerts

The monitor component integrates with the API to provide real-time metrics:

- **CPU Usage**: Average and peak CPU usage per container.
- **Memory Usage**: Total and available memory consumption.
- **Disk I/O**: Read and write operations per second.
- **Network Traffic**: Inbound and outbound data rates.

Alerts can be sent via email, Slack, or other notification channels when critical thresholds are exceeded.

### 3. Model Component

The **Model** component utilizes machine learning algorithms to analyze the collected metrics and predict future resource demands. The model's primary goal is to determine when and how to scale the LXC containers to maintain optimal performance.

#### 📘 Key Features of the Model

- **Anomaly Detection**: Detects anomalous behavior in container resource usage using models like `IsolationForest`.
- **Predictive Scaling**: Uses historical data to predict when scaling actions will be necessary.
- **Adaptive Learning**: Continuously improves the accuracy of predictions by learning from new data.
- **Customizable Models**: Allows the use of different ML algorithms and parameters based on the specific environment.

#### 🔍 Machine Learning Algorithms

The current implementation uses a combination of `scikit-learn` models for scaling decisions:

- **Isolation Forest**: For detecting anomalies and sudden spikes in usage.
- **Linear Regression**: For predicting trends in resource consumption.
- **Clustering Algorithms**: To group similar usage patterns and optimize scaling actions.

#### 🔧 Model Configuration

The model configuration is stored in `lxc_autoscale_ml.yaml`, located in `/etc/lxc_autoscale_ml/`. Configuration parameters include:

- **Algorithm Parameters**: Specific parameters for the ML models, such as the number of estimators or contamination rates.
- **Data Retention**: Duration for retaining historical data.
- **Training Frequency**: How often the model retrains itself with new data.

```yaml
model:
  algorithm: IsolationForest
  parameters:
    n_estimators: 100
    contamination: 0.1
  data_retention: 30  # days
  training_frequency: 24  # hours
```

#### 📈 Machine Learning Pipeline

Here’s an example of the machine learning pipeline used for scaling decisions:

```python
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

pipeline = Pipeline([
    ('scaler', StandardScaler()),
    ('model', IsolationForest(n_estimators=100, contamination=0.1))
])

# Training the model
pipeline.fit(training_data)

# Predicting anomalies
anomalies = pipeline.predict(new_data)
```

The pipeline is dynamically retrained based on new data collected by the monitor component.

## 🔧 Usage and

 Control

Once installed, you can manage the autoscaling services using the following systemd commands:

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

- **Metrics Dashboard**: Integrate with tools like Grafana or Prometheus to visualize the metrics collected by the monitor.
- **Alerting**: Configure alerts for critical events, such as sudden spikes in CPU or memory usage.

## 🛠️ Uninstallation

To uninstall **LXC AutoScale ML**, execute the following command on your Proxmox host:

```bash
curl -sSL https://raw.githubusercontent.com/fabriziosalmi/proxmox-lxc-autoscale-ml/main/uninstall.sh | bash
```

## 📝 Contributing

We welcome contributions to **LXC AutoScale ML**! Please follow these steps:

1. **Fork** the repository.
2. **Create** a new branch (`git checkout -b feature/your-feature`).
3. **Commit** your changes (`git commit -m 'Add your feature'`).
4. **Push** to the branch (`git push origin feature/your-feature`).
5. Open a **Pull Request**.

### 🔧 Development Environment Setup

To set up a development environment:

1. Clone the repository:
   ```bash
   git clone https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml.git
   cd proxmox-lxc-autoscale-ml
   ```

2. Install the necessary dependencies:
   ```bash
   sudo apt update
   sudo apt install git python3 python3-flask python3-requests python3-sklearn python3-pandas python3-numpy
   ```

3. Run the services locally for testing and development.

## 🛡️ License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.
