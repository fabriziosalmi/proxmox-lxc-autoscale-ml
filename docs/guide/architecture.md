# Architecture

LXC AutoScale ML is three separate systemd services that share nothing but a metrics file on disk.

## System Overview

```
┌────────────────────────────────────────────────────────────────┐
│                        Proxmox Host                            │
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│  │   Monitor   │───▶│    Model    │───▶│     API     │        │
│  │  Service    │    │   Service   │    │   Service   │        │
│  └─────────────┘    └─────────────┘    └─────────────┘        │
│         │                  │                  │                │
│         ▼                  │                  ▼                │
│  lxc_metrics.json          │           pct commands           │
│                            │                                   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                          │
│  │ LXC 101 │ │ LXC 102 │ │ LXC 103 │  ...                     │
│  └─────────┘ └─────────┘ └─────────┘                          │
└────────────────────────────────────────────────────────────────┘
```

## Component Details

### Monitor Service

**Service**: `lxc_monitor.service`
**Configuration**: `/etc/lxc_autoscale_ml/lxc_monitor.yaml`
**Output**: `/var/log/lxc_metrics.json`

The Monitor service collects resource metrics from all running LXC containers at configurable intervals.

#### Responsibilities

- Scan for running containers
- Collect CPU, memory, disk, network, and I/O metrics
- Store metrics in JSON format
- Manage file size (limit to 1000 entries by default)

#### Metrics Collected

| Category | Metrics |
|----------|---------|
| CPU | Usage percentage, per-process usage, min/max values |
| Memory | Usage in MB, per-process usage, min/max values |
| Swap | Current usage, total available |
| Disk | Used, free, and total space in GB |
| Network | Received and transmitted bytes |
| I/O | Read and write operation counts |
| System | Process count, timestamp |

### Model Service

**Service**: `lxc_autoscale_ml.service`
**Configuration**: `/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml`
**Log**: `/var/log/lxc_autoscale_ml.log`

The Model service is the ML engine that analyzes metrics and makes scaling decisions.

#### Responsibilities

- Load and preprocess historical metrics
- Train IsolationForest model
- Detect anomalies in resource usage
- Determine scaling actions for each container
- Execute scaling via API calls

#### Processing Loop

```
1. Load Configuration
   ↓
2. Verify Lock (prevent multiple instances)
   ↓
3. Load Historical Metrics
   ↓
4. Preprocess & Feature Engineering
   ↓
5. Train IsolationForest Model
   ↓
6. Batch Fetch Container Configs (async)
   ↓
7. For Each Container:
   - Predict anomaly
   - Determine scaling action
   - Apply scaling via API
   ↓
8. Sleep & Repeat
```

#### IsolationForest Model

The IsolationForest algorithm detects anomalies by isolating observations. It works well for this use case because:

- Unsupervised learning (no labeled data required)
- Efficient for high-dimensional data
- Good at detecting outliers in resource usage patterns

**Features used for training** (26 total):

- CPU metrics: usage, rolling mean/std, trend, min/max, per-process
- Memory metrics: usage, rolling mean/std, trend, min/max, per-process, swap
- Combined: CPU/memory ratio
- Disk: used, free, total
- Network: RX/TX bytes
- I/O: reads, writes
- System: process count, time diff

### API Service

**Service**: `lxc_autoscale_api.service`
**Configuration**: `/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml`
**Port**: 5000 (default)

The API service provides a RESTful interface for executing scaling operations.

#### Responsibilities

- Handle scaling requests (CPU, RAM, storage)
- Manage snapshots and clones
- Report container and node status
- Export Prometheus metrics
- Enforce authentication and rate limiting

#### Security Layers

```
Request
   │
   ▼
┌─────────────────┐
│ Rate Limiting   │ ──▶ 120 req/min (localhost bypass)
└─────────────────┘
   │
   ▼
┌─────────────────┐
│ Authentication  │ ──▶ API key validation
└─────────────────┘
   │
   ▼
┌─────────────────┐
│ Input Validation│ ──▶ Parameter sanitization
└─────────────────┘
   │
   ▼
┌─────────────────┐
│ Route Handler   │ ──▶ Execute operation
└─────────────────┘
```

## Data Flow

### Metrics Collection Flow

```
Container → Monitor → JSON File
   │           │          │
   │           │          └─ /var/log/lxc_metrics.json
   │           │
   │           └─ Collects every 10 seconds (configurable)
   │
   └─ /proc/stat, /proc/meminfo, /proc/diskstats, etc.
```

### Scaling Decision Flow

```
JSON File → Model → Scaling Decision → API → Container
    │          │           │            │        │
    │          │           │            │        └─ pct set <vmid> -cores N
    │          │           │            │
    │          │           │            └─ POST /scale/cores
    │          │           │
    │          │           └─ CPU: Scale Up/Down/None
    │          │               RAM: Scale Up/Down/None
    │          │
    │          └─ IsolationForest prediction
    │
    └─ Historical metrics
```

## Async Batch Processing

The Model service uses async batch processing for fetching container configurations, providing significant performance improvements.

### Sequential (Old)

```
Container 1 ──▶ API ──▶ Response ──▶ Container 2 ──▶ API ──▶ Response ...
                                          │
                                          └─ Total: 60 containers × 100ms = 6s
```

### Concurrent (Current)

```
Container 1 ─┐
Container 2 ─┤
Container 3 ─┼──▶ API (parallel) ──▶ All Responses
...          │
Container 60─┘
                    │
                    └─ issued concurrently, bounded by api.max_concurrent
```

## Circuit Breaker Pattern

The circuit breaker prevents cascading failures when API endpoints fail.

```
Normal ────▶ Failure ────▶ Open ────▶ Half-Open ────▶ Normal
  │             │           │            │              │
  │             │           │            │              └─ Success: close
  │             │           │            │
  │             │           │            └─ After timeout: test one request
  │             │           │
  │             │           └─ Skip all requests (fail fast)
  │             │
  │             └─ Failures > threshold: open circuit
  │
  └─ All requests pass through
```

### Configuration

```yaml
circuit_breaker:
  enabled: true
  failure_threshold: 5   # Open after 5 consecutive failures
  timeout_seconds: 300   # Reset after 5 minutes
```

## File Locations

| File | Purpose |
|------|---------|
| `/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml` | API configuration |
| `/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml` | Model configuration |
| `/etc/lxc_autoscale_ml/lxc_monitor.yaml` | Monitor configuration |
| `/var/log/lxc_metrics.json` | Collected metrics |
| `/var/log/lxc_autoscale_ml.log` | Model service log |
| `/var/log/lxc_autoscale_api.log` | API service log |
| `/run/lxc_autoscale_ml.lock` | Process lock file |

## Next Steps

- [Configuration](/reference/configuration): Customize all settings
- [API Endpoints](/reference/api-endpoints): Complete API reference
- [Metrics](/reference/metrics): Prometheus metrics details
