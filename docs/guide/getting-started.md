# Getting Started

This guide walks you through installing and verifying LXC AutoScale ML on your Proxmox host.

## Prerequisites

Before installation, ensure your system meets these requirements:

| Requirement | Specification |
|-------------|---------------|
| Proxmox VE | Version 6.x or higher (tested on 8.2.4) |
| Operating System | Linux (Debian-based) |
| Python | Version 3.x |
| Privileges | Root or sudo access |
| Network | Internet access for package downloads |

## Installation

Run the installation script on your Proxmox host:

```bash
curl -sSL https://raw.githubusercontent.com/fabriziosalmi/proxmox-lxc-autoscale-ml/main/install.sh | bash
```

The script performs these actions:

1. Verifies system requirements
2. Installs Python dependencies
3. Downloads and configures service files
4. Enables and starts all three services

### Dependencies Installed

```
python3-flask
python3-requests
python3-sklearn
python3-pandas
python3-numpy
python3-aiofiles
python3-yaml
python3-psutil
python3-aiohttp
python3-prometheus-client (optional)
```

## Verify Installation

Check that all services are running:

```bash
systemctl status lxc_autoscale_api
systemctl status lxc_monitor
systemctl status lxc_autoscale_ml
```

Expected output for each service:

```
● lxc_autoscale_api.service - LXC AutoScale API
     Loaded: loaded
     Active: active (running)
```

### Test the API

Verify the API responds to health checks:

```bash
curl http://localhost:5000/health/check
```

Expected response:

```json
{
  "status": "healthy",
  "timestamp": "2024-12-24T12:00:00Z"
}
```

### Check Metrics Collection

Verify the monitor is collecting metrics:

```bash
cat /var/log/lxc_metrics.json | head -20
```

You should see JSON entries with container metrics.

## LXCFS Configuration

::: warning Important
Configure LXCFS to report accurate load averages inside containers.
:::

Edit `/lib/systemd/system/lxcfs.service` and update the `ExecStart` line to include the `-l` flag:

```ini
[Unit]
Description=FUSE filesystem for LXC
ConditionVirtualization=!container
Before=lxc.service
Documentation=man:lxcfs(1)

[Service]
OOMScoreAdjust=-1000
ExecStartPre=/bin/mkdir -p /var/lib/lxcfs
ExecStart=/usr/bin/lxcfs /var/lib/lxcfs -l
KillMode=process
Restart=on-failure
ExecStopPost=-/bin/fusermount -u /var/lib/lxcfs
Delegate=yes
ExecReload=/bin/kill -USR1 $MAINPID

[Install]
WantedBy=multi-user.target
```

Apply the changes:

```bash
systemctl daemon-reload
systemctl restart lxcfs
```

Restart your LXC containers for the changes to take effect.

## Initial Configuration

### API Key Setup

Edit the API configuration to set your API key:

```bash
nano /etc/lxc_autoscale_ml/lxc_autoscale_api.yaml
```

Update the authentication section:

```yaml
authentication:
  enabled: true
  api_key: "your-secure-api-key-here"
```

::: tip
Generate a secure key using: `openssl rand -hex 32`
:::

### Scaling Thresholds

Review and adjust scaling thresholds in the model configuration:

```bash
nano /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
```

Key settings:

```yaml
scaling:
  cpu_scale_up_threshold: 70      # Scale up at 70% CPU
  cpu_scale_down_threshold: 30    # Scale down at 30% CPU
  ram_scale_up_threshold: 80      # Scale up at 80% RAM
  ram_scale_down_threshold: 40    # Scale down at 40% RAM
  cpu_scale_step: 1               # Add/remove 1 core at a time
  ram_scale_step_mb: 512          # Add/remove 512 MB at a time
```

Restart services after configuration changes:

```bash
systemctl restart lxc_autoscale_api lxc_autoscale_ml
```

## First Scaling Cycle

The system begins collecting metrics immediately. The first scaling decisions occur after sufficient historical data is gathered (typically 5-10 data points).

Monitor the ML service logs to observe scaling activity:

```bash
journalctl -u lxc_autoscale_ml -f
```

Example output:

```
INFO - Batch fetching configs for 12 containers...
INFO - Batch fetch completed in 0.15s: 12/12 successful
INFO - Processing container 104...
INFO - IsolationForest prediction for 104: -1 (anomaly)
INFO - Scaling decision for 104: CPU=Scale Up (confidence: 87.4%)
INFO - Successfully scaled CPU for LXC ID 104 to 4 cores
```

## Service Management

### Start Services

```bash
systemctl start lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

### Stop Services

```bash
systemctl stop lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

### Restart Services

```bash
systemctl restart lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

### View Logs

```bash
# API logs
journalctl -u lxc_autoscale_api -n 50

# Monitor logs
journalctl -u lxc_monitor -n 50

# Model logs
journalctl -u lxc_autoscale_ml -n 50
```

## Next Steps

- [Architecture](/guide/architecture): Understand how the components work together
- [Configuration](/reference/configuration): Customize all available settings
- [Troubleshooting](/guide/troubleshooting): Resolve common issues
