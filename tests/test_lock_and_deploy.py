"""Tests for the single-instance lock and the gunicorn configuration."""
import os

import pytest
import yaml

import lock_manager


@pytest.fixture
def lock_path(tmp_path):
    return str(tmp_path / "autoscale.lock")


class TestCreateLockFile:
    def test_writes_the_current_pid(self, lock_path):
        lock_manager.create_lock_file(lock_path)
        with open(lock_path) as f:
            assert f.read().strip() == str(os.getpid())

    def test_is_created_exclusively(self, lock_path, monkeypatch):
        """os.path.exists() followed by open() left a window where two
        instances starting together both proceeded to scale the same
        containers. The create must be atomic."""
        seen = {}
        real_open = os.open

        def recording_open(path, flags, *args):
            if path == lock_path:
                seen["flags"] = flags
            return real_open(path, flags, *args)

        monkeypatch.setattr(os, "open", recording_open)
        lock_manager.create_lock_file(lock_path)
        assert seen["flags"] & os.O_EXCL
        assert seen["flags"] & os.O_CREAT

    def test_a_live_lock_holder_stops_the_second_instance(self, lock_path):
        with open(lock_path, "w") as f:
            f.write(str(os.getpid()))  # this process is definitely alive
        with pytest.raises(SystemExit) as excinfo:
            lock_manager.create_lock_file(lock_path)
        assert excinfo.value.code == 1

    def test_a_stale_lock_is_reclaimed(self, lock_path, monkeypatch):
        with open(lock_path, "w") as f:
            f.write("999999")

        def not_running(pid, signal):
            raise ProcessLookupError

        monkeypatch.setattr(os, "kill", not_running)
        lock_manager.create_lock_file(lock_path)
        with open(lock_path) as f:
            assert f.read().strip() == str(os.getpid())

    def test_an_empty_lock_is_reclaimed(self, lock_path):
        open(lock_path, "w").close()
        lock_manager.create_lock_file(lock_path)
        with open(lock_path) as f:
            assert f.read().strip() == str(os.getpid())

    def test_a_garbage_lock_is_reclaimed(self, lock_path):
        with open(lock_path, "w") as f:
            f.write("not-a-pid")
        lock_manager.create_lock_file(lock_path)
        with open(lock_path) as f:
            assert f.read().strip() == str(os.getpid())

    def test_a_lock_owned_by_another_user_is_respected(self, lock_path, monkeypatch):
        """PermissionError means the process exists; treating it as stale would
        start a second instance alongside a running one."""
        with open(lock_path, "w") as f:
            f.write("1")

        def permission_denied(pid, signal):
            raise PermissionError

        monkeypatch.setattr(os, "kill", permission_denied)
        with pytest.raises(SystemExit):
            lock_manager.create_lock_file(lock_path)


class TestRemoveLockFile:
    def test_removes_an_existing_lock(self, lock_path):
        lock_manager.create_lock_file(lock_path)
        lock_manager.remove_lock_file(lock_path)
        assert not os.path.exists(lock_path)

    def test_absent_lock_is_not_an_error(self, lock_path):
        lock_manager.remove_lock_file(lock_path)  # must not raise


class TestGunicornConfig:
    """The systemd unit ran Flask's development server; the gunicorn section of
    the config file described a setup nothing read."""

    def _load(self, tmp_path, monkeypatch, config):
        path = tmp_path / "api.yaml"
        path.write_text(yaml.safe_dump(config))
        monkeypatch.setenv("LXC_AUTOSCALE_API_CONFIG", str(path))
        import importlib

        import gunicorn_config
        return importlib.reload(gunicorn_config)

    def test_binds_to_the_configured_address(self, tmp_path, monkeypatch):
        module = self._load(tmp_path, monkeypatch, {
            "server": {"host": "127.0.0.1", "port": 5050}})
        assert module.bind == "127.0.0.1:5050"
        assert module.wsgi_app == "lxc_autoscale_api:app"

    def test_reads_the_gunicorn_section(self, tmp_path, monkeypatch):
        module = self._load(tmp_path, monkeypatch, {"gunicorn": {
            "workers": 1, "threads": 4, "timeout_seconds": 90,
            "graceful_timeout_seconds": 15, "max_requests": 100,
        }})
        assert module.workers == 1
        assert module.threads == 4
        assert module.timeout == 90
        assert module.graceful_timeout == 15
        assert module.max_requests == 100

    def test_makes_the_api_directory_importable(self, tmp_path, monkeypatch):
        """The API modules import each other by bare name, so the service must
        not depend on the unit's WorkingDirectory being right."""
        import os

        module = self._load(tmp_path, monkeypatch, {})
        expected = os.path.dirname(os.path.abspath(module.__file__))
        assert module.chdir == expected
        assert module.pythonpath == expected
        assert os.path.exists(os.path.join(module.pythonpath, "lxc_autoscale_api.py"))

    def test_defaults_to_a_single_worker(self, tmp_path, monkeypatch):
        """Rate limiting and Prometheus counters live in process memory, so
        extra worker processes multiply the rate limit and split /metrics."""
        module = self._load(tmp_path, monkeypatch, {})
        assert module.workers == 1
        assert module.threads > 1

    def test_a_missing_config_file_still_yields_a_usable_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LXC_AUTOSCALE_API_CONFIG", str(tmp_path / "absent.yaml"))
        import importlib

        import gunicorn_config
        module = importlib.reload(gunicorn_config)
        assert module.bind == "0.0.0.0:5000"

    def test_multiple_workers_are_warned_about(self, tmp_path, monkeypatch):
        module = self._load(tmp_path, monkeypatch, {"gunicorn": {"workers": 4}})

        warnings = []

        class FakeServer:
            class log:
                @staticmethod
                def warning(message, *args):
                    warnings.append(message % args)

        module.on_starting(FakeServer())
        assert warnings and "per-process" in warnings[0]
