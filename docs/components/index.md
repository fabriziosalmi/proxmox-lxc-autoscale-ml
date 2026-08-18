# Components Overview

LXC AutoScale ML is three separate services. Each runs under its own systemd unit and reads its own configuration file.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Proxmox Host                           │
│                                                             │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐   │
│  │    Monitor    │──│     Model     │──│      API      │   │
│  │   (Collect)   │  │   (Decide)    │  │   (Execute)   │   │
│  └───────────────┘  └───────────────┘  └───────────────┘   │
│         │                  │                   │            │
│         ▼                  ▼                   ▼            │
│  lxc_metrics.json    Predictions         pct commands      │
│                                                             │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                       │
│  │ LXC 101 │ │ LXC 102 │ │ LXC 103 │  ...                  │
│  └─────────┘ └─────────┘ └─────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

## Component Summary

| Component | Service | Purpose | Port |
|-----------|---------|---------|------|
| [API](/components/api) | `lxc_autoscale_api` | RESTful interface for scaling operations | 5000 |
| [Model](/components/model) | `lxc_autoscale_ml` | ML engine for scaling decisions | - |
| [Monitor](/components/monitor) | `lxc_monitor` | Metrics collection from containers | - |

## Data Flow

### 1. Metrics Collection

The Monitor service runs continuously, collecting resource metrics from all running LXC containers every 10 seconds (configurable).

**Metrics collected:**
- CPU usage percentage
- Memory usage (MB)
- Swap usage (MB)
- Disk usage (GB)
- Network I/O (bytes)
- Disk I/O (operations)
- Process count

**Output:** `/var/log/lxc_metrics.json`

### 2. ML Analysis

The Model service reads historical metrics and trains an IsolationForest model to detect anomalies in resource usage patterns.

**Processing steps:**
1. Load metrics from JSON file
2. Preprocess and engineer features
3. Train IsolationForest model
4. Batch fetch current container configurations
5. For each container:
   - Predict if usage is anomalous
   - Determine scaling action based on thresholds
   - Execute scaling via API

### 3. Scaling Execution

The API service receives scaling requests and executes them on the Proxmox host.

**Capabilities:**
- Scale CPU cores
- Scale memory (RAM)
- Increase storage
- Create/list/rollback snapshots
- Clone/delete containers
- Query resource status

## Service Management

### Start All Services

```bash
systemctl start lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

### Stop All Services

```bash
systemctl stop lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

### Check Status

```bash
systemctl status lxc_autoscale_api lxc_monitor lxc_autoscale_ml
```

### View Logs

```bash
journalctl -u lxc_autoscale_api -f
journalctl -u lxc_monitor -f
journalctl -u lxc_autoscale_ml -f
```

## Configuration Files

| Component | Configuration Path |
|-----------|-------------------|
| API | `/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml` |
| Model | `/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml` |
| Monitor | `/etc/lxc_autoscale_ml/lxc_monitor.yaml` |

## Dependencies Between Components

```
Monitor ──writes──▶ lxc_metrics.json ◀──reads── Model
                                                  │
                                                  │ API calls
                                                  ▼
                                                 API
                                                  │
                                                  │ pct commands
                                                  ▼
                                            LXC Containers
```

The components can run independently:
- **Monitor only**: Collect metrics without scaling
- **API only**: Manual scaling via API
- **All three**: Full automated scaling

## Next Steps

- [API Component](/components/api): RESTful interface details
- [Model Component](/components/model): ML engine and scaling logic
- [Monitor Component](/components/monitor): Metrics collection
