import logging
import time

from flask import jsonify, request

from config import create_app
from scaling import scale_cpu, scale_ram, resize_storage
from snapshot_management import create_snapshot, list_snapshots, rollback_snapshot
from cloning_management import delete_clone
from resource_checking import check_lxc_status, check_node_status, check_cluster_status
from health_check import health_check
from rate_limiting import rate_limit
from lxc_management import LXCManager
from utils import create_response, handle_error
from validation import (
    validate_request,
    validate_lxc_id,
    validate_cores,
    validate_memory,
    validate_disk_size,
    validate_snapshot_name,
    validate_hostname,
    validate_node_name,
)
from authentication import require_api_key
from metrics import (
    metrics_endpoint,
    record_api_request,
    record_scaling_action,
    update_container_resources,
)

# Logging is configured from the `logging` section of the config file by
# create_app(), so there is no basicConfig call here.
app = create_app()

# Endpoints are documented under both the accurate "lxc" spelling and the
# historical "vm" one. The latter is deprecated but kept so that existing
# deployments and scripts keep working.
ENDPOINTS = [
    ("/scale/cores", "POST", "Set the exact number of CPU cores for an LXC container.",
     """curl -X POST http://proxmox:5000/scale/cores -H "Content-Type: application/json" -d '{"lxc_id": 104, "cores": 4}'"""),
    ("/scale/ram", "POST", "Set the exact amount of RAM for an LXC container.",
     """curl -X POST http://proxmox:5000/scale/ram -H "Content-Type: application/json" -d '{"lxc_id": 104, "memory": 4096}'"""),
    ("/scale/storage/increase", "POST", "Increase the storage size of an LXC container's root filesystem.",
     """curl -X POST http://proxmox:5000/scale/storage/increase -H "Content-Type: application/json" -d '{"lxc_id": 104, "disk_size": 2}'"""),
    ("/snapshot/create", "POST", "Create a snapshot for an LXC container.",
     """curl -X POST http://proxmox:5000/snapshot/create -H "Content-Type: application/json" -d '{"lxc_id": 104, "snapshot_name": "my_snapshot"}'"""),
    ("/snapshot/list", "GET", "List all snapshots for an LXC container.",
     """curl -X GET "http://proxmox:5000/snapshot/list?lxc_id=104" """),
    ("/snapshot/rollback", "POST", "Rollback to a specific snapshot.",
     """curl -X POST http://proxmox:5000/snapshot/rollback -H "Content-Type: application/json" -d '{"lxc_id": 104, "snapshot_name": "my_snapshot"}'"""),
    ("/clone/create", "POST", "Clone an LXC container.",
     """curl -X POST http://proxmox:5000/clone/create -H "Content-Type: application/json" -d '{"lxc_id": 104, "new_lxc_id": 105, "new_lxc_name": "cloned-container"}'"""),
    ("/clone/delete", "DELETE", "Delete a cloned LXC container.",
     """curl -X DELETE http://proxmox:5000/clone/delete -H "Content-Type: application/json" -d '{"lxc_id": 105}'"""),
    ("/resource/lxc/status", "GET", "Check the run state of an LXC container (alias: /resource/vm/status).",
     """curl -X GET "http://proxmox:5000/resource/lxc/status?lxc_id=104" """),
    ("/resource/lxc/config", "GET", "Get the CPU and RAM allocation of an LXC container (alias: /resource/vm/config).",
     """curl -X GET "http://proxmox:5000/resource/lxc/config?lxc_id=104" """),
    ("/resource/node/status", "GET", "Check the resource usage of a specific node.",
     """curl -X GET "http://proxmox:5000/resource/node/status?node_name=proxmox4" """),
    ("/resource/cluster/status", "GET", "Check the status of the Proxmox cluster.",
     """curl -X GET http://proxmox:5000/resource/cluster/status"""),
    ("/health/check", "GET", "Perform a health check on the API server.",
     """curl -X GET http://proxmox:5000/health/check"""),
    ("/metrics", "GET", "Prometheus metrics exposition endpoint.",
     """curl -X GET http://proxmox:5000/metrics"""),
    ("/routes", "GET", "List all available routes.",
     """curl -X GET http://proxmox:5000/routes"""),
]


def _failure_reason(response):
    """A coarse, bounded label for a failed scaling action.

    Every failure used to be recorded as reason="unknown", so the failure
    counter carried no diagnostic value at all. Derived from the status code
    rather than the message, to keep the label set finite.
    """
    status = response[1]
    if status < 400:
        return None
    return {400: "invalid_request", 401: "unauthenticated", 403: "forbidden",
            404: "not_found", 429: "rate_limited"}.get(status, "command_failed")


KNOWN_METHODS = frozenset({'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'})


def _escape(text):
    """Minimal HTML escaping for the self-documenting home page."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


@app.route('/', methods=['GET'])
def home():
    """Self-documenting index page. Intentionally free of external assets so the
    API server never reaches out to a CDN."""
    rows = "\n".join(
        "<tr><td><code>{}</code></td><td>{}</td><td>{}</td><td><code>{}</code></td></tr>".format(
            _escape(path), _escape(method), _escape(description), _escape(example.strip())
        )
        for path, method, description, example in ENDPOINTS
    )

    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>AutoScaleAPI Documentation</title>
    <style>
        body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
               margin: 0 auto; max-width: 1100px; padding: 2rem 1rem; line-height: 1.5; }}
        h1 {{ margin-bottom: 0.25rem; }}
        p.lead {{ color: #555; margin-top: 0; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 1.5rem; }}
        th, td {{ border: 1px solid #ddd; padding: 0.5rem 0.6rem; text-align: left;
                  vertical-align: top; font-size: 0.9rem; }}
        th {{ background: #222; color: #fff; }}
        tr:nth-child(even) {{ background: #fafafa; }}
        code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; word-break: break-all; }}
    </style>
</head>
<body>
    <h1>AutoScaleAPI</h1>
    <p class="lead">Available API routes with descriptions and example usage.
    Container IDs may be passed as <code>lxc_id</code> (preferred) or <code>vm_id</code> (deprecated).</p>
    <table>
        <thead><tr><th>Endpoint</th><th>Method</th><th>Description</th><th>Example</th></tr></thead>
        <tbody>
{rows}
        </tbody>
    </table>
</body>
</html>
""".format(rows=rows)


# --- Scaling -----------------------------------------------------------------

@app.route('/scale/cores', methods=['POST'])
@rate_limit
@require_api_key
@validate_request({'vm_id': validate_lxc_id, 'cores': validate_cores})
def set_cores():
    data = request.validated_data
    lxc_id = data['vm_id']
    cores = data['cores']
    logging.info(f"Setting {cores} cores for container {lxc_id}")
    response = scale_cpu(lxc_id, cores)
    record_scaling_action(lxc_id, 'cpu', 'set', success=response[1] < 400,
                          failure_reason=_failure_reason(response))
    return response


@app.route('/scale/ram', methods=['POST'])
@rate_limit
@require_api_key
@validate_request({'vm_id': validate_lxc_id, 'memory': validate_memory})
def set_ram():
    data = request.validated_data
    lxc_id = data['vm_id']
    memory = data['memory']
    logging.info(f"Setting {memory} MB RAM for container {lxc_id}")
    response = scale_ram(lxc_id, memory)
    record_scaling_action(lxc_id, 'ram', 'set', success=response[1] < 400,
                          failure_reason=_failure_reason(response))
    return response


@app.route('/scale/storage/increase', methods=['POST'])
@rate_limit
@require_api_key
@validate_request({'vm_id': validate_lxc_id, 'disk_size': validate_disk_size})
def increase_storage():
    data = request.validated_data
    lxc_id = data['vm_id']
    disk_size = data['disk_size']
    logging.info(f"Increasing storage by {disk_size} GB for container {lxc_id}")
    response = resize_storage(lxc_id, disk_size)
    record_scaling_action(lxc_id, 'storage', 'increase', success=response[1] < 400,
                          failure_reason=_failure_reason(response))
    return response


# --- Snapshots ---------------------------------------------------------------

@app.route('/snapshot/create', methods=['POST'])
@rate_limit
@require_api_key
@validate_request({'vm_id': validate_lxc_id, 'snapshot_name': validate_snapshot_name})
def create_snapshot_route():
    data = request.validated_data
    lxc_id = data['vm_id']
    snapshot_name = data['snapshot_name']
    logging.info(f"Creating snapshot '{snapshot_name}' for container {lxc_id}")
    return create_snapshot(lxc_id, snapshot_name)


@app.route('/snapshot/list', methods=['GET'])
@rate_limit
@require_api_key
@validate_request({'vm_id': validate_lxc_id})
def list_snapshots_route():
    lxc_id = request.validated_data['vm_id']
    logging.info(f"Listing snapshots for container {lxc_id}")
    return list_snapshots(lxc_id)


@app.route('/snapshot/rollback', methods=['POST'])
@rate_limit
@require_api_key
@validate_request({'vm_id': validate_lxc_id, 'snapshot_name': validate_snapshot_name})
def rollback_snapshot_route():
    data = request.validated_data
    lxc_id = data['vm_id']
    snapshot_name = data['snapshot_name']
    logging.info(f"Rolling container {lxc_id} back to snapshot '{snapshot_name}'")
    return rollback_snapshot(lxc_id, snapshot_name)


# --- Cloning -----------------------------------------------------------------

@app.route('/clone/create', methods=['POST'])
@rate_limit
@require_api_key
@validate_request({
    'vm_id': validate_lxc_id,
    'new_vm_id': validate_lxc_id,
    'new_vm_name': validate_hostname,
})
def create_clone_route():
    data = request.validated_data
    lxc_id = data['vm_id']
    new_lxc_id = data['new_vm_id']
    new_lxc_name = data['new_vm_name']
    snapshot_name = f"snapshot-{new_lxc_id}"

    try:
        lxc_manager = LXCManager()

        logging.info(f"Creating snapshot '{snapshot_name}' of container {lxc_id}")
        lxc_manager.create_snapshot(lxc_id, snapshot_name)

        cleanup_error = None
        try:
            logging.info(f"Cloning container {lxc_id} to {new_lxc_id} ('{new_lxc_name}')")
            lxc_manager.clone_container(lxc_id, new_lxc_id, new_lxc_name, snapshot_name)

            logging.info(f"Starting clone {new_lxc_id}")
            lxc_manager.start_container(new_lxc_id)
        finally:
            # Always drop the temporary snapshot, even when cloning failed. A
            # failure here is logged rather than raised, so it cannot mask the
            # error that actually broke the clone.
            logging.info(f"Deleting snapshot '{snapshot_name}' of container {lxc_id}")
            try:
                lxc_manager.delete_snapshot(lxc_id, snapshot_name)
            except Exception as e:  # noqa: BLE001 - reported, never swallowed silently
                cleanup_error = e
                logging.error(
                    f"Failed to delete temporary snapshot '{snapshot_name}' of "
                    f"container {lxc_id}: {e}"
                )

        if cleanup_error is not None:
            return create_response(
                data=f"Container {new_lxc_id} cloned from {lxc_id} and started successfully, "
                     f"but the temporary snapshot {snapshot_name} could not be removed.",
                message=f"Clone succeeded; snapshot cleanup failed: {cleanup_error}",
                status_code=200
            )

        return create_response(
            data=f"Container {new_lxc_id} cloned from {lxc_id} and started successfully. Snapshot {snapshot_name} removed.",
            message="Clone operation completed successfully.",
            status_code=200
        )
    except Exception as e:
        return handle_error(e)


@app.route('/clone/delete', methods=['DELETE'])
@rate_limit
@require_api_key
@validate_request({'vm_id': validate_lxc_id})
def delete_clone_route():
    lxc_id = request.validated_data['vm_id']
    logging.info(f"Stopping and destroying container {lxc_id}")
    return delete_clone(lxc_id)


# --- Resource inspection -----------------------------------------------------

@app.route('/resource/lxc/status', methods=['GET'])
@app.route('/resource/vm/status', methods=['GET'])  # deprecated alias
@rate_limit
@require_api_key
@validate_request({'vm_id': validate_lxc_id})
def check_lxc_status_route():
    lxc_id = request.validated_data['vm_id']
    logging.info(f"Checking status for container {lxc_id}")
    return check_lxc_status(lxc_id)


@app.route('/resource/lxc/config', methods=['GET'])
@app.route('/resource/vm/config', methods=['GET'])  # deprecated alias
@rate_limit
@require_api_key
@validate_request({'vm_id': validate_lxc_id})
def get_lxc_config_route():
    """Get current CPU cores and RAM configuration for a container."""
    lxc_id = request.validated_data['vm_id']
    logging.info(f"Getting configuration for container {lxc_id}")
    try:
        lxc_manager = LXCManager()
        cores, memory = lxc_manager.get_current_resources(lxc_id)
        # The only place the API learns a container's real allocation, so it is
        # also where the gauges get their value.
        update_container_resources(lxc_id, cpu_cores=cores, memory_mb=memory)
        return create_response(
            data={"lxc_id": lxc_id, "vm_id": lxc_id, "cores": cores, "memory_mb": memory},
            message=f"Successfully retrieved configuration for container {lxc_id}",
            status_code=200
        )
    except Exception as e:
        return handle_error(e)


@app.route('/resource/node/status', methods=['GET'])
@rate_limit
@require_api_key
@validate_request({'node_name': validate_node_name})
def check_node_status_route():
    node_name = request.validated_data['node_name']
    logging.info(f"Checking status for node {node_name}")
    return check_node_status(node_name)


@app.route('/resource/cluster/status', methods=['GET'])
@rate_limit
@require_api_key
def check_cluster_status_route():
    logging.info("Checking cluster status")
    return check_cluster_status()


# --- Operations --------------------------------------------------------------

@app.route('/health/check', methods=['GET'])
@rate_limit
def health_check_route():
    logging.info("Health check endpoint accessed")
    return health_check()


@app.route('/metrics', methods=['GET'])
def metrics_route():
    return metrics_endpoint()


@app.route('/routes', methods=['GET'])
@rate_limit
@require_api_key
def list_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            "endpoint": rule.endpoint,
            "methods": ','.join(sorted(rule.methods)),
            "url": str(rule)
        })
    logging.info("Routes list endpoint accessed")
    return jsonify(routes), 200


# --- Metrics instrumentation -------------------------------------------------

@app.before_request
def _start_timer():
    request.start_time = time.monotonic()


@app.after_request
def _record_request_metrics(response):
    start_time = getattr(request, 'start_time', None)
    duration = None if start_time is None else time.monotonic() - start_time
    # Both labels are clamped. The endpoint uses the matched rule rather than
    # the raw path; the method is checked against the known verbs, because an
    # unmatched route never reaches @rate_limit (it is a per-view decorator) so
    # a client could mint an unbounded number of series at line rate.
    endpoint = request.url_rule.rule if request.url_rule is not None else 'unmatched'
    method = request.method if request.method in KNOWN_METHODS else 'other'
    record_api_request(method, endpoint, response.status_code, duration)
    return response


if __name__ == "__main__":
    # Defaults preserve the historical behaviour. Bind to 127.0.0.1 in the
    # config when the ML service runs on the same node as the API, which is the
    # standard layout -- the API executes pct commands as root and has no
    # transport security of its own.
    server_config = app.config.get('SERVER', {})
    app.run(
        host=server_config.get('host', '0.0.0.0'),  # noqa: S104 - configurable, see above
        port=server_config.get('port', 5000),
    )
