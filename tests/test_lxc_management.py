"""Tests for the pct command wrapper.

These assert on the argument list actually handed to subprocess. Testing only
the HTTP status code is what let a malformed `pct stop 105 && pct destroy 105`
survive: the route answered 200 while the command could never run.
"""
import subprocess

import pytest

from lxc_management import LXCManager


@pytest.fixture
def manager(app):
    with app.app_context():
        yield LXCManager()


class TestRunCommand:
    def test_rejects_a_string_command(self, manager):
        """Guards the class of bug that broke container deletion."""
        with pytest.raises(TypeError, match="list of arguments"):
            manager._run_command("pct stop 104 && pct destroy 104")

    def test_arguments_are_stringified(self, manager, monkeypatch):
        seen = {}

        def fake_run(argv, **kwargs):
            seen["argv"] = argv
            seen["kwargs"] = kwargs
            return subprocess.CompletedProcess(argv, 0, stdout="done\n", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert manager._run_command(["pct", "set", 104, "-cores", 4]) == "done"
        assert seen["argv"] == ["pct", "set", "104", "-cores", "4"]
        assert seen["kwargs"]["timeout"] == 5
        # No shell, ever.
        assert seen["kwargs"].get("shell") in (None, False)

    def test_non_zero_exit_raises(self, manager, monkeypatch):
        def fake_run(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 2, stdout="", stderr="no such container")

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(RuntimeError, match="no such container"):
            manager._run_command(["pct", "status", 999])

    def test_timeout_raises_with_context(self, manager, monkeypatch):
        def fake_run(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 5)

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(RuntimeError, match="timed out after 5s"):
            manager._run_command(["pct", "status", 104])

    def test_missing_binary_raises_a_clear_error(self, manager, monkeypatch):
        def fake_run(argv, **kwargs):
            raise FileNotFoundError(2, "No such file or directory", "pct")

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(RuntimeError, match="Proxmox host"):
            manager._run_command(["pct", "status", 104])


class TestDeleteContainer:
    def test_issues_two_separate_commands(self, manager, pct):
        """Regression: this used to be one `pct stop X && pct destroy X` string."""
        manager.delete_container(105)
        assert pct == [["pct", "stop", "105"], ["pct", "destroy", "105"]]
        pct.assert_no_shell_syntax()

    def test_does_not_destroy_when_stopping_fails(self, manager, pct):
        pct.responses = {("pct", "stop"): RuntimeError("container is locked")}
        with pytest.raises(RuntimeError, match="locked"):
            manager.delete_container(105)
        assert ["pct", "destroy", "105"] not in pct


class TestGetConfig:
    def test_parses_key_value_pairs(self, manager, pct):
        assert manager.get_config(104)["cores"] == "2"
        pct.assert_ran("pct", "config", 104)

    def test_get_current_resources(self, manager, pct):
        assert manager.get_current_resources(104) == (2, 2048)

    def test_absent_fields_are_reported_as_unknown_not_as_an_error(self, manager, pct):
        """See TestOptionalConfigFields: `cores` is optional in Proxmox, so its
        absence is a fact about the container rather than a failure."""
        pct.output = "arch: amd64\n"
        assert manager.get_current_resources(104) == (None, None)


class TestDiskSize:
    @pytest.mark.parametrize(
        "rootfs,expected",
        [
            ("local-lvm:vm-104-disk-0,size=8G", 8),
            # Options are order-independent; the old code took the second field.
            ("local-lvm:vm-104-disk-0,acl=1,size=16G", 16),
            ("local-lvm:vm-104-disk-0,size=8G,acl=1,mountoptions=noatime", 8),
            ("local:104/vm-104-disk-0.raw,size=2T", 2048),
            ("local-lvm:vm-104-disk-0,size=512M", 0),
            ("local-lvm:vm-104-disk-0,size=2048M", 2),
        ],
    )
    def test_parses_size_regardless_of_position_or_unit(self, manager, pct, rootfs, expected):
        pct.output = f"cores: 2\nmemory: 2048\nrootfs: {rootfs}\n"
        assert manager.get_current_disk_size(104) == expected

    def test_missing_rootfs_raises(self, manager, pct):
        pct.output = "cores: 2\nmemory: 2048\n"
        with pytest.raises(RuntimeError, match="no rootfs entry"):
            manager.get_current_disk_size(104)

    def test_missing_size_option_raises(self, manager, pct):
        pct.output = "rootfs: local-lvm:vm-104-disk-0,acl=1\n"
        with pytest.raises(RuntimeError, match="current disk size"):
            manager.get_current_disk_size(104)

    def test_resize_grows_by_a_relative_amount(self, manager, pct):
        """`pct resize` takes `+NG`. The read-modify-write this replaces raced
        with any concurrent resize and silently lost up to 1 GiB, because the
        current size was floored to whole GB."""
        manager.resize_storage(104, 4)
        pct.assert_ran("pct", "resize", 104, "rootfs", "+4G")
        # No read of the current size at all.
        assert not any(argv[:2] == ["pct", "config"] for argv in pct)

    def test_a_fractional_current_size_is_not_lost(self, manager, pct):
        """8.5G + 2G used to become 10G while reporting success."""
        pct.output = "rootfs: local-lvm:vm-104-disk-0,size=8.5G\n"
        manager.resize_storage(104, 2)
        pct.assert_ran("pct", "resize", 104, "rootfs", "+2G")


class TestCommandShapes:
    """Every command must be a well-formed argv, on every code path."""

    def test_all_commands_are_shell_free(self, manager, pct):
        manager.start_container(104)
        manager.stop_container(104)
        manager.destroy_container(104)
        manager.scale_cpu(104, 4)
        manager.scale_ram(104, 2048)
        manager.create_snapshot(104, "snap-1")
        manager.delete_snapshot(104, "snap-1")
        manager.list_snapshots(104)
        manager.rollback_snapshot(104, "snap-1")
        manager.clone_container(104, 105, "web-1", "snap-1")
        manager.clone(104, 106, "web-2")
        manager.resize_storage(104, 1)
        pct.assert_no_shell_syntax()
        assert all(argv[0] == "pct" for argv in pct)

    def test_clone_variants_use_the_right_flags(self, manager, pct):
        manager.clone_container(104, 105, "web-1", "snap-1")
        pct.assert_ran(
            "pct", "clone", 104, 105, "--hostname", "web-1", "--snapname", "snap-1"
        )
        manager.clone(104, 106, "web-2")
        pct.assert_ran("pct", "clone", 104, 106, "--hostname", "web-2", "--full")


class TestOptionalConfigFields:
    """`cores` is optional in Proxmox: `pct create` without `--cores` leaves it
    unset, meaning "all host cores". Treating that as an error made
    /resource/lxc/config return 500 for such a container permanently."""

    def test_missing_cores_is_reported_as_unknown(self, manager, pct):
        pct.output = "arch: amd64\nmemory: 2048\nrootfs: local-lvm:vm-104-disk-0,size=8G\n"
        assert manager.get_current_resources(104) == (None, 2048)

    def test_missing_memory_is_reported_as_unknown(self, manager, pct):
        pct.output = "arch: amd64\ncores: 2\n"
        assert manager.get_current_resources(104) == (2, None)

    def test_non_numeric_values_are_reported_as_unknown(self, manager, pct):
        pct.output = "cores: many\nmemory: 2048\n"
        assert manager.get_current_resources(104) == (None, 2048)

    def test_both_present_is_unchanged(self, manager, pct):
        assert manager.get_current_resources(104) == (2, 2048)
