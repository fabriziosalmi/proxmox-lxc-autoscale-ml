# Changelog

All notable changes to the LXC AutoScale ML project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed — the autoscaler could not work at all

Three independent defects each broke the scaling loop end to end. Together they
mean no released version of this project has ever successfully scaled a
container automatically.

1. **`/resource/*/config` always failed**
   ([Issue #14](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/issues/14)).
   The validation decorator read `request.json`, which aborts a request with no
   JSON body — the normal case for a GET. Older Flask reported 400, current
   Flask 415. The ML service polls this endpoint before every scaling decision.
2. **The scaling loop matched no containers.** `data_manager` produces string
   container IDs (they come from JSON object keys); the loop selected rows with
   `df["container_id"] == int(container_id)`, which matches nothing, so
   `.iloc[-1]` raised `IndexError` on the first container. The broad handler in
   `main()` caught it and the process exited — one cycle, nothing scaled, every
   time.
3. **CPU usage was the container's lifetime average.** `/proc/stat` holds
   counters accumulated since boot; the monitor read them once per cycle and
   computed `100 * (1 - idle/total)`. For a container up for days that value
   barely moves regardless of load. Two readings are now differenced.

### Fixed — commands that could never run

- **`/clone/delete` was broken twice over.** It first raised `NameError` from an
  undefined variable. Routing it to the deletion helper then landed on
  `"pct stop {id} && pct destroy {id}"` built as one string and passed through
  `shlex.split`, so `pct` received `&&` as a positional argument. `LXCManager`
  now builds argument lists and rejects string commands outright.
- **`get_current_disk_size` read the wrong field.** It took the second
  comma-separated part of the rootfs entry and assumed a `G` suffix, so
  `rootfs: local-lvm:vm-104-disk-0,acl=1,size=16G` returned nonsense. Sizes are
  looked up by name, with K/M/G/T handled.
- **Failed `pct` commands were reported as success.** `resource_checking`
  ignored the exit status and had no timeout.

### Fixed — things that lied

- **The health check could not fail.** It returned a hard-coded `healthy`
  including `"database": "connected"` for a component this project does not
  have. It now probes `pct list` and the configured node, and returns 503 when
  either is broken.
- **`notify_on_critical_error` logged "Notified {recipient}"** while sending
  nothing.
- **`/metrics` advertised metrics nothing populated.** Model-prediction,
  circuit-breaker and container-usage series belong to the ML service and the
  monitor, neither of which serves a metrics endpoint. Removed; a test now
  fails if a declared metric has no code path that fills it.
- **The metrics reference documented names that did not exist**
  (`lxc_circuit_breaker_state` vs `lxc_autoscale_circuit_breaker_state`, and so
  on). Rewritten from the actual definitions.

### Fixed — configuration that was read by nobody

Every one of these keys shipped in the default config file and had no effect:

| Key | Consequence |
|-----|-------------|
| `scaling.dry_run` | Anyone rehearsing a change with it was scaling for real |
| `ignore_lxc` | Containers could not be excluded |
| `scaling.min_confidence` | No confidence gating |
| `circuit_breaker.*` | Thresholds hard-coded |
| `log_level` | Config asks for DEBUG; logging stayed at INFO |
| `spike_detection.rolling_window` | Read from the top level, where it never exists |
| `monitoring.enable_swap` | Swap always collected |
| `logging.log_max_bytes` | A timed rotation handler cannot use it |
| `gunicorn.*` | The unit ran Flask's development server |
| `server.host` / `server.port` | Hard-coded |
| `api.timeout_seconds` / `api.max_concurrent` | Hard-coded |

`scaling.min_confidence` now defaults to `0` (no gating) rather than the `70`
the docs claimed, because the confidence value it compares against was itself
wrong: `(1 - decision_function) * 100` yields roughly 50–150%, never below 50
and not bounded by 100. Confidence is now the distance from the decision
boundary mapped onto 0–100.

### Fixed — services that died quietly

Both daemons ended their loop on an unexpected error and returned normally,
exiting with status 0. systemd's `Restart=on-failure` ignores a clean exit, so
the service stayed dead and the ML model went on training against a metrics
file that never updated again. Both now log the failure and continue at the
next interval, and one bad container no longer abandons the rest of the fleet.

### Fixed — other correctness and robustness

- The rate limiter held its global lock while running the request handler,
  serialising the whole API behind the slowest `pct` call.
- `apply_scaling` read `response.status_code` inside its own `except` block; on
  a connection error no response exists, so the handler raised
  `UnboundLocalError` and masked the API being unreachable. Requests now have a
  timeout.
- The single-instance lock checked `os.path.exists()` and opened the file
  afterwards, so two instances starting together could both proceed to scale
  the same containers. Now `O_CREAT | O_EXCL`. A lock whose owner returns
  `PermissionError` is treated as live, not stale.
- The lock moved out of world-writable `/tmp` to `/run`.
- Dividing by `process_count` or memory produced `inf` for a container
  reporting zero of either, which `StandardScaler` turns into `NaN` and
  `IsolationForest` refuses to fit on.
- `np.polyfit` raised on a single-sample group and left the caller with a
  half-transformed frame.
- Missing `MemAvailable` made memory usage equal the container's entire
  allocation — indistinguishable from real pressure, and a direct push towards
  scale-up.
- Container listing matched `running` anywhere in the line, so a stopped
  container named e.g. `running-backup` was collected.
- Endpoints returned 500 instead of 400 for missing or malformed parameters.
- `/resource/node/status` passed an unvalidated node name into a `pvesh` path.
- Numeric validators raised `OverflowError` (→ 500) on a float infinity.
- API key authentication was imported and never applied; the config section had
  no effect. `/metrics` was implemented but had no route.
- `/clone/create` leaked its temporary snapshot when the clone or start failed,
  and cleanup failures could mask the error that broke the clone.
- Log files were never rotated by either service.
- `install.sh` overwrote existing configuration on upgrade; `uninstall.sh`
  deleted it outright. The first now writes shipped defaults to
  `<name>.yaml.new`, the second backs the configuration up to `/root` first.
- `create_app()` crashed on a config file missing optional sections.
- Chained `fillna(inplace=True)` stops working under pandas copy-on-write.

### Added

- **`/resource/lxc/*` endpoints and `lxc_id` parameters.** These objects are LXC
  containers, not VMs. The `vm` spellings keep working. Picks up the intent of
  [PR #15](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/pull/15) by
  [@deswong](https://github.com/deswong) without breaking existing deployments.
- **`/resource/cluster/status`**, which had an implementation but no route.
- **Gunicorn** replaces the Flask development server, configured from the
  `gunicorn` section that already existed. It defaults to one worker with
  several threads: the rate limiter and the Prometheus counters live in process
  memory, so extra worker processes would multiply the effective rate limit and
  split `/metrics`.
- **A test suite** — 204 tests over the routes, validators, authentication,
  rate limiting, configuration, the `pct` wrapper, the data pipeline, the
  confidence mapping, the scaling loop, the metrics collector and the lock. The
  project had none.
- **CI**: ruff, pytest on Python 3.10/3.11/3.12, a dependency-resolution job
  and shellcheck over the install scripts.
- **Dependabot configuration** for pip, the docs npm tree and workflow actions.

### Changed

- **The supported Python range is now stated: 3.10 to 3.12.** The floor comes
  from the pinned `requests`, which requires 3.10, so the previously documented
  "Python 3.x" was never accurate. The ceiling comes from the pinned `numpy`,
  `pandas` and `scikit-learn`, which have no 3.13 wheels -- meaning the ML
  component will not install on Proxmox VE 9 (Debian 13) until those pins are
  raised. The API and the monitor are unaffected.
- The API index page is generated from the route table and no longer loads
  Bootstrap and jQuery from public CDNs.
- `model/scaling.py` is renamed `model/scaling_decisions.py`: it collided with
  `api/scaling.py` in a flat module namespace, which is why the ML side could
  not be tested. Both are installed into separate directories, so deployments
  are unaffected.
- Flask 3.0.0 → 3.1.3.
- The configuration reference now matches the shipped YAML.

## [1.2.0] - 2025-12-24

Major release with critical bug fixes, performance improvements, and new enterprise features.

### 🎉 Highlights

- **10x Performance**: Batch async API calls for concurrent container config fetching
- **Enterprise Security**: API key authentication, rate limiting, input validation
- **Fixed Critical Bugs**: Scaling logic, RAM threshold, IsolationForest interpretation
- **Production Ready**: Circuit breaker, stale lock cleanup, metrics export

### Added

#### API Component
- **API Key Authentication** ([`authentication.py`](lxc_autoscale_ml/api/authentication.py))
  - Secure all endpoints with `X-API-Key` header or query parameter
  - Constant-time comparison to prevent timing attacks
  - Configurable in `lxc_autoscale_api.yaml`
  - Health check and metrics endpoints remain public

- **Enhanced Rate Limiting** ([`rate_limiting.py`](lxc_autoscale_ml/api/rate_limiting.py))
  - Localhost bypass for internal services (fixes [Issue #3](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/issues/3))
  - Increased limit from 60 to 120 requests/minute
  - Per-IP tracking with sliding window algorithm
  - Informative headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`
  - Detailed error responses with retry guidance

- **Input Validation** ([`validation.py`](lxc_autoscale_ml/api/validation.py))
  - Comprehensive parameter validation on all endpoints
  - Prevents injection attacks and invalid operations
  - Clear error messages for debugging
  - Validation rules:
    - `vm_id`: 100-999999
    - `cores`: 1-128
    - `memory`: 64MB-1TB
    - `disk_size`: Positive integer
    - `snapshot_name`: Alphanumeric, max 100 chars

- **Prometheus Metrics Export** ([`metrics.py`](lxc_autoscale_ml/api/metrics.py))
  - `/metrics` endpoint for Prometheus scraping
  - Tracks scaling actions, API requests, container resources
  - Circuit breaker status and model predictions
  - Graceful degradation if prometheus-client not installed

- **New Endpoint: `/resource/vm/config`**
  - Fetch min/max CPU and RAM limits for containers
  - Used by ML model for batch config fetching
  - Returns current resource boundaries

#### Model Component
- **Batch Async API Client** ([`async_api_client.py`](lxc_autoscale_ml/model/async_api_client.py))
  - Concurrent API requests using `asyncio` and `aiohttp`
  - **10x faster** than sequential requests (60 containers in 0.6s vs 6s)
  - Connection pooling with configurable concurrency (default: 10)
  - Smart retry with exponential backoff (1s, 2s, 4s)
  - Timeout protection (5 seconds per request)
  - Graceful degradation on failures

- **Circuit Breaker Pattern** ([`lxc_autoscale_ml.py`](lxc_autoscale_ml/model/lxc_autoscale_ml.py))
  - Automatically skip failed API endpoints
  - Prevents cascading failures and wasted cycles
  - Configurable threshold (default: 5 failures) and timeout (default: 5 minutes)
  - Auto-recovery after timeout period

- **Incremental Scaling** ([`scaling.py`](lxc_autoscale_ml/model/scaling.py))
  - Scale gradually instead of jumping to extremes
  - CPU: ±1 core per cycle (configurable via `cpu_scale_step`)
  - RAM: ±512MB per cycle (configurable via `ram_scale_step_mb`)
  - Prevents resource waste and system instability

- **Stale Lock Cleanup** ([`lock_manager.py`](lxc_autoscale_ml/model/lock_manager.py))
  - Automatic recovery from service crashes
  - PID checking with `os.kill(pid, 0)`
  - Logs lock age before removal
  - No more manual lock file deletion needed

- **Config Validation** ([`config_manager.py`](lxc_autoscale_ml/model/config_manager.py))
  - Validates scaling configuration on startup
  - Checks min < max, thresholds in valid ranges
  - Provides clear error messages for misconfigurations

#### Monitor Component
- **Automatic Metrics File Size Limiting** ([`lxc_monitor.py`](lxc_autoscale_ml/monitor/lxc_monitor.py))
  - Limits metrics file to 1000 entries (configurable)
  - Prevents memory exhaustion on long-running systems
  - Automatically removes oldest entries
  - Maintains constant file size (~2MB)

#### Documentation
- **[BUGFIX_SCALING_ISSUE_6.md](BUGFIX_SCALING_ISSUE_6.md)** - Detailed explanation of critical scaling bug fixes
- **[QUICKWINS_80_20.md](QUICKWINS_80_20.md)** - High-impact optimizations following 80/20 principle
- **[FIXES_ISSUES_3_4.md](FIXES_ISSUES_3_4.md)** - Resolution of year-old rate limiting and config issues
- **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** - Comprehensive troubleshooting guide
- Updated README with all new features and security information
- Complete API, Model, and Monitor documentation rewrites

#### Dependencies
- **[requirements.txt](requirements.txt)** - Complete dependency list
  - `aiohttp==3.9.1` - Async HTTP client
  - `prometheus-client` (optional) - Metrics export
  - All existing dependencies with version pins

### Fixed

#### Critical Bugs (Issue #6)

1. **IsolationForest Prediction Interpretation** ([`lxc_autoscale_ml.py`](lxc_autoscale_ml/model/lxc_autoscale_ml.py))
   - **Bug**: Treated any truthy value as anomaly
   - **Impact**: `prediction=1` (normal) triggered scale up!
   - **Fix**: Check for `-1` specifically (anomaly)
   - **Result**: Correct anomaly detection

2. **Always Jumping to Max/Min Resources** ([`scaling.py`](lxc_autoscale_ml/model/scaling.py))
   - **Bug**: Scaled directly to `max_cpu_cores` or `min_cpu_cores`
   - **Impact**: 2 cores → 8 cores in one step, wasting resources
   - **Fix**: Incremental scaling with step sizes
   - **Result**: Gradual resource adjustment

3. **RAM Threshold Comparison** ([`scaling.py`](lxc_autoscale_ml/model/scaling.py))
   - **Bug**: Compared MB value to percentage threshold (e.g., 4096 MB > 80%)
   - **Impact**: RAM scaling never triggered or always triggered
   - **Fix**: Calculate percentage: `(usage_mb / current_ram_mb) * 100`
   - **Result**: Accurate RAM threshold checks

#### Year-Old Issues

4. **Rate Limiting Too Aggressive** (Issue #3)
   - **Bug**: ML service rate limited after 10-15 containers
   - **Impact**: 429 errors prevented scaling large deployments
   - **Fix**: 
     - Localhost bypass for internal services
     - Increased limit from 60 to 120 req/min
     - Better error messages and headers
   - **Result**: Unlimited containers for ML service, protected API for external clients

5. **Default Config Ignores 101/102** (Issue #4)
   - **Bug**: Default `ignore_lxc` contained most common container IDs
   - **Impact**: New users got zero scaling out-of-the-box
   - **Fix**: Empty default ignore list with clear documentation
   - **Result**: Works immediately for new installations

### Changed

#### API
- Rate limit increased from 60 to 120 requests/minute
- All endpoints now require authentication (except `/health/check` and `/metrics`)
- Error responses now include detailed troubleshooting information

#### Model
- Default `ignore_lxc` changed from `["101", "102"]` to `[]`
- Scaling logic now uses step sizes instead of jumping to limits
- API calls now batched and concurrent instead of sequential

#### Configuration
- Added `cpu_scale_step` parameter (default: 1)
- Added `ram_scale_step_mb` parameter (default: 512)
- Added `authentication` section in API config
- Added `circuit_breaker` section in ML config
- Added `max_entries` parameter in monitor config (default: 1000)

### Performance

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **60 containers config fetch** | ~6s | ~0.6s | **10x faster** |
| **100 containers config fetch** | ~10s | ~1.0s | **10x faster** |
| **Max containers before 429** | 10-15 | Unlimited | ∞ |
| **Metrics file size** | Unlimited | ~2MB | Bounded |
| **Scaling granularity** | Max jump | ±1 core, ±512MB | Gradual |

### Security

- ✅ API key authentication on all sensitive endpoints
- ✅ Rate limiting with per-IP tracking
- ✅ Input validation prevents injection attacks
- ✅ Constant-time API key comparison
- ✅ Localhost exemption for internal services
- ✅ Security headers in all responses

### Deprecated

- None

### Removed

- Removed placeholder `if True:` blocks in scaling logic
- Removed hardcoded 101/102 from default ignore list

### Known Issues

- None critical - all reported issues resolved

---

## [1.0.0] - 2024-08-20

Initial release with basic autoscaling functionality.

### Added
- IsolationForest ML model for anomaly detection
- Basic API for container management
- Monitor service for metrics collection
- Sequential container processing
- Basic logging and error handling
- Configuration via YAML files

### Known Issues
- Scaling only increases to maximum (Issue #6)
- Rate limiting too aggressive for large deployments (Issue #3)
- Default config ignores common container IDs (Issue #4)

---

## How to Upgrade

### From 1.x to 2.0

1. **Backup your configuration**:
```bash
cp /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml /etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml.backup
cp /etc/lxc_autoscale_ml/lxc_autoscale_api.yaml /etc/lxc_autoscale_ml/lxc_autoscale_api.yaml.backup
```

2. **Install new dependencies**:
```bash
pip3 install aiohttp==3.9.1
# Optional: pip3 install prometheus-client
```

3. **Update configuration files** (see documentation for details):
```yaml
# lxc_autoscale_api.yaml - Add authentication
authentication:
  enabled: true
  api_key: "your-secret-key-here"

# lxc_autoscale_api.yaml - Update rate limiting
rate_limiting:
  max_requests_per_minute: 120  # Was 60

# lxc_autoscale_ml.yaml - Add step sizes
scaling:
  cpu_scale_step: 1
  ram_scale_step_mb: 512

# lxc_autoscale_ml.yaml - Fix ignore list
ignore_lxc: []  # Was ["101", "102"]

# lxc_autoscale_ml.yaml - Add circuit breaker
circuit_breaker:
  enabled: true
  failure_threshold: 5
  timeout_seconds: 300

# lxc_monitor.yaml - Add size limiting
metrics:
  max_entries: 1000
```

4. **Restart services**:
```bash
systemctl restart lxc_autoscale_api
systemctl restart lxc_autoscale_ml
systemctl restart lxc_monitor
```

5. **Verify**:
```bash
# Check services
systemctl status lxc_autoscale_api
systemctl status lxc_autoscale_ml
systemctl status lxc_monitor

# Test API authentication
curl -H "X-API-Key: your-secret-key-here" http://127.0.0.1:5000/health/check

# Monitor logs for batch fetch performance
journalctl -u lxc_autoscale_ml -f | grep "Batch fetch"
```

---

## Migration Guide

### API Clients

If you have scripts or tools calling the API, update them to include authentication:

**Before**:
```bash
curl http://proxmox:5000/resource/vm/status?vm_id=104
```

**After**:
```bash
curl -H "X-API-Key: your-secret-key-here" \
  http://proxmox:5000/resource/vm/status?vm_id=104
```

### Monitoring

If you're monitoring the `/health/check` endpoint, it still works without authentication. For Prometheus metrics:

```bash
# No authentication needed for /metrics
curl http://proxmox:5000/metrics
```

### Rate Limiting

If you were hitting rate limits:
- Internal services (localhost): Now unlimited
- External clients: Limit increased to 120/min
- Check `X-RateLimit-Remaining` header to monitor usage

---

## Support

- **Documentation**: [docs/](docs/)
- **Issues**: [GitHub Issues](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/issues)
- **Troubleshooting**: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

---

**Thank you for using LXC AutoScale ML!** 🎉
