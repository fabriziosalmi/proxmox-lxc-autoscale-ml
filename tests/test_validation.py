"""Unit tests for the input validators."""
import pytest

from validation import (
    ValidationError,
    validate_cores,
    validate_disk_size,
    validate_hostname,
    validate_lxc_id,
    validate_memory,
    validate_node_name,
    validate_snapshot_name,
    validate_vm_id,
)


class TestLxcId:
    @pytest.mark.parametrize("value,expected", [(100, 100), ("104", 104), (999999, 999999)])
    def test_accepts_valid_ids(self, value, expected):
        assert validate_lxc_id(value) == expected

    @pytest.mark.parametrize("value", [99, 1000000, "abc", None, "", 1.5e400])
    def test_rejects_invalid_ids(self, value):
        with pytest.raises(ValidationError):
            validate_lxc_id(value)

    def test_legacy_alias_points_at_the_same_validator(self):
        assert validate_vm_id is validate_lxc_id


class TestNumericValidators:
    @pytest.mark.parametrize(
        "validator,valid,invalid",
        [
            (validate_cores, [1, "4", 128], [0, 129, "x"]),
            (validate_memory, [64, "2048", 1048576], [63, 1048577, "x"]),
            (validate_disk_size, [1, "10", 10240], [0, 10241, "x"]),
        ],
    )
    def test_bounds(self, validator, valid, invalid):
        for value in valid:
            assert validator(value) == int(value)
        for value in invalid:
            with pytest.raises(ValidationError):
                validator(value)


class TestSnapshotName:
    @pytest.mark.parametrize("name", ["backup", "backup-1", "backup_1", "a" * 40])
    def test_accepts_safe_names(self, name):
        assert validate_snapshot_name(name) == name

    @pytest.mark.parametrize(
        "name", ["", None, "a" * 41, "back up", "rm -rf /", "a;b", "../etc/passwd", "a$b"]
    )
    def test_rejects_unsafe_names(self, name):
        with pytest.raises(ValidationError):
            validate_snapshot_name(name)


class TestHostname:
    def test_underscores_are_normalised(self):
        assert validate_hostname("cloned_container") == "cloned-container"

    @pytest.mark.parametrize("name", ["web1", "web-1", "A-B"])
    def test_accepts_rfc1123_names(self, name):
        assert validate_hostname(name) == name

    @pytest.mark.parametrize("name", ["", None, "-web", "web-", "a" * 64, "we b", "a;b"])
    def test_rejects_invalid_names(self, name):
        with pytest.raises(ValidationError):
            validate_hostname(name)


class TestNodeName:
    @pytest.mark.parametrize("name", ["pve", "proxmox4", "node-1", "node.example.com"])
    def test_accepts_valid_names(self, name):
        assert validate_node_name(name) == name

    @pytest.mark.parametrize("name", ["", None, "-node", "node/../etc", "no spaces", "a;b"])
    def test_rejects_invalid_names(self, name):
        with pytest.raises(ValidationError):
            validate_node_name(name)
