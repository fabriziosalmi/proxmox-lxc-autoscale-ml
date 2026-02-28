from lxc_management import LXCManager
from utils import create_response, handle_error

def create_snapshot(lxc_id, snapshot_name):
    try:
        lxc_manager = LXCManager()
        result = lxc_manager.create_snapshot(lxc_id, snapshot_name)
        return create_response(data=result, message=f"Snapshot '{snapshot_name}' created for container {lxc_id}")
    except Exception as e:
        return handle_error(e)

def list_snapshots(lxc_id):
    try:
        lxc_manager = LXCManager()
        result = lxc_manager.list_snapshots(lxc_id)
        return create_response(data=result, message=f"Snapshots listed for container {lxc_id}")
    except Exception as e:
        return handle_error(e)

def rollback_snapshot(lxc_id, snapshot_name):
    try:
        lxc_manager = LXCManager()
        result = lxc_manager.rollback_snapshot(lxc_id, snapshot_name)
        return create_response(data=result, message=f"Container {lxc_id} rolled back to snapshot '{snapshot_name}'")
    except Exception as e:
        return handle_error(e)
