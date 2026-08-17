import logging
import re
import subprocess

from flask import current_app

DEFAULT_TIMEOUT_SECONDS = 30

# Multipliers for the size suffixes `pct config` reports on a rootfs entry.
_SIZE_SUFFIX_GB = {'K': 1 / (1024 * 1024), 'M': 1 / 1024, 'G': 1, 'T': 1024}


class LXCManager:
    """Thin wrapper around the `pct` command line.

    Every method builds an argument list and hands it straight to subprocess
    without a shell. Commands are never composed as a single string: doing so
    silently broke container deletion, because `shlex.split` turned
    "pct stop 105 && pct destroy 105" into one `pct` call with `&&` as a
    positional argument.
    """

    def __init__(self, node=None):
        self.node = node or current_app.config.get('LXC_NODE')
        self.timeout = current_app.config.get('TIMEOUT', DEFAULT_TIMEOUT_SECONDS)

    def _run_command(self, command):
        """
        Run a single command given as a list of arguments.

        Args:
            command: Argument list, e.g. ["pct", "stop", "104"]

        Returns:
            str: The command's stdout, stripped.

        Raises:
            RuntimeError: If the command fails, times out or is not installed.
        """
        if isinstance(command, str):
            raise TypeError(
                "commands must be passed as a list of arguments, not a string"
            )

        argv = [str(part) for part in command]
        printable = " ".join(argv)
        try:
            logging.info(f"Running command: {printable}")
            result = subprocess.run(  # noqa: S603 - fixed argv, no shell
                argv,
                capture_output=True,
                timeout=self.timeout,
                text=True,
            )
            result.check_returncode()
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logging.error(f"Command failed: {e.stderr}")
            raise RuntimeError(f"Command failed: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            logging.error(f"Command timed out: {printable}")
            raise RuntimeError(
                f"Command '{printable}' timed out after {self.timeout}s"
            ) from e
        except FileNotFoundError as e:
            logging.error(f"Command not found: {argv[0]}")
            raise RuntimeError(
                f"'{argv[0]}' not found. Is this running on a Proxmox host?"
            ) from e

    # --- Lifecycle -----------------------------------------------------------

    def start_container(self, lxc_id):
        return self._run_command(["pct", "start", lxc_id])

    def stop_container(self, lxc_id):
        return self._run_command(["pct", "stop", lxc_id])

    def destroy_container(self, lxc_id):
        return self._run_command(["pct", "destroy", lxc_id])

    def delete_container(self, lxc_id):
        """Stop the container, then destroy it.

        Two separate commands: `pct` cannot do both at once, and joining them
        with `&&` does not work without a shell.
        """
        stop_output = self.stop_container(lxc_id)
        destroy_output = self.destroy_container(lxc_id)
        return "\n".join(part for part in (stop_output, destroy_output) if part)

    # --- Resources -----------------------------------------------------------

    def scale_cpu(self, lxc_id, cores):
        return self._run_command(["pct", "set", lxc_id, "-cores", cores])

    def scale_ram(self, lxc_id, memory):
        return self._run_command(["pct", "set", lxc_id, "-memory", memory])

    def get_config(self, lxc_id):
        """Return `pct config` output as a dict of key -> value."""
        output = self._run_command(["pct", "config", lxc_id])
        config = {}
        for line in output.splitlines():
            key, separator, value = line.partition(":")
            if separator:
                config[key.strip()] = value.strip()
        return config

    def get_current_disk_size(self, lxc_id):
        """
        Return the size of the root filesystem in GB.

        The rootfs entry looks like `local-lvm:vm-104-disk-0,size=8G,acl=1`.
        The options after the volume are order-independent, so the size is
        looked up by name rather than by position, and every suffix pct can
        emit is handled.
        """
        rootfs = self.get_config(lxc_id).get("rootfs")
        if not rootfs:
            raise RuntimeError(
                f"Container {lxc_id} has no rootfs entry in its configuration"
            )

        for option in rootfs.split(","):
            key, separator, value = option.partition("=")
            if separator and key.strip() == "size":
                match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMGT])?", value.strip(), re.IGNORECASE)
                if not match:
                    raise RuntimeError(
                        f"Unrecognised rootfs size '{value}' for container {lxc_id}"
                    )
                amount = float(match.group(1))
                suffix = (match.group(2) or "G").upper()
                return int(amount * _SIZE_SUFFIX_GB[suffix])

        raise RuntimeError(
            f"Failed to retrieve the current disk size of container {lxc_id}"
        )

    def get_current_resources(self, lxc_id):
        """Return (cores, memory_mb) for a container.

        Either may be None. `cores` in particular is OPTIONAL in Proxmox --
        `pct create` without `--cores` leaves it unset, meaning "all host
        cores" -- and treating its absence as an error made
        /resource/lxc/config return 500 for such a container forever, which in
        turn drove the scaling loop down its guess-the-allocation path.
        A missing value is a fact about the container, not a failure.
        """
        config = self.get_config(lxc_id)

        def optional_int(key):
            raw = config.get(key)
            if raw is None:
                return None
            try:
                return int(raw)
            except ValueError:
                logging.warning(
                    f"Container {lxc_id} reports a non-numeric {key}: {raw!r}")
                return None

        return optional_int("cores"), optional_int("memory")

    def resize_storage(self, lxc_id, disk_size):
        """Grow the root filesystem by `disk_size` GB."""
        new_size = self.get_current_disk_size(lxc_id) + int(disk_size)
        return self._run_command(["pct", "resize", lxc_id, "rootfs", f"{new_size}G"])

    # --- Snapshots -----------------------------------------------------------

    def create_snapshot(self, lxc_id, snapshot_name):
        return self._run_command(["pct", "snapshot", lxc_id, snapshot_name])

    def delete_snapshot(self, lxc_id, snapshot_name):
        return self._run_command(["pct", "delsnapshot", lxc_id, snapshot_name])

    def list_snapshots(self, lxc_id):
        return self._run_command(["pct", "listsnapshot", lxc_id])

    def rollback_snapshot(self, lxc_id, snapshot_name):
        return self._run_command(["pct", "rollback", lxc_id, snapshot_name])

    # --- Cloning -------------------------------------------------------------

    def clone_container(self, lxc_id, new_lxc_id, new_lxc_name, snapshot_name):
        """Clone from an existing snapshot."""
        return self._run_command([
            "pct", "clone", lxc_id, new_lxc_id,
            "--hostname", new_lxc_name,
            "--snapname", snapshot_name,
        ])

    def clone(self, lxc_id, new_lxc_id, new_lxc_name):
        """Full clone of a container, without going through a snapshot."""
        return self._run_command([
            "pct", "clone", lxc_id, new_lxc_id,
            "--hostname", new_lxc_name,
            "--full",
        ])
