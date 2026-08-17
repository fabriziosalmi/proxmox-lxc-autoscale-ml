"""Health check endpoint.

The previous implementation returned a hard-coded "healthy" with a fake
"database: connected" line for a component this project does not have. A health
check that cannot fail is worse than none: it makes a broken API look fine to
whatever is watching it.
"""
import logging
import shutil
import subprocess

from flask import current_app, jsonify

# The health check must answer quickly even when the node is struggling.
PROBE_TIMEOUT_SECONDS = 5


def _check_pct():
    """Verify that the pct binary exists and responds."""
    if shutil.which("pct") is None:
        return False, "pct not found in PATH"

    try:
        result = subprocess.run(  # noqa: S603, S607 - fixed argv, no shell
            ["pct", "list"],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, f"pct list timed out after {PROBE_TIMEOUT_SECONDS}s"
    except OSError as e:
        return False, f"pct list could not be executed: {e}"

    if result.returncode != 0:
        return False, f"pct list exited {result.returncode}: {result.stderr.strip()}"

    return True, "ok"


def health_check():
    checks = {}
    healthy = True

    pct_ok, pct_detail = _check_pct()
    checks["lxc_commands"] = {"ok": pct_ok, "detail": pct_detail}
    healthy = healthy and pct_ok

    # Configuration is loaded once at startup; report whether the node the API
    # is supposed to manage was actually configured.
    node = current_app.config.get("LXC_NODE")
    node_ok = bool(node)
    checks["configuration"] = {
        "ok": node_ok,
        "detail": f"node={node}" if node_ok else "lxc.node is not configured",
    }
    healthy = healthy and node_ok

    if not healthy:
        failing = [name for name, check in checks.items() if not check["ok"]]
        logging.warning(f"Health check failed: {', '.join(failing)}")

    return jsonify({
        "status": "healthy" if healthy else "unhealthy",
        "checks": checks,
    }), 200 if healthy else 503
