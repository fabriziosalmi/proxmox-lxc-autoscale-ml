# Uninstallation

This guide covers removing LXC AutoScale ML from your system.

## Quick Uninstallation

Run the uninstallation script:

```bash
curl -sSL https://raw.githubusercontent.com/fabriziosalmi/proxmox-lxc-autoscale-ml/main/uninstall.sh | bash
```

::: warning
This removes all application files and configurations. Back up your configuration before proceeding.
:::

## Manual Uninstallation

### Step 1: Stop and Disable Services

```bash
systemctl stop lxc_autoscale_api lxc_monitor lxc_autoscale_ml
systemctl disable lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

### Step 2: Remove Service Files

```bash
rm /lib/systemd/system/lxc_autoscale_api.service
rm /lib/systemd/system/lxc_monitor.service
rm /lib/systemd/system/lxc_autoscale_ml.service
systemctl daemon-reload
```

### Step 3: Remove Application Files

```bash
rm -rf /usr/local/bin/lxc_autoscale_ml
```

### Step 4: Remove Configuration (Optional)

```bash
rm -rf /etc/lxc_autoscale_ml
```

### Step 5: Remove Log Files (Optional)

```bash
rm /var/log/lxc_metrics.json
rm /var/log/lxc_autoscale_ml.log
rm /var/log/lxc_autoscale_api_*.log
```

### Step 6: Remove Lock File (If Exists)

```bash
rm -f /run/lxc_autoscale_ml.lock
```

### Step 7: Remove Log Rotation Configuration (Optional)

```bash
rm /etc/logrotate.d/lxc-autoscale-api
```

## Verify Uninstallation

```bash
# Check services are removed
systemctl status lxc_autoscale_api
# Should show: Unit lxc_autoscale_api.service could not be found

# Check files are removed
ls /usr/local/bin/lxc_autoscale_ml
# Should show: No such file or directory

ls /etc/lxc_autoscale_ml
# Should show: No such file or directory
```

## Keep Configuration for Reinstallation

If you plan to reinstall later, back up the configuration:

```bash
mkdir -p ~/lxc_autoscale_backup
cp -r /etc/lxc_autoscale_ml ~/lxc_autoscale_backup/
```

After reinstalling, restore the configuration:

```bash
cp -r ~/lxc_autoscale_backup/lxc_autoscale_ml /etc/
```

## Container State After Uninstallation

Uninstalling LXC AutoScale ML does not affect your LXC containers. They retain their current resource allocations.

To manually adjust container resources after uninstallation:

```bash
# Set CPU cores
pct set <vmid> -cores <number>

# Set memory
pct set <vmid> -memory <MB>
```
