# Environment Reference

This page documents file locations, log files, and system paths for LXC AutoScale ML.

## Installation Paths

### Application Files

| Path | Description |
|------|-------------|
| `/usr/local/bin/lxc_autoscale_ml/` | Application code |
| `/usr/local/bin/lxc_autoscale_ml/api/` | API component |
| `/usr/local/bin/lxc_autoscale_ml/model/` | Model component |
| `/usr/local/bin/lxc_autoscale_ml/monitor/` | Monitor component |

### Configuration Files

| Path | Component |
|------|-----------|
| `/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml` | API |
| `/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml` | Model |
| `/etc/lxc_autoscale_ml/lxc_monitor.yaml` | Monitor |

### Systemd Service Files

| Path | Service |
|------|---------|
| `/lib/systemd/system/lxc_autoscale_api.service` | API |
| `/lib/systemd/system/lxc_autoscale_ml.service` | Model |
| `/lib/systemd/system/lxc_monitor.service` | Monitor |

## Log Files

### Application Logs

| Path | Content |
|------|---------|
| `/var/log/lxc_autoscale_ml.log` | Model service main log |
| `/var/log/autoscaleapi.log` | API main log |
| `/var/log/autoscaleapi_access.log` | API access log |
| `/var/log/autoscaleapi_error.log` | API error log |
| `/var/log/lxc_monitor.log` | Monitor service log |

### Data Files

| Path | Content |
|------|---------|
| `/var/log/lxc_metrics.json` | Collected container metrics |

### Lock Files

| Path | Purpose |
|------|---------|
| `/var/lock/lxc_autoscale_ml.lock` | Model service instance lock |

## Service Names

| Service | Description |
|---------|-------------|
| `lxc_autoscale_api` | RESTful API service |
| `lxc_autoscale_ml` | ML model service |
| `lxc_monitor` | Metrics collection service |

## Network

### Ports

| Port | Service | Protocol |
|------|---------|----------|
| 5000 | API | HTTP |

### Default Bind Address

The API binds to `0.0.0.0` by default (all interfaces).

## Permissions

### File Ownership

All files should be owned by `root:root`:

```bash
chown -R root:root /usr/local/bin/lxc_autoscale_ml
chown -R root:root /etc/lxc_autoscale_ml
```

### File Permissions

| Path | Permissions | Notes |
|------|-------------|-------|
| Configuration files | `600` | Contains API key |
| Application files | `755` | Executable |
| Log directory | `755` | - |
| Log files | `644` | - |
| Lock file | `644` | Created at runtime |

### Secure Configuration

```bash
chmod 600 /etc/lxc_autoscale_ml/lxc_autoscale_api.yaml
chmod 644 /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml
chmod 644 /etc/lxc_autoscale_ml/lxc_monitor.yaml
```

## Dependencies

### Required System Packages

```
python3
python3-flask
python3-requests
python3-sklearn
python3-pandas
python3-numpy
python3-aiofiles
python3-yaml
python3-psutil
python3-aiohttp
```

### Optional System Packages

```
python3-prometheus-client  # For Prometheus metrics
```

### Python Module Paths

The application uses system Python packages installed via apt.

## Proxmox Integration

### Commands Used

| Command | Purpose |
|---------|---------|
| `pct` | LXC container management |
| `pvesh` | Proxmox API shell |
| `pct list` | List containers |
| `pct config` | Get container configuration |
| `pct set` | Set container options |

### Container Paths

| Path (inside container) | Collected Metrics |
|------------------------|-------------------|
| `/proc/stat` | CPU usage |
| `/proc/meminfo` | Memory usage |
| `/proc/diskstats` | Disk I/O |
| `/proc/net/dev` | Network I/O |

## Log Rotation

### Recommended Configuration

Create `/etc/logrotate.d/lxc_autoscale`:

```
/var/log/lxc_autoscale_ml.log
/var/log/autoscaleapi*.log
/var/log/lxc_monitor.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 640 root adm
    sharedscripts
    postrotate
        systemctl reload lxc_autoscale_api > /dev/null 2>&1 || true
        systemctl reload lxc_autoscale_ml > /dev/null 2>&1 || true
        systemctl reload lxc_monitor > /dev/null 2>&1 || true
    endscript
}
```

## Backup Locations

### Files to Backup

```bash
# Configuration
/etc/lxc_autoscale_ml/

# Metrics history (optional)
/var/log/lxc_metrics.json
```

### Backup Script

```bash
#!/bin/bash
BACKUP_DIR="/backup/lxc_autoscale"
DATE=$(date +%Y%m%d)

mkdir -p "$BACKUP_DIR"
tar czf "$BACKUP_DIR/config_$DATE.tar.gz" /etc/lxc_autoscale_ml/
cp /var/log/lxc_metrics.json "$BACKUP_DIR/metrics_$DATE.json"
```

## Troubleshooting Paths

### Check Service Status

```bash
systemctl status lxc_autoscale_api
systemctl status lxc_autoscale_ml
systemctl status lxc_monitor
```

### Check Logs

```bash
journalctl -u lxc_autoscale_api -n 50
journalctl -u lxc_autoscale_ml -n 50
journalctl -u lxc_monitor -n 50
```

### Verify Files Exist

```bash
ls -la /etc/lxc_autoscale_ml/
ls -la /var/log/lxc_*.json
ls -la /var/log/lxc_*.log
ls -la /var/log/autoscaleapi*.log
```
