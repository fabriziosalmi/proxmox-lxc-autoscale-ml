# System Requirements

This page details all requirements for running LXC AutoScale ML.

## Hardware Requirements

### Proxmox Host

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8+ GB |
| Storage | 20 GB free | 50+ GB free |

The ML model training adds minimal overhead (typically less than 5% CPU during training cycles).

### Container Scaling Limits

Default limits that can be adjusted in configuration:

| Resource | Minimum | Maximum |
|----------|---------|---------|
| CPU Cores | 1 | 8 |
| RAM | 512 MB | 16 GB |

## Software Requirements

### Proxmox VE

| Version | Status |
|---------|--------|
| 8.x | Tested and supported |
| 7.x | Supported |
| 6.x | Supported |
| 5.x and earlier | Not supported |

### Python

Python **3.10 to 3.12** is required, and the installation script verifies that
Python is available.

The floor comes from the pinned `requests`, which needs 3.10; the ceiling from
the pinned `numpy`, `pandas` and `scikit-learn`, which have no 3.13 wheels.
Proxmox VE 8 (Debian 12) ships Python 3.11 and is the primary target. Proxmox VE
9 (Debian 13) ships 3.13, so the ML component needs those three pins raised
before it will install there; the API and the monitor are unaffected.

```bash
python3 --version
```

### Required Python Packages

These packages are installed automatically by the installation script:

| Package | Purpose |
|---------|---------|
| `flask` | API web framework |
| `requests` | HTTP client for API calls |
| `scikit-learn` | Machine learning (IsolationForest) |
| `pandas` | Data manipulation |
| `numpy` | Numerical operations |
| `aiofiles` | Async file operations |
| `pyyaml` | YAML configuration parsing |
| `psutil` | System metrics collection |
| `aiohttp` | Async HTTP client for batch requests |

### Optional Packages

| Package | Purpose |
|---------|---------|
| `prometheus-client` | Prometheus metrics export |

## Network Requirements

### Inbound Ports

| Port | Service | Access |
|------|---------|--------|
| 5000 | API | Localhost by default |

::: tip
The API listens on all interfaces but is protected by API key authentication. For additional security, restrict access using firewall rules.
:::

### Outbound Connections

The installation script requires internet access to download packages and source files.

## Filesystem Requirements

### Required Directories

| Directory | Purpose | Permissions |
|-----------|---------|-------------|
| `/etc/lxc_autoscale_ml/` | Configuration files | root:root 755 |
| `/var/log/` | Log files | root:root 755 |
| `/var/lock/` | Lock files | root:root 755 |
| `/usr/local/bin/lxc_autoscale_ml/` | Application code | root:root 755 |

### Disk Space for Logs

| File | Typical Size | Notes |
|------|-------------|-------|
| `lxc_metrics.json` | 2 MB max | Limited to 1000 entries |
| `lxc_autoscale_ml.log` | Varies | Use logrotate |
| `autoscaleapi.log` | Varies | Use logrotate |

## Container Requirements

### Supported Container Types

- Standard LXC containers
- Privileged and unprivileged containers
- Any Linux distribution inside containers

### LXCFS Configuration

For accurate load average reporting inside containers, LXCFS must be configured with the `-l` flag:

```bash
# Check current configuration
grep ExecStart /lib/systemd/system/lxcfs.service

# Should include -l flag:
# ExecStart=/usr/bin/lxcfs /var/lib/lxcfs -l
```

## Verification Commands

Run these commands to verify your system meets requirements:

```bash
# Check Proxmox version
pveversion

# Check Python version
python3 --version

# Check available disk space
df -h /var/log

# Check if required commands exist
which pct pvesh

# Verify LXCFS is running
systemctl status lxcfs
```

## Known Limitations

### Container ID Range

The API validates container IDs between 100 and 999999. IDs outside this range are rejected.

### Maximum Containers

Tested with up to 200 containers. Performance remains stable with batch async processing.

### Metrics Storage

The metrics file is limited to 1000 entries (configurable). Older entries are automatically removed.

## Next Steps

- [Installation](/guide/installation): Install LXC AutoScale ML
- [Getting Started](/guide/getting-started): Quick start guide
