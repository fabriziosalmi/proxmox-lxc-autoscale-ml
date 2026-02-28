from lxc_management import LXCManager
from utils import create_response, handle_error

def create_clone(lxc_id, new_lxc_id, new_lxc_name):
    try:
        lxc_manager = LXCManager()
        result = lxc_manager.clone(lxc_id, new_lxc_id, new_lxc_name)
        return create_response(data=result, message=f"Container {lxc_id} cloned as '{new_lxc_name}' with ID {new_lxc_id}")
    except Exception as e:
        return handle_error(e)

def delete_clone(lxc_id):
    try:
        lxc_manager = LXCManager()
        result = lxc_manager.delete_container(lxc_id)
        return create_response(data=result, message=f"Container {lxc_id} successfully deleted")
    except Exception as e:
        return handle_error(e)
