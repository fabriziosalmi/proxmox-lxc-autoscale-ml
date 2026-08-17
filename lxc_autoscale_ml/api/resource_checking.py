import logging
import subprocess

from flask import current_app

from utils import create_response, handle_error

# Fallback used when the app config carries no explicit command timeout.
DEFAULT_TIMEOUT_SECONDS = 30


def _timeout():
    try:
        return current_app.config.get('TIMEOUT', DEFAULT_TIMEOUT_SECONDS)
    except RuntimeError:  # outside an application context
        return DEFAULT_TIMEOUT_SECONDS


def _run(command):
    """
    Run a Proxmox CLI command and return its stdout.

    Commands are always passed as an argument list, never through a shell.
    A non-zero exit status raises, so a failed lookup can no longer be reported
    to the caller as an empty success.
    """
    printable = " ".join(command)
    logging.info("Running command: %s", printable)
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command,
            capture_output=True,
            text=True,
            timeout=_timeout(),
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Command '{printable}' timed out") from e
    except FileNotFoundError as e:
        raise RuntimeError(
            f"'{command[0]}' not found. Is this running on a Proxmox host?"
        ) from e

    if result.returncode != 0:
        raise RuntimeError(
            f"Command '{printable}' failed with exit code "
            f"{result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def check_lxc_status(lxc_id):
    try:
        output = _run(["pct", "status", str(lxc_id)])
        return create_response(
            data=output,
            message=f"Resource status retrieved for container {lxc_id}",
        )
    except Exception as e:
        return handle_error(e)


# Backwards-compatible alias for the historical "vm" naming.
check_vm_status = check_lxc_status


def check_node_status(node_name):
    try:
        output = _run(["pvesh", "get", f"/nodes/{node_name}/status"])
        return create_response(
            data=output,
            message=f"Resource status retrieved for node '{node_name}'",
        )
    except Exception as e:
        return handle_error(e)


def check_cluster_status():
    try:
        output = _run(["pvecm", "status"])
        return create_response(
            data=output,
            message="Cluster resource status retrieved successfully",
        )
    except Exception as e:
        return handle_error(e)
