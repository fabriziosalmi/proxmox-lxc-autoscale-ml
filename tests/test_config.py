"""Tests for application configuration and logging setup."""
import logging
from logging.handlers import RotatingFileHandler

import pytest
import yaml

from config import DEFAULT_LOG_FORMAT, configure_logging, create_app, load_config


@pytest.fixture
def restore_root_logger():
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)


class TestLoadConfig:
    def test_reads_yaml(self, tmp_path):
        path = tmp_path / "api.yaml"
        path.write_text(yaml.safe_dump({"lxc": {"node": "pve"}}))
        assert load_config(str(path)) == {"lxc": {"node": "pve"}}


class TestCreateApp:
    def test_reads_every_section(self, restore_root_logger):
        app = create_app({
            "server": {"host": "127.0.0.1", "port": 5001},
            "lxc": {"node": "pve", "default_storage": "local-lvm", "timeout_seconds": 7},
            "rate_limiting": {"enabled": False},
            "authentication": {"enabled": True, "api_keys": ["k"]},
            "logging": {"level": "WARNING"},
            "error_handling": {"log_errors": True},
        })
        assert app.config["LXC_NODE"] == "pve"
        assert app.config["TIMEOUT"] == 7
        assert app.config["SERVER"] == {"host": "127.0.0.1", "port": 5001}
        assert app.config["AUTHENTICATION"]["enabled"] is True
        assert app.config["DEBUG"] is False

    def test_tolerates_a_minimal_config(self, restore_root_logger):
        """A config file missing optional sections must not crash startup."""
        app = create_app({})
        assert app.config["TIMEOUT"] == 30
        assert app.config["AUTHENTICATION"] == {"enabled": False}
        assert app.config["ERROR_HANDLING"] == {}
        assert app.config["SERVER"] == {}


class TestConfigureLogging:
    def test_defaults_to_stdout_only(self, restore_root_logger):
        configure_logging({})
        root = logging.getLogger()
        assert root.level == logging.INFO
        assert [type(h) for h in root.handlers] == [logging.StreamHandler]
        assert root.handlers[0].formatter._fmt == DEFAULT_LOG_FORMAT

    def test_honours_the_configured_level(self, restore_root_logger):
        configure_logging({"level": "debug"})
        assert logging.getLogger().level == logging.DEBUG

    def test_unknown_level_falls_back_to_info(self, restore_root_logger):
        configure_logging({"level": "chatty"})
        assert logging.getLogger().level == logging.INFO

    def test_adds_a_rotating_file_handler(self, tmp_path, restore_root_logger):
        log_file = tmp_path / "api.log"
        configure_logging({"log_file": str(log_file), "max_log_size_mb": 1, "backup_count": 2})
        handlers = logging.getLogger().handlers
        rotating = [h for h in handlers if isinstance(h, RotatingFileHandler)]
        assert len(rotating) == 1
        assert rotating[0].maxBytes == 1024 * 1024
        assert rotating[0].backupCount == 2

    def test_rotation_can_be_disabled(self, tmp_path, restore_root_logger):
        log_file = tmp_path / "api.log"
        configure_logging({"log_file": str(log_file), "rotate": False})
        handlers = logging.getLogger().handlers
        assert not any(isinstance(h, RotatingFileHandler) for h in handlers)
        assert any(isinstance(h, logging.FileHandler) for h in handlers)

    def test_repeated_calls_do_not_duplicate_handlers(self, restore_root_logger):
        configure_logging({})
        configure_logging({})
        assert len(logging.getLogger().handlers) == 1
