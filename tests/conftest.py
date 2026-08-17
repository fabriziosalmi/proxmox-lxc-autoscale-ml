"""Shared pytest fixtures.

The API modules are deployed flat into /usr/local/bin/lxc_autoscale_api and
import each other by bare module name, so that directory goes on sys.path.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_DIR = os.path.join(ROOT, "lxc_autoscale_ml", "api")
MODEL_DIR = os.path.join(ROOT, "lxc_autoscale_ml", "model")
MONITOR_DIR = os.path.join(ROOT, "lxc_autoscale_ml", "monitor")
for path in (API_DIR, MODEL_DIR, MONITOR_DIR):
    sys.path.insert(0, path)


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


DEFAULT_PCT_CONFIG = (
    "arch: amd64\n"
    "cores: 2\n"
    "memory: 2048\n"
    "rootfs: local-lvm:vm-104-disk-0,size=8G\n"
)

# Anything that only has meaning to a shell. `pct` is invoked without one, so a
# metacharacter reaching argv means a command was composed as a string
# somewhere -- the defect that left /clone/delete broken.
SHELL_METACHARACTERS = ("&&", "||", ";", "|", ">", "<", "$(", "`", "&")


class CommandRecorder(list):
    """Records `pct`/`pvesh` invocations as argument lists.

    Stubbing at this level is deliberate: the real defect in /clone/delete was
    a malformed argv that a stub returning a canned string would happily
    accept. Tests assert on the recorded argv, and `assert_no_shell_syntax`
    rejects any argument that only a shell could interpret.
    """

    responses = {}
    output = DEFAULT_PCT_CONFIG

    def record(self, argv):
        argv = [str(part) for part in argv]
        self.append(argv)
        for prefix, response in self.responses.items():
            if argv[:len(prefix)] == list(prefix):
                if isinstance(response, Exception):
                    raise response
                return response
        return self.output

    @property
    def commands(self):
        """The recorded invocations rendered as readable strings."""
        return [" ".join(argv) for argv in self]

    def assert_ran(self, *argv):
        expected = [str(part) for part in argv]
        assert expected in self, f"{expected} not in {self.commands}"

    def assert_no_shell_syntax(self):
        for argv in self:
            for argument in argv:
                for metacharacter in SHELL_METACHARACTERS:
                    assert metacharacter not in argument, (
                        f"argument {argument!r} in {' '.join(argv)!r} contains "
                        f"{metacharacter!r}: the command was composed as a "
                        f"string instead of an argument list"
                    )


@pytest.fixture
def pct(monkeypatch):
    """Capture every `pct`/`pvesh` invocation instead of running it."""
    import lxc_management
    import resource_checking

    calls = CommandRecorder()
    calls.responses = {}

    def fake_run_command(self, command):
        if isinstance(command, str):
            raise AssertionError(
                f"command was passed as a string, not an argument list: {command!r}"
            )
        return calls.record(command)

    monkeypatch.setattr(lxc_management.LXCManager, "_run_command", fake_run_command)
    monkeypatch.setattr(resource_checking, "_run", calls.record)
    return calls
