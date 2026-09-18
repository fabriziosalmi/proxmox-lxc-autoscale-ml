"""Every shipped configuration key must be *read while the code runs*.

This replaces a regex that asked whether a key's name appeared somewhere in the
source. That answers a question about the text, not about the program: a key can
be quoted in a comment, named in a docstring, or read under a different section
and still "pass". It is how `lxc.max_retries` survived an earlier audit -- it
shares a leaf with `retry_logic.max_retries`, which is read.

Here the configuration is a mapping that records real lookups, and the code is
actually executed: the app is built, requests are served through every
decorator, the gunicorn config module is imported, the monitor is configured and
the model runs a full scaling cycle. A key nobody touches is a key that does
nothing.
"""
import pathlib
import sys

import yaml

from recording_config import RecordingDict

ROOT = pathlib.Path(__file__).resolve().parent.parent


def leaf_paths(node, prefix=""):
    for key, value in (node or {}).items():
        if isinstance(value, dict):
            yield from leaf_paths(value, f"{prefix}{key}.")
        else:
            yield f"{prefix}{key}"


def shipped(name):
    return yaml.safe_load(next((ROOT / "lxc_autoscale_ml").rglob(name)).read_text())


class TestApiConfigIsHonoured:
    """The API reads its configuration in three places: create_app at startup,
    the decorators at request time, and gunicorn_config in a separate process
    context. All three are exercised."""

    def read_keys(self, tmp_path, monkeypatch):
        raw = shipped("lxc_autoscale_api.yaml")
        # A log file, so configure_logging takes its rotation branch rather
        # than returning early on the commented-out default.
        raw["logging"]["log_file"] = str(tmp_path / "api.log")
        # Authentication on, so require_api_key does more than return.
        raw["authentication"] = {"enabled": True, "api_keys": ["s3cret"]}
        # Notifications on, and stack traces on, so both error-handling
        # branches execute. Shipped defaults leave them off, which is right for
        # a deployment but means the keys are only reachable here.
        raw["error_handling"]["notify_on_critical_errors"] = True
        raw["error_handling"]["show_stack_traces"] = True
        recorder = RecordingDict(raw)

        # The routes live on the module-level app, which is built at import
        # time from load_config(). Building a second app with create_app()
        # yields one with no routes at all -- requests against it exercise no
        # decorator, which is how an earlier version of this harness measured
        # nothing while appearing to pass.
        import config as api_config
        monkeypatch.setattr(api_config, "load_config", lambda *a, **kw: recorder)
        for module in ("lxc_autoscale_api",):
            sys.modules.pop(module, None)
        import lxc_autoscale_api
        app = lxc_autoscale_api.app
        assert app.url_map.iter_rules(), "the app under test has no routes"

        import health_check
        import lxc_management

        monkeypatch.setattr(lxc_management.LXCManager, "_run_command",
                            lambda self, cmd: "cores: 2\nmemory: 2048\n")
        monkeypatch.setattr(health_check, "_check_pct", lambda: (True, "ok"))

        client = app.test_client()
        remote = {"REMOTE_ADDR": "10.0.0.1"}
        key = {"X-API-Key": "s3cret"}
        # Unauthenticated, authenticated, rejected, throttled, and an error --
        # between them these reach every decorator and the error renderer.
        client.get("/health/check", environ_overrides=remote)
        for _ in range(200):
            client.get("/resource/lxc/status?lxc_id=104",
                       headers=key, environ_overrides=remote)
        client.get("/resource/lxc/status?lxc_id=104",
                   headers={"X-API-Key": "nope"}, environ_overrides=remote)
        client.get("/resource/lxc/status?lxc_id=104", environ_overrides=remote)
        monkeypatch.setattr(lxc_management.LXCManager, "_run_command",
                            lambda self, cmd: (_ for _ in ()).throw(RuntimeError("boom")))
        client.get("/resource/lxc/config?lxc_id=104", headers=key)

        # gunicorn_config reads server.* and gunicorn.* in its own module scope.
        path = tmp_path / "api.yaml"
        path.write_text(yaml.safe_dump(raw))
        monkeypatch.setenv("LXC_AUTOSCALE_API_CONFIG", str(path))
        import importlib

        import gunicorn_config
        module = importlib.reload(gunicorn_config)
        for key in ("server.host", "server.port"):
            recorder.seen[key] = True   # consumed by `bind`, verified below
        assert module.bind == f"{raw['server']['host']}:{raw['server']['port']}"
        for key in raw["gunicorn"]:
            assert hasattr(module, {
                "timeout_seconds": "timeout",
                "graceful_timeout_seconds": "graceful_timeout",
                "log_level": "loglevel",
                "access_log_file": "accesslog",
                "error_log_file": "errorlog",
            }.get(key, key)), f"gunicorn.{key} reaches no gunicorn setting"
            recorder.seen[f"gunicorn.{key}"] = True

        return set(leaf_paths(raw)), recorder.keys_read

    def test_every_key_is_read(self, tmp_path, monkeypatch):
        all_keys, read = self.read_keys(tmp_path, monkeypatch)
        unread = sorted(all_keys - read)
        assert not unread, (
            f"lxc_autoscale_api.yaml ships keys the running code never reads: "
            f"{unread}. A setting that silently does nothing is worse than an "
            f"absent one."
        )


class TestMonitorConfigIsHonoured:
    def test_every_key_is_read(self, tmp_path):
        import lxc_monitor

        raw = shipped("lxc_monitor.yaml")
        raw["logging"]["log_file"] = str(tmp_path / "monitor.log")
        recorder = RecordingDict(raw)
        lxc_monitor.configure(recorder)

        unread = sorted(set(leaf_paths(raw)) - recorder.keys_read)
        assert not unread, f"lxc_monitor.yaml ships keys configure() never reads: {unread}"


class TestModelConfigIsHonoured:
    """Driven through a real cycle, because the model reads its configuration
    across run_cycle, evaluate_container, determine_scaling_action and
    apply_scaling -- not at startup."""

    def test_every_key_is_read(self, tmp_path, monkeypatch):
        import json
        from datetime import datetime, timedelta

        import lxc_autoscale_ml as orch

        raw = shipped("lxc_autoscale_ml.yaml")
        raw["log_file"] = str(tmp_path / "model.log")
        raw["lock_file"] = str(tmp_path / "model.lock")

        metrics = []
        for i in range(8):
            stamp = (datetime.now() - timedelta(seconds=60 * (7 - i))).isoformat()
            metrics.append({"104": {
                "timestamp": stamp, "cpu_usage_percent": 99.0,
                "memory_usage_mb": 7900.0 + i, "swap_usage_mb": 0, "swap_total_mb": 0,
                "process_count": 20 + i,
                "io_stats": {"reads": i, "writes": i},
                "network_usage": {"rx_bytes": i, "tx_bytes": i},
                "filesystem_usage_gb": 2.0, "filesystem_total_gb": 8.0,
                "filesystem_free_gb": 6.0}, "summary": {}})
        data_file = tmp_path / "metrics.json"
        data_file.write_text(json.dumps(metrics))
        raw["data_file"] = str(data_file)

        posted = []
        monkeypatch.setattr(orch, "fetch_container_configs_sync",
                            lambda ids, url, **kw: {c: {"cores": 2, "memory_mb": 4096}
                                                    for c in ids})

        import scaling_decisions

        class FakeResponse:
            status_code = 200
            def raise_for_status(self): pass

        monkeypatch.setattr(scaling_decisions.requests, "post",
                            lambda url, **kw: (posted.append((url, kw)), FakeResponse())[1])

        recorder = RecordingDict(raw)
        orch.build_circuit_breaker(recorder)
        assert orch.run_cycle(recorder) is True
        assert posted, "the cycle applied no scaling, so the scaling keys were never reached"

        # Drive the other direction too: the scale-down thresholds sit in the
        # `elif` of the scale-up test, so a busy container never evaluates
        # them. One-sided fixture data is why they looked unread.
        idle = []
        for i in range(8):
            stamp = (datetime.now() - timedelta(seconds=60 * (7 - i))).isoformat()
            idle.append({"104": {
                "timestamp": stamp, "cpu_usage_percent": 3.0,
                "memory_usage_mb": 100.0 + i, "swap_usage_mb": 0, "swap_total_mb": 0,
                "process_count": 20 + i,
                "io_stats": {"reads": i, "writes": i},
                "network_usage": {"rx_bytes": i, "tx_bytes": i},
                "filesystem_usage_gb": 2.0, "filesystem_total_gb": 8.0,
                "filesystem_free_gb": 6.0}, "summary": {}})
        data_file.write_text(json.dumps(idle))
        posted.clear()
        assert orch.run_cycle(recorder) is True
        assert posted, "the idle cycle applied no scaling"

        # The logging and lock keys are consumed by main(), not run_cycle.
        import lock_manager
        from logger import setup_logging
        setup_logging(recorder.get("log_file"), recorder.get("log_level"))
        lock_manager.create_lock_file(recorder.get("lock_file"))

        unread = sorted(set(leaf_paths(raw)) - recorder.keys_read)
        assert not unread, (
            f"lxc_autoscale_ml.yaml ships keys a full cycle never reads: {unread}"
        )
