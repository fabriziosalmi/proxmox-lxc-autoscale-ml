"""Shared pytest fixtures.

The API modules are deployed flat into /usr/local/bin/lxc_autoscale_api and
import each other by bare module name, so that directory goes on sys.path.
"""
import os
import sys

import pytest

API_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "lxc_autoscale_ml",
    "api",
)
sys.path.insert(0, API_DIR)


TEST_CONFIG = {
    "lxc": {"node": "test-node", "default_storage": "local-lvm", "timeout_seconds": 5},
    "rate_limiting": {"enabled": True, "max_requests_per_minute": 3, "time_window_seconds": 60},
    "authentication": {"enabled": False},
    "logging": {"level": "INFO"},
    "error_handling": {"log_errors": False, "show_stack_traces": True},
}


@pytest.fixture
def app(monkeypatch):
    """A Flask app wired to the real routes, with Proxmox calls stubbed out."""
    import config as api_config

    monkeypatch.setattr(api_config, "load_config", lambda *a, **kw: dict(TEST_CONFIG))

    import lxc_autoscale_api

    lxc_autoscale_api.app.config.update(
        {k.upper(): v for k, v in TEST_CONFIG.items()},
        TESTING=True,
        LXC_NODE="test-node",
        TIMEOUT=5,
        RATE_LIMITING=TEST_CONFIG["rate_limiting"],
        AUTHENTICATION=TEST_CONFIG["authentication"],
        ERROR_HANDLING=TEST_CONFIG["error_handling"],
    )
    return lxc_autoscale_api.app


@pytest.fixture(autouse=True)
def reset_rate_limit():
    import rate_limiting

    rate_limiting.rate_limit_data.clear()
    yield
    rate_limiting.rate_limit_data.clear()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def pct(monkeypatch):
    """Capture every `pct`/`pvesh` invocation instead of running it.

    Returns the list of commands issued; the canned stdout can be overridden by
    assigning to ``pct.output``.
    """
    import lxc_management
    import resource_checking

    calls = []

    class Recorder(list):
        output = (
            "arch: amd64\n"
            "cores: 2\n"
            "memory: 2048\n"
            "rootfs: local-lvm:vm-104-disk-0,size=8G\n"
        )

    calls = Recorder()

    def fake_run_command(self, command):
        calls.append(command)
        return calls.output

    def fake_resource_run(command):
        calls.append(" ".join(command))
        return calls.output

    monkeypatch.setattr(lxc_management.LXCManager, "_run_command", fake_run_command)
    monkeypatch.setattr(resource_checking, "_run", fake_resource_run)
    return calls
