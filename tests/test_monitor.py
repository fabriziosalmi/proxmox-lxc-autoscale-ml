"""Tests for the metrics collector."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

import lxc_monitor
from lxc_monitor import Settings


@pytest.fixture(autouse=True)
def reset_settings():
    """Each test starts from the built-in defaults."""
    for name in dir(Settings):
        if not name.startswith("_"):
            setattr(lxc_monitor.settings, name, getattr(Settings, name))
    lxc_monitor._previous_cpu_sample.clear()
    yield
    lxc_monitor._previous_cpu_sample.clear()


@pytest.fixture
def executor():
    pool = ThreadPoolExecutor(max_workers=2)
    yield pool
    pool.shutdown(wait=True)


@pytest.fixture
def pct_exec(monkeypatch):
    """Stub `pct exec` output, keyed by the file being read."""
    outputs = {}

    def fake_run_command(command):
        for key, value in outputs.items():
            if key in command:
                return value() if callable(value) else value
        return None

    monkeypatch.setattr(lxc_monitor, "run_command", fake_run_command)
    return outputs


def stat_line(idle, other=0):
    """A /proc/stat cpu line: user nice system idle iowait irq softirq."""
    return f"cpu  {other} 0 0 {idle} 0 0 0\n"


class TestConfigure:
    def test_module_imports_without_a_config_file(self):
        """The config used to be read at import time, so the module could not
        be imported -- or tested -- anywhere the file was absent."""
        assert lxc_monitor.settings.check_interval == 60

    def test_applies_the_monitoring_section(self):
        lxc_monitor.configure({"monitoring": {
            "check_interval": 15,
            "max_workers": 2,
            "excluded_devices": ["sr"],
            "enable_network": False,
        }})
        assert lxc_monitor.settings.check_interval == 15
        assert lxc_monitor.settings.max_workers == 2
        assert lxc_monitor.settings.excluded_devices == ("sr",)
        assert lxc_monitor.settings.enable_network is False

    def test_uses_a_size_based_rotating_handler(self, tmp_path):
        from logging.handlers import RotatingFileHandler

        log_file = tmp_path / "monitor.log"
        lxc_monitor.configure({"logging": {
            "log_file": str(log_file), "log_max_bytes": 1024, "log_backup_count": 3,
        }})
        rotating = [h for h in lxc_monitor.logger.handlers
                    if isinstance(h, RotatingFileHandler)]
        assert len(rotating) == 1
        # log_max_bytes was in the config but the previous timed handler could
        # not use it.
        assert rotating[0].maxBytes == 1024
        assert rotating[0].backupCount == 3

    def test_repeated_configuration_does_not_duplicate_handlers(self, tmp_path):
        for _ in range(3):
            lxc_monitor.configure({"logging": {"log_file": str(tmp_path / "m.log")}})
        assert len(lxc_monitor.logger.handlers) == 2  # console + file


class TestContainerListing:
    def test_parses_the_status_column(self, monkeypatch):
        output = (
            "VMID       Status     Lock         Name\n"
            "104        running                 web\n"
            "105        stopped                 db\n"
        )
        monkeypatch.setattr(lxc_monitor, "check_output", lambda *a, **kw: output)
        assert lxc_monitor.get_running_lxc_containers() == ["104"]

    def test_a_stopped_container_named_running_is_not_collected(self, monkeypatch):
        """The old check was `'running' in line`, which matched the name."""
        output = (
            "VMID       Status     Lock         Name\n"
            "106        stopped                 running-backup\n"
        )
        monkeypatch.setattr(lxc_monitor, "check_output", lambda *a, **kw: output)
        assert lxc_monitor.get_running_lxc_containers() == []

    def test_missing_pct_is_handled(self, monkeypatch):
        def boom(*a, **kw):
            raise FileNotFoundError(2, "No such file or directory", "pct")

        monkeypatch.setattr(lxc_monitor, "check_output", boom)
        assert lxc_monitor.get_running_lxc_containers() == []


class TestCpuUsage:
    def test_first_sample_falls_back_to_the_since_boot_average(self, pct_exec, executor):
        # 25 idle out of 100 total -> 75% since boot.
        pct_exec["/proc/stat"] = stat_line(idle=25, other=75)
        usage = asyncio.run(lxc_monitor.get_container_cpu_usage("104", executor))
        assert usage == pytest.approx(75.0)

    def test_second_sample_measures_only_the_interval(self, pct_exec, executor):
        """/proc/stat holds since-boot counters. Deriving usage from a single
        reading reports the container's lifetime average, not current load."""
        # Long-idle container: 10 busy, 990 idle since boot (1% average).
        pct_exec["/proc/stat"] = stat_line(idle=990, other=10)
        first = asyncio.run(lxc_monitor.get_container_cpu_usage("104", executor))
        assert first == pytest.approx(1.0)

        # In the last interval it was fully busy: +100 busy, +0 idle.
        pct_exec["/proc/stat"] = stat_line(idle=990, other=110)
        second = asyncio.run(lxc_monitor.get_container_cpu_usage("104", executor))
        assert second == pytest.approx(100.0)

    def test_idle_interval_reports_zero(self, pct_exec, executor):
        pct_exec["/proc/stat"] = stat_line(idle=100, other=100)
        asyncio.run(lxc_monitor.get_container_cpu_usage("104", executor))
        pct_exec["/proc/stat"] = stat_line(idle=200, other=100)
        assert asyncio.run(lxc_monitor.get_container_cpu_usage("104", executor)) == 0.0

    def test_samples_are_tracked_per_container(self, pct_exec, executor):
        pct_exec["/proc/stat"] = stat_line(idle=100, other=100)
        asyncio.run(lxc_monitor.get_container_cpu_usage("104", executor))
        # A different container has no history yet and must not reuse 104's.
        assert "105" not in lxc_monitor._previous_cpu_sample
        pct_exec["/proc/stat"] = stat_line(idle=50, other=150)
        assert asyncio.run(
            lxc_monitor.get_container_cpu_usage("105", executor)) == pytest.approx(75.0)

    def test_counter_reset_after_a_restart_is_handled(self, pct_exec, executor):
        pct_exec["/proc/stat"] = stat_line(idle=1000, other=1000)
        asyncio.run(lxc_monitor.get_container_cpu_usage("104", executor))
        pct_exec["/proc/stat"] = stat_line(idle=1, other=1)  # counters reset
        assert asyncio.run(lxc_monitor.get_container_cpu_usage("104", executor)) == 0.0

    def test_result_is_always_a_percentage(self, pct_exec, executor):
        pct_exec["/proc/stat"] = stat_line(idle=100, other=100)
        asyncio.run(lxc_monitor.get_container_cpu_usage("104", executor))
        pct_exec["/proc/stat"] = stat_line(idle=90, other=210)  # idle went backwards
        usage = asyncio.run(lxc_monitor.get_container_cpu_usage("104", executor))
        assert 0.0 <= usage <= 100.0

    def test_unreadable_stat_returns_zero(self, pct_exec, executor):
        pct_exec["/proc/stat"] = "cpu garbage\n"
        assert asyncio.run(lxc_monitor.get_container_cpu_usage("104", executor)) == 0.0


class TestMemory:
    def test_usage_is_total_minus_available(self, pct_exec, executor):
        pct_exec["/proc/meminfo"] = lambda: TestMemory.meminfo.pop(0)
        TestMemory.meminfo = [
            "MemTotal:       2097152 kB\n",
            "MemAvailable:   1048576 kB\n",
            "SwapTotal:       524288 kB\n",
            "SwapFree:        524288 kB\n",
        ]
        info = asyncio.run(lxc_monitor.parse_meminfo("104", executor))
        assert info["memory_usage_mb"] == pytest.approx(1024.0)
        assert info["swap_usage_mb"] == pytest.approx(0.0)

    def test_missing_available_does_not_report_everything_as_used(self, pct_exec, executor):
        """Previously MemTotal minus a missing MemAvailable reported the whole
        allocation as used, which reads as pressure and drives scale-up."""
        pct_exec["/proc/meminfo"] = lambda: TestMemory.meminfo.pop(0)
        TestMemory.meminfo = ["MemTotal: 2097152 kB\n", "", "", ""]
        info = asyncio.run(lxc_monitor.parse_meminfo("104", executor))
        assert info["memory_usage_mb"] == 0.0

    def test_swap_can_be_disabled(self, pct_exec, executor):
        lxc_monitor.settings.enable_swap = False
        pct_exec["/proc/meminfo"] = lambda: TestMemory.meminfo.pop(0)
        TestMemory.meminfo = ["MemTotal: 2097152 kB\n", "MemAvailable: 1048576 kB\n"]
        info = asyncio.run(lxc_monitor.parse_meminfo("104", executor))
        assert info["swap_usage_mb"] == 0.0
        assert TestMemory.meminfo == []  # swap was never queried


class TestResilience:
    def test_retry_gives_up_without_raising(self, executor, monkeypatch):
        """Re-raising propagated through asyncio.gather and discarded the
        metrics of every other container in the cycle."""
        lxc_monitor.settings.retry_limit = 2
        lxc_monitor.settings.retry_delay = 0
        attempts = []

        async def always_fails(*args, **kwargs):
            attempts.append(1)
            raise RuntimeError("pct exec failed")

        result = asyncio.run(lxc_monitor.retry_on_failure(always_fails, "104", executor))
        assert result is None
        assert len(attempts) == 2

    def test_one_broken_container_does_not_lose_the_others(self, monkeypatch, tmp_path):
        export_file = tmp_path / "metrics.json"
        lxc_monitor.settings.export_file = str(export_file)
        monkeypatch.setattr(
            lxc_monitor, "get_running_lxc_containers", lambda: ["104", "105"])

        async def collect(container_id, executor):
            if container_id == "104":
                raise RuntimeError("container is unreachable")
            return container_id, {"cpu_usage_percent": 5.0}

        monkeypatch.setattr(lxc_monitor, "collect_metrics_for_container", collect)
        asyncio.run(lxc_monitor.collect_and_export_metrics())

        written = json.loads(export_file.read_text())
        assert "105" in written[0]
        assert "104" not in written[0]
        assert written[0]["summary"]["collected_containers"] == 1

    def test_metrics_record_is_complete_even_when_probes_fail(self, monkeypatch, executor):
        """Consumers index these keys directly; a None from a failed retry used
        to reach the record."""
        async def give_up(*args, **kwargs):
            return None

        monkeypatch.setattr(lxc_monitor, "retry_on_failure", give_up)
        _, metrics = asyncio.run(lxc_monitor.collect_metrics_for_container("104", executor))
        for key in ["cpu_usage_percent", "memory_usage_mb", "swap_usage_mb",
                    "swap_total_mb", "process_count", "io_stats", "network_usage",
                    "filesystem_usage_gb", "filesystem_total_gb", "filesystem_free_gb"]:
            assert metrics[key] is not None

    def test_a_failed_cycle_does_not_end_the_service(self, monkeypatch):
        """Returning from the loop exited with status 0, which systemd's
        Restart=on-failure ignores, so monitoring stopped silently."""
        lxc_monitor.settings.check_interval = 0
        cycles = []

        async def failing_cycle():
            cycles.append(1)
            if len(cycles) >= 3:
                raise KeyboardInterrupt
            raise RuntimeError("collection blew up")

        monkeypatch.setattr(lxc_monitor, "collect_and_export_metrics", failing_cycle)
        with pytest.raises(KeyboardInterrupt):
            asyncio.run(lxc_monitor.monitor_and_export())
        assert len(cycles) == 3  # kept going after the first two failures


class TestExport:
    def test_entries_are_capped(self, tmp_path):
        export_file = tmp_path / "metrics.json"
        lxc_monitor.settings.max_metrics_entries = 5
        asyncio.run(lxc_monitor.write_metrics_to_file(
            str(export_file), [{"n": i} for i in range(20)]))
        written = json.loads(export_file.read_text())
        assert len(written) == 5
        assert written[0]["n"] == 15

    def test_corrupt_existing_file_is_ignored(self, tmp_path):
        export_file = tmp_path / "metrics.json"
        export_file.write_text("{not json")
        assert asyncio.run(lxc_monitor.load_existing_data(str(export_file))) == []

    def test_write_is_atomic(self, tmp_path):
        export_file = tmp_path / "metrics.json"
        asyncio.run(lxc_monitor.write_metrics_to_file(str(export_file), [{"a": 1}]))
        assert json.loads(export_file.read_text()) == [{"a": 1}]
        assert not (tmp_path / "metrics.json.tmp").exists()
