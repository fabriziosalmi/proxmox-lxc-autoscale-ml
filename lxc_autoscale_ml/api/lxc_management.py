import subprocess
import shlex
from flask import current_app
import logging

class LXCManager:
    def __init__(self, node=None):
        self.node = node or current_app.config['LXC_NODE']
        self.timeout = current_app.config['TIMEOUT']

    def _run_command(self, command):
        try:
            logging.info(f"Running command: {command}")
            result = subprocess.run(
                shlex.split(command),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
                universal_newlines=True
            )
            result.check_returncode()
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logging.error(f"Command failed: {e.stderr}")
            raise Exception(f"Command failed: {e.stderr}")
        except subprocess.TimeoutExpired:
            logging.error("Command timed out")
            raise Exception("Command timed out")


    def stop_container(self, lxc_id):
        command = f"pct stop {lxc_id}"
        return self._run_command(command)

    def destroy_container(self, lxc_id):
        command = f"pct destroy {lxc_id}"
        return self._run_command(command)

    def create_temporary_snapshot(self, lxc_id):
        snapshot_name = f"migrate-snapshot-{lxc_id}"
        command = f"pct snapshot {lxc_id} {snapshot_name}"
        self._run_command(command)
        return snapshot_name

    def delete_snapshot(self, lxc_id, snapshot_name):
        command = f"pct delsnapshot {lxc_id} {snapshot_name}"
        self._run_command(command)

    def migrate_container(self, lxc_id, target_node):
        # Check for non-migratable snapshots or create a new one for migration
        snapshot_name = self.create_temporary_snapshot(lxc_id)
        
        try:
            command = f"pct migrate {lxc_id} {target_node}"
            self._run_command(command)
        finally:
            # Clean up the temporary snapshot after migration
            self.delete_snapshot(lxc_id, snapshot_name)

    def scale_cpu(self, lxc_id, cores):
        command = f"pct set {lxc_id} -cores {cores}"
        return self._run_command(command)

    def scale_ram(self, lxc_id, memory):
        command = f"pct set {lxc_id} -memory {memory}"
        return self._run_command(command)

    def get_current_disk_size(self, lxc_id):
        # Retrieve the current size of the root filesystem in GB
        command = f"pct config {lxc_id}"
        output = self._run_command(command)
        for line in output.splitlines():
            if line.startswith("rootfs:"):
                current_size = line.split(",")[1].replace("size=", "").replace("G", "").strip()
                return int(current_size)
        raise Exception("Failed to retrieve current disk size")
    
    def get_current_resources(self, lxc_id):
        """Retrieve current CPU cores and memory (MB) for a container"""
        command = f"pct config {lxc_id}"
        output = self._run_command(command)
        cores = None
        memory = None
        for line in output.splitlines():
            if line.startswith("cores:"):
                cores = int(line.split(":")[1].strip())
            elif line.startswith("memory:"):
                memory = int(line.split(":")[1].strip())
        if cores is None or memory is None:
            raise Exception(f"Failed to retrieve current resources for container {lxc_id}")
        return cores, memory

    def resize_storage(self, lxc_id, disk_size):
        current_size = self.get_current_disk_size(lxc_id)
        new_size = current_size + disk_size
        command = f"pct resize {lxc_id} rootfs {new_size}G"
        return self._run_command(command)

    def create_snapshot(self, lxc_id, snapshot_name):
        command = f"pct snapshot {lxc_id} {snapshot_name}"
        return self._run_command(command)

    def clone_container(self, lxc_id, new_lxc_id, new_lxc_name, snapshot_name):
        command = f"pct clone {lxc_id} {new_lxc_id} --hostname {new_lxc_name} --snapname {snapshot_name}"
        return self._run_command(command)

    def start_container(self, lxc_id):
        command = f"pct start {lxc_id}"
        return self._run_command(command)

    def list_snapshots(self, lxc_id):
        command = f"pct listsnapshot {lxc_id}"
        return self._run_command(command)

    def rollback_snapshot(self, lxc_id, snapshot_name):
        command = f"pct rollback {lxc_id} {snapshot_name}"
        return self._run_command(command)

    def clone(self, lxc_id, new_lxc_id, new_lxc_name):
        command = f"pct clone {lxc_id} {new_lxc_id} --hostname {new_lxc_name} --full"
        return self._run_command(command)

    def delete_container(self, lxc_id):
        command = f"pct stop {lxc_id} && pct destroy {lxc_id}"
        return self._run_command(command)

    def migrate(self, lxc_id, target_node):
        command = f"pct migrate {lxc_id} {target_node}"
        return self._run_command(command)
