# Bug Fix: Scaling Only Increases to Maximum (Issue #6)

## Problem Description

The autoscaling system was exhibiting the following behavior:
- Containers were always being scaled UP to maximum allowed resources
- Scale DOWN actions were never triggered, even when containers had very low resource utilization
- Example: Container 113 with only 5.7% CPU usage and 497 MB RAM was being scaled to 8 CPU cores and 20480 MB RAM

## Root Causes Identified

### 1. **Incorrect IsolationForest Prediction Interpretation**
**Location:** `lxc_autoscale_ml/model/scaling.py` (lines 30-34)

**Problem:**
```python
if scaling_decision:
    logging.debug("Anomaly detected. Scaling up CPU and RAM.")
    cpu_action = "Scale Up"
    ram_action = "Scale Up"
```

**Issue:** IsolationForest returns:
- `-1` for anomalies (outliers that might need attention)
- `1` for normal data points

The code was treating truthy values (which includes `1`) as a signal to scale up, when in fact `-1` indicates anomalies.

**Fix:** Corrected the logic to properly interpret IsolationForest predictions and rely primarily on threshold-based scaling rather than automatically scaling up on anomalies.

### 2. **Always Jumping to Min/Max Values Instead of Incremental Scaling**
**Location:** `lxc_autoscale_ml/model/scaling.py` (lines 51-61)

**Problem:**
```python
if cpu_action == "Scale Up":
    new_cores = min(cpu_thresholds["total_cores"], cpu_thresholds["max_cpu_cores"])
elif cpu_action == "Scale Down":
    new_cores = max(cpu_thresholds["min_cpu_cores"], cpu_thresholds["min_cpu_cores"])
```

**Issues:**
- Scale Up: Always set to the maximum allowed cores (not incremental)
- Scale Down: `max(min_cpu_cores, min_cpu_cores)` always equals `min_cpu_cores` - logic error
- Same bugs existed for RAM scaling
- No consideration of current resource allocation

**Fix:** Implemented proper incremental scaling:
```python
# Get current resources
current_cores = latest_metrics.get("current_cores", cpu_thresholds.get("min_cpu_cores", 2))
current_ram = latest_metrics.get("current_ram_mb", ram_thresholds.get("min_ram_mb", 1024))

# Calculate incremental changes
cpu_step = cpu_thresholds.get("cpu_scale_step", 1)
ram_step = ram_thresholds.get("ram_scale_step_mb", 512)

# Apply incremental scaling
if cpu_action == "Scale Up":
    new_cores = min(current_cores + cpu_step, cpu_thresholds["max_cpu_cores"])
elif cpu_action == "Scale Down":
    new_cores = max(current_cores - cpu_step, cpu_thresholds["min_cpu_cores"])
```

### 3. **Missing Current Resource Information**
**Problem:** The system had no way to know the current CPU/RAM allocation of containers, making incremental scaling impossible.

**Fix:** 
- Added `get_current_resources()` method to `LXCManager` class
- Added new API endpoint `/resource/vm/config` to retrieve current container configuration
- Updated ML script to fetch and include current resource allocation in metrics

## Changes Made

### 1. `lxc_autoscale_ml/model/scaling.py`
- Fixed IsolationForest prediction interpretation
- Implemented incremental scaling logic with configurable step sizes
- Added current resource tracking in scaling calculations

### 2. `lxc_autoscale_ml/api/lxc_management.py`
- Added `get_current_resources(vm_id)` method to retrieve current CPU cores and RAM

### 3. `lxc_autoscale_ml/api/lxc_autoscale_api.py`
- Added `/resource/vm/config` GET endpoint to expose container configuration

### 4. `lxc_autoscale_ml/model/lxc_autoscale_ml.py`
- Updated to fetch current container resources from API before making scaling decisions
- Added error handling for API calls with fallback to default values

### 5. `lxc_autoscale_ml/model/lxc_autoscale_ml.yaml`
- Added `cpu_scale_step: 1` - cores to add/remove per scaling action
- Added `ram_scale_step_mb: 512` - MB to add/remove per scaling action

## New Configuration Parameters

```yaml
scaling:
  cpu_scale_step: 1              # Number of CPU cores to add/remove per scaling action
  ram_scale_step_mb: 512         # Amount of RAM in MB to add/remove per scaling action
```

## Expected Behavior After Fix

1. **Incremental Scaling:** Resources will scale up/down gradually by the configured step sizes
2. **Proper Scale Down:** Containers with low utilization will scale down appropriately
3. **Threshold-Based Logic:** Scaling primarily driven by CPU/RAM usage thresholds
4. **Anomaly Awareness:** IsolationForest anomalies inform decisions but don't override threshold logic

## Example Scenarios

### Before Fix:
- Container at 5.7% CPU, 497 MB RAM
- System scales to: 8 cores (max), 20480 MB (max)

### After Fix:
- Container at 5.7% CPU, 497 MB RAM
- System detects usage below scale_down_threshold (30%)
- Scales down by 1 core and 512 MB incrementally
- Continues until minimum or utilization increases

## Testing Recommendations

1. **Monitor containers with low utilization** to verify scale-down occurs
2. **Check incremental scaling** - resources should change by step amounts, not jump to max/min
3. **Verify thresholds** are appropriate for your workload:
   - `cpu_scale_up_threshold: 75` (default)
   - `cpu_scale_down_threshold: 30` (default)
   - `ram_scale_up_threshold: 75` (default)
   - `ram_scale_down_threshold: 30` (default)
4. **Adjust step sizes** based on your container requirements:
   - Smaller steps for fine-grained control
   - Larger steps for faster response to load changes

## Rollback Instructions

If issues arise, you can rollback by:
1. Restoring previous versions of modified files
2. Restarting both API and ML services:
   ```bash
   systemctl restart lxc_autoscale_api
   systemctl restart lxc_autoscale_ml
   ```

## Additional Notes

- The new `/resource/vm/config` API endpoint requires the LXC AutoScale API to be running
- If the API is unavailable, the system will fall back to using configured minimum values
- Consider adjusting `interval_seconds` (default: 600) to control how frequently scaling decisions are made
- Enable DEBUG logging to see detailed scaling decision information:
  ```yaml
  log_level: "DEBUG"
  ```

## Related Issue

Fixes: https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/issues/6
