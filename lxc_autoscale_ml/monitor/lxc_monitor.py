#!/usr/bin/env python3
"""Collects per-container metrics from a Proxmox node and exports them as JSON."""
import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from logging.handlers import RotatingFileHandler
from subprocess import CalledProcessError, check_output
from typing import Any

import aiofiles
import psutil
import yaml

CONFIG_PATH = "/etc/lxc_autoscale_ml/lxc_monitor.yaml"

logger = logging.getLogger("LXCMonitor")


class Settings:
    """Runtime configuration, populated by :func:`configure`.

    Previously these were module-level constants read at import time, which
    made the module impossible to import -- and therefore to test -- anywhere
    the config file did not exist.
    """

    export_file = "/var/log/lxc_metrics.json"
    check_interval = 60
    enable_swap = True
    enable_network = True
    enable_filesystem = True
    parallel_processing = True
    max_workers = 8
    excluded_devices = ('loop', 'dm-')
    retry_limit = 3
    retry_delay = 2
    max_metrics_entries = 1000


settings = Settings()

# Previous cumulative CPU counters per container, used to turn /proc/stat's
# since-boot totals into usage over the last interval.
_previous_cpu_sample: dict[str, tuple[int, int]] = {}


def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path) as config_file:
        return yaml.safe_load(config_file) or {}


def configure(config: dict) -> None:
    """Apply a parsed config file to logging and the module settings."""
    logging_config = config.get('logging', {})
    monitoring = config.get('monitoring', {})

    log_level = getattr(
        logging, str(logging_config.get('log_level', 'INFO')).upper(), logging.INFO)
    logger.setLevel(log_level)

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_file = logging_config.get('log_file')
    if log_file:
        # Size-based rotation: log_max_bytes was in the config but the previous
        # TimedRotatingFileHandler had no way to use it, so the setting did
        # nothing and a busy node could still fill the disk between midnights.
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=logging_config.get('log_max_bytes', 5 * 1024 * 1024),
            backupCount=logging_config.get('log_backup_count', 7),
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    settings.export_file = monitoring.get('export_file', Settings.export_file)
    settings.check_interval = monitoring.get('check_interval', Settings.check_interval)
    settings.enable_swap = monitoring.get('enable_swap', Settings.enable_swap)
    settings.enable_network = monitoring.get('enable_network', Settings.enable_network)
    settings.enable_filesystem = monitoring.get('enable_filesystem', Settings.enable_filesystem)
    settings.parallel_processing = monitoring.get(
        'parallel_processing', Settings.parallel_processing)
    settings.max_workers = monitoring.get('max_workers', Settings.max_workers)
    settings.excluded_devices = tuple(
        monitoring.get('excluded_devices', Settings.excluded_devices))
    settings.retry_limit = monitoring.get('retry_limit', Settings.retry_limit)
    settings.retry_delay = monitoring.get('retry_delay', Settings.retry_delay)
    settings.max_metrics_entries = monitoring.get(
        'max_metrics_entries', Settings.max_metrics_entries)


def get_running_lxc_containers() -> list[str]:
    """Retrieve the IDs of running LXC containers."""
    try:
        output = check_output(['pct', 'list'], text=True).splitlines()  # noqa: S603, S607
    except (CalledProcessError, OSError) as e:
        logger.error(f"Error retrieving LXC containers: {e}")
        return []

    containers = []
    for line in output[1:]:  # skip the header row
        fields = line.split()
        # Match on the status column rather than anywhere in the line: a
        # stopped container named "running-backup" used to be collected.
        if len(fields) >= 2 and fields[1] == 'running':
            containers.append(fields[0])
    return containers


def run_command(command: list[str]) -> str | None:
    """Run a command and return its stdout, or None if it failed."""
    try:
        return check_output(command, text=True)  # noqa: S603
    except (CalledProcessError, OSError) as e:
        logger.error(f"Command failed: {' '.join(command)}, error: {e}")
        return None


async def retry_on_failure(func: Any, *args, **kwargs) -> Any:
    """Retry a coroutine a few times, then give up and return None.

    Re-raising here used to propagate through asyncio.gather and abandon the
    metrics for every other container in the same cycle.
    """
    for attempt in range(settings.retry_limit):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.warning(
                f"Attempt {attempt + 1} failed for {func.__name__} with error: {e}")
            if attempt < settings.retry_limit - 1:
                await asyncio.sleep(settings.retry_delay)
            else:
                logger.error(f"All {settings.retry_limit} attempts failed for {func.__name__}.")
                return None


async def get_container_metric(command: list[str], executor: ThreadPoolExecutor) -> str | None:
    """Execute a command asynchronously in a worker thread."""
    return await asyncio.get_running_loop().run_in_executor(executor, run_command, command)


async def parse_meminfo(container_id: str, executor: ThreadPoolExecutor) -> dict[str, float]:
    """Retrieve memory and swap usage inside the container."""
    fields = [('MemTotal', 'memory_total_mb'), ('MemAvailable', 'memory_available_mb')]
    if settings.enable_swap:
        fields += [('SwapTotal', 'swap_total_mb'), ('SwapFree', 'swap_free_mb')]

    mem_info: dict[str, float] = {}
    for metric, key in fields:
        command = ['pct', 'exec', container_id, '--', 'grep', f'^{metric}:', '/proc/meminfo']
        result = await get_container_metric(command, executor)
        if not result:
            continue
        parts = result.split()
        if len(parts) < 2:
            logger.warning(f"Unexpected memory info format for container {container_id}: {result}")
            continue
        try:
            mem_info[key] = int(parts[1]) / 1024  # kB -> MB
        except ValueError:
            logger.warning(f"Unexpected memory info format for container {container_id}: {result}")

    # Without MemAvailable the old code reported the container's entire memory
    # as used, which reads as sustained pressure and drives constant scale-up.
    if 'memory_total_mb' in mem_info and 'memory_available_mb' in mem_info:
        mem_info['memory_usage_mb'] = max(
            0.0, mem_info['memory_total_mb'] - mem_info['memory_available_mb'])
    else:
        logger.warning(
            f"Incomplete memory info for container {container_id}; reporting 0 MB used")
        mem_info['memory_usage_mb'] = 0.0

    if 'swap_total_mb' in mem_info and 'swap_free_mb' in mem_info:
        mem_info['swap_usage_mb'] = max(
            0.0, mem_info['swap_total_mb'] - mem_info['swap_free_mb'])
    else:
        mem_info.setdefault('swap_total_mb', 0.0)
        mem_info['swap_usage_mb'] = 0.0

    return mem_info


async def get_container_cpu_usage(container_id: str, executor: ThreadPoolExecutor) -> float:
    """
    CPU usage of the container over the interval since the previous sample.

    /proc/stat holds counters accumulated since boot. Deriving usage from a
    single reading, as this used to, yields the average over the container's
    whole uptime: for a container up for days it barely moves, so the
    autoscaler was reacting to a number that had almost nothing to do with
    current load. Two readings are differenced instead.

    The first reading for a container has nothing to compare against and falls
    back to the since-boot average.
    """
    command = ['pct', 'exec', container_id, '--', 'grep', '^cpu ', '/proc/stat']
    result = await get_container_metric(command, executor)
    if not result:
        return 0.0

    fields = result.split()
    if len(fields) < 5:
        logger.warning(f"Unexpected CPU stat format for container {container_id}: {fields}")
        return 0.0

    try:
        values = [int(field) for field in fields[1:]]
    except ValueError:
        logger.warning(f"Unexpected CPU stat format for container {container_id}: {fields}")
        return 0.0

    idle_time = values[3]
    total_time = sum(values)
    if total_time <= 0:
        return 0.0

    previous = _previous_cpu_sample.get(container_id)
    _previous_cpu_sample[container_id] = (idle_time, total_time)

    if previous is None:
        logger.debug(
            f"No previous CPU sample for container {container_id}; "
            f"reporting the since-boot average for this cycle"
        )
        return 100.0 * (1 - (idle_time / total_time))

    previous_idle, previous_total = previous
    idle_delta = idle_time - previous_idle
    total_delta = total_time - previous_total

    if total_delta <= 0:
        # Counters did not advance, or the container restarted and reset them.
        logger.debug(f"CPU counters did not advance for container {container_id}")
        return 0.0

    usage = 100.0 * (1 - (idle_delta / total_delta))
    return max(0.0, min(100.0, usage))


async def get_container_io_stats(container_id: str, executor: ThreadPoolExecutor) -> dict[str, int]:
    """Retrieve I/O statistics inside the container."""
    command = ['pct', 'exec', container_id, '--', 'cat', '/proc/diskstats']
    result = await get_container_metric(command, executor)
    if not result:
        return {"reads": 0, "writes": 0}

    io_stats = {"reads": 0, "writes": 0}
    for line in result.splitlines():
        fields = line.split()
        if len(fields) < 10:
            continue
        device = fields[2]
        if any(device.startswith(exclude) for exclude in settings.excluded_devices):
            continue
        try:
            io_stats["reads"] += int(fields[5])
            io_stats["writes"] += int(fields[9])
        except ValueError:
            logger.warning(f"Unexpected disk stats format for container {container_id}: {fields}")
    return io_stats


async def get_container_network_usage(container_id: str, executor: ThreadPoolExecutor) -> dict[str, int]:
    """Retrieve network usage inside the container."""
    if not settings.enable_network:
        return {"rx_bytes": 0, "tx_bytes": 0}

    command = ['pct', 'exec', container_id, '--', 'cat', '/proc/net/dev']
    result = await get_container_metric(command, executor)
    if not result:
        return {"rx_bytes": 0, "tx_bytes": 0}

    rx_bytes, tx_bytes = 0, 0
    for line in result.splitlines()[2:]:  # skip the two header rows
        fields = line.split()
        if len(fields) < 10:
            continue
        iface = fields[0].split(':')[0]
        if iface == 'lo':
            continue
        try:
            rx_bytes += int(fields[1])
            tx_bytes += int(fields[9])
        except ValueError:
            logger.warning(f"Unexpected network stats format for container {container_id}: {fields}")
    return {"rx_bytes": rx_bytes, "tx_bytes": tx_bytes}


EMPTY_FILESYSTEM_STATS = {
    "filesystem_usage_gb": 0,
    "filesystem_total_gb": 0,
    "filesystem_free_gb": 0,
}


async def get_container_filesystem_usage(container_id: str, executor: ThreadPoolExecutor) -> dict[str, float]:
    """Retrieve filesystem usage inside the container."""
    if not settings.enable_filesystem:
        return dict(EMPTY_FILESYSTEM_STATS)

    command = ['pct', 'exec', container_id, '--', 'df', '-m', '/']
    result = await get_container_metric(command, executor)
    if not result:
        return dict(EMPTY_FILESYSTEM_STATS)

    lines = result.splitlines()
    if len(lines) < 2:
        logger.warning(f"Unexpected filesystem stats format for container {container_id}: {lines}")
        return dict(EMPTY_FILESYSTEM_STATS)

    stats = lines[1].split()
    if len(stats) < 4:
        logger.warning(f"Incomplete filesystem stats for container {container_id}: {stats}")
        return dict(EMPTY_FILESYSTEM_STATS)

    try:
        return {
            "filesystem_total_gb": int(stats[1]) / 1024,
            "filesystem_usage_gb": int(stats[2]) / 1024,
            "filesystem_free_gb": int(stats[3]) / 1024,
        }
    except ValueError:
        logger.warning(f"Unexpected filesystem stats format for container {container_id}: {stats}")
        return dict(EMPTY_FILESYSTEM_STATS)


async def get_container_process_count(container_id: str, executor: ThreadPoolExecutor) -> int:
    """Retrieve the number of processes running inside the container."""
    command = ['pct', 'exec', container_id, '--', 'ps', '-e']
    result = await get_container_metric(command, executor)
    if not result:
        return 0
    lines = result.splitlines()
    if lines and any(header in lines[0] for header in ["PID", "TTY", "TIME", "CMD"]):
        lines = lines[1:]  # drop the header row
    return len(lines)


async def collect_metrics_for_container(container_id: str, executor: ThreadPoolExecutor) -> tuple[str, dict[str, Any]]:
    """Collect all metrics for a given container."""
    logger.info(f"Collecting metrics for container: {container_id}")

    cpu_usage = await retry_on_failure(get_container_cpu_usage, container_id, executor)
    memory_swap_usage = await retry_on_failure(parse_meminfo, container_id, executor)
    io_stats = await retry_on_failure(get_container_io_stats, container_id, executor)
    network_usage = await retry_on_failure(get_container_network_usage, container_id, executor)
    filesystem_usage = await retry_on_failure(get_container_filesystem_usage, container_id, executor)
    process_count = await retry_on_failure(get_container_process_count, container_id, executor)

    # retry_on_failure returns None once it gives up; every consumer of this
    # record expects the full set of keys to be present.
    memory_swap_usage = memory_swap_usage or {}
    filesystem_usage = filesystem_usage or dict(EMPTY_FILESYSTEM_STATS)

    container_metrics = {
        "timestamp": datetime.now().isoformat(),
        "cpu_usage_percent": cpu_usage if cpu_usage is not None else 0.0,
        "memory_usage_mb": memory_swap_usage.get("memory_usage_mb", 0.0),
        "swap_usage_mb": memory_swap_usage.get("swap_usage_mb", 0.0),
        "swap_total_mb": memory_swap_usage.get("swap_total_mb", 0.0),
        "process_count": process_count if process_count is not None else 0,
        "io_stats": io_stats or {"reads": 0, "writes": 0},
        "network_usage": network_usage or {"rx_bytes": 0, "tx_bytes": 0},
        "filesystem_usage_gb": filesystem_usage["filesystem_usage_gb"],
        "filesystem_total_gb": filesystem_usage["filesystem_total_gb"],
        "filesystem_free_gb": filesystem_usage["filesystem_free_gb"],
    }

    logger.debug(f"Metrics for {container_id}: {container_metrics}")

    return container_id, container_metrics


async def collect_and_export_metrics():
    """Collect and export metrics for all running LXC containers."""
    start_time = datetime.now()
    metrics = {}
    containers = get_running_lxc_containers()

    if not containers:
        logger.info("No running LXC containers found.")
        return

    logger.debug(f"Found {len(containers)} running containers.")

    executor = ThreadPoolExecutor(max_workers=settings.max_workers)
    try:
        if settings.parallel_processing:
            tasks = [collect_metrics_for_container(cid, executor) for cid in containers]
            # return_exceptions keeps one unhealthy container from discarding
            # the metrics collected for every other container in the cycle.
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            results = []
            for container_id in containers:
                try:
                    results.append(await collect_metrics_for_container(container_id, executor))
                except Exception as e:  # noqa: BLE001 - recorded below, per container
                    results.append(e)
    finally:
        executor.shutdown(wait=True)

    for container_id, result in zip(containers, results, strict=True):
        if isinstance(result, BaseException):
            logger.error(f"Failed to collect metrics for container {container_id}: {result}")
            continue
        collected_id, container_metrics = result
        metrics[collected_id] = container_metrics

    if not metrics:
        logger.error("No container metrics were collected this cycle.")
        return

    end_time = datetime.now()
    metrics["summary"] = {
        "collection_start_time": start_time.isoformat(),
        "collection_end_time": end_time.isoformat(),
        "total_containers": len(containers),
        "collected_containers": len(metrics),
        "total_duration_seconds": (end_time - start_time).total_seconds(),
        "monitor_cpu_percent": psutil.cpu_percent(),
        "monitor_memory_usage_mb": psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024,
    }

    existing_data = await load_existing_data(settings.export_file)
    existing_data.append(metrics)

    logger.debug(f"Appending new metrics: {metrics}")

    await write_metrics_to_file(settings.export_file, existing_data)


async def load_existing_data(file_path: str) -> list[dict[str, Any]]:
    """Load existing data from the JSON file."""
    if not os.path.exists(file_path):
        return []

    try:
        async with aiofiles.open(file_path) as json_file:
            content = await json_file.read()
            data = json.loads(content)
            if not isinstance(data, list):
                logger.error(f"Data in {file_path} is not a list. Resetting to an empty list.")
                return []
            logger.debug(f"Loaded existing metrics from {file_path}.")
            return data
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to read existing data from {file_path}: {e}")
        return []


async def write_metrics_to_file(file_path: str, data: list[dict[str, Any]]):
    """
    Write metrics data to a JSON file asynchronously with size limiting.
    Keeps only the most recent max_metrics_entries to prevent unbounded growth.
    """
    if len(data) > settings.max_metrics_entries:
        removed = len(data) - settings.max_metrics_entries
        data = data[-settings.max_metrics_entries:]
        logger.info(
            f"Rotated metrics: removed {removed} old entries, "
            f"keeping last {settings.max_metrics_entries}"
        )

    temp_file = f"{file_path}.tmp"
    try:
        async with aiofiles.open(temp_file, mode='w') as json_file:
            await json_file.write(json.dumps(data, indent=4, sort_keys=True))
        os.replace(temp_file, file_path)
        logger.info(f"Metrics successfully exported to {file_path} ({len(data)} entries)")
    except OSError as e:
        logger.error(f"Failed to write metrics to {file_path}: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)


async def monitor_and_export():
    """Continuously monitor and export metrics at the defined intervals."""
    while True:
        logger.info("Starting new metrics collection cycle.")
        try:
            await collect_and_export_metrics()
        except Exception:
            # A failed cycle must not end the service: returning normally here
            # exited with status 0, which systemd's Restart=on-failure ignores,
            # so monitoring stopped silently and the model went stale.
            logger.exception("Metrics collection cycle failed; retrying at the next interval.")
        logger.info(f"Waiting for {settings.check_interval} seconds before the next cycle.")
        await asyncio.sleep(settings.check_interval)


def main():
    configure(load_config())
    try:
        asyncio.run(monitor_and_export())
    except KeyboardInterrupt:
        logger.info("Shutting down metrics collector due to KeyboardInterrupt.")


if __name__ == "__main__":
    main()
