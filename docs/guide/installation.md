# Installation

This guide covers installation methods for LXC AutoScale ML.

## Quick Installation

The recommended method uses the installation script:

```bash
curl -sSL https://raw.githubusercontent.com/fabriziosalmi/proxmox-lxc-autoscale-ml/main/install.sh | bash
```

This script:

1. Verifies system requirements
2. Installs Python dependencies via apt
3. Downloads application files to `/usr/local/bin/lxc_autoscale_ml/`
4. Creates configuration directory at `/etc/lxc_autoscale_ml/`
5. Installs systemd service files
6. Enables and starts all services

## Manual Installation

For environments requiring manual installation:

### Step 1: Install Dependencies

```bash
apt update
apt install -y git python3-flask python3-requests python3-sklearn \
  python3-pandas python3-numpy python3-aiofiles python3-yaml \
  python3-psutil python3-aiohttp
```

Optional Prometheus metrics support:

```bash
apt install -y python3-prometheus-client
```

### Step 2: Clone Repository

```bash
git clone https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml.git /tmp/lxc-autoscale-ml
```

### Step 3: Install Application Files

```bash
mkdir -p /usr/local/bin/lxc_autoscale_ml
cp -r /tmp/lxc-autoscale-ml/lxc_autoscale_ml/* /usr/local/bin/lxc_autoscale_ml/
chmod +x /usr/local/bin/lxc_autoscale_ml/*/*.py
```

### Step 4: Create Configuration Directory

```bash
mkdir -p /etc/lxc_autoscale_ml
cp /usr/local/bin/lxc_autoscale_ml/api/lxc_autoscale_api.yaml /etc/lxc_autoscale_ml/
cp /usr/local/bin/lxc_autoscale_ml/model/lxc_autoscale_ml.yaml /etc/lxc_autoscale_ml/
cp /usr/local/bin/lxc_autoscale_ml/monitor/lxc_monitor.yaml /etc/lxc_autoscale_ml/
```

### Step 5: Install Systemd Services

Create `/lib/systemd/system/lxc_autoscale_api.service`:

```ini
[Unit]
Description=LXC AutoScale API Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/lxc_autoscale_ml/api/lxc_autoscale_api.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Create `/lib/systemd/system/lxc_monitor.service`:

```ini
[Unit]
Description=LXC Monitor Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/lxc_autoscale_ml/monitor/lxc_monitor.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Create `/lib/systemd/system/lxc_autoscale_ml.service`:

```ini
[Unit]
Description=LXC AutoScale ML Service
After=network.target lxc_autoscale_api.service lxc_monitor.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/lxc_autoscale_ml/model/lxc_autoscale_ml.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Step 6: Enable and Start Services

```bash
systemctl daemon-reload
systemctl enable lxc_autoscale_api lxc_monitor lxc_autoscale_ml
systemctl start lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

## Post-Installation Configuration

### Set API Key

Generate a secure API key:

```bash
openssl rand -hex 32
```

Edit `/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml`:

```yaml
authentication:
  enabled: true
  api_keys:
    - "your-generated-key-here"
```

Restart the API service:

```bash
systemctl restart lxc_autoscale_api
```

### Configure LXCFS

Edit `/lib/systemd/system/lxcfs.service` and add the `-l` flag:

```ini
ExecStart=/usr/bin/lxcfs /var/lib/lxcfs -l
```

Apply changes:

```bash
systemctl daemon-reload
systemctl restart lxcfs
```

Restart LXC containers for the change to take effect.

## Verify Installation

### Check Service Status

```bash
systemctl status lxc_autoscale_api
systemctl status lxc_monitor
systemctl status lxc_autoscale_ml
```

### Test API Health

```bash
curl http://localhost:5000/health/check
```

### Check Metrics Collection

```bash
ls -la /var/log/lxc_metrics.json
```

### View Logs

```bash
journalctl -u lxc_autoscale_ml -n 20
```

## Log Rotation Setup

Create `/etc/logrotate.d/lxc_autoscale`:

```
/var/log/lxc_autoscale_ml.log
/var/log/autoscaleapi*.log {
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
    endscript
}
```

## Troubleshooting Installation

### Service Fails to Start

Check logs for errors:

```bash
journalctl -u lxc_autoscale_api -n 50 --no-pager
```

Common issues:

- Missing Python packages: Run `apt install python3-<package>`
- Permission errors: Verify file ownership is root
- Port conflict: Check if port 5000 is in use

### Cannot Connect to API

```bash
# Check if service is listening
ss -tlnp | grep 5000

# Test from localhost
curl -v http://127.0.0.1:5000/health/check
```

### Metrics Not Being Collected

```bash
# Check monitor service
systemctl status lxc_monitor

# Check for running containers
pct list

# Check metrics file
cat /var/log/lxc_metrics.json | head
```

## Next Steps

- [Configuration](/reference/configuration): Customize settings
- [Upgrading](/guide/upgrading): Upgrade from previous versions
