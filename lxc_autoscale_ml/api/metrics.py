"""Prometheus metrics exporter for LXC AutoScale.

Only the API process serves /metrics, so only metrics the API can populate are
declared here. Model-prediction and circuit-breaker metrics used to be declared
as well, but they belong to the separate ML process, which has no exporter --
so they appeared on /metrics and were permanently empty. Reintroduce them
alongside an exporter in that process.
"""
try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

from flask import Response
import logging

if PROMETHEUS_AVAILABLE:
    # API Request Metrics
    api_requests_total = Counter(
        'lxc_autoscale_api_requests_total',
        'Total API requests',
        ['method', 'endpoint', 'status']
    )

    api_request_duration = Histogram(
        'lxc_autoscale_api_request_duration_seconds',
        'API request duration in seconds',
        ['method', 'endpoint']
    )

    # Scaling Metrics
    scaling_actions_total = Counter(
        'lxc_autoscale_scaling_actions_total',
        'Total scaling actions performed',
        ['container_id', 'resource', 'action']
    )

    scaling_failures_total = Counter(
        'lxc_autoscale_scaling_failures_total',
        'Total scaling action failures',
        ['container_id', 'resource', 'reason']
    )

    # Container Resource Metrics
    container_cpu_cores = Gauge(
        'lxc_autoscale_container_cpu_cores',
        'Current CPU cores allocated',
        ['container_id']
    )

    container_memory_mb = Gauge(
        'lxc_autoscale_container_memory_mb',
        'Current memory allocated in MB',
        ['container_id']
    )


def metrics_endpoint():
    """Generate Prometheus metrics endpoint."""
    if not PROMETHEUS_AVAILABLE:
        return Response(
            "Prometheus client not installed. Install with: pip install prometheus-client",
            status=501,
            mimetype='text/plain'
        )

    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

def record_api_request(method, endpoint, status, duration=None):
    """Record API request metrics."""
    if not PROMETHEUS_AVAILABLE:
        return

    api_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
    if duration is not None:
        api_request_duration.labels(method=method, endpoint=endpoint).observe(duration)

def record_scaling_action(container_id, resource, action, success=True, failure_reason=None):
    """Record scaling action metrics."""
    if not PROMETHEUS_AVAILABLE:
        return

    if success:
        scaling_actions_total.labels(
            container_id=container_id,
            resource=resource,
            action=action
        ).inc()
    else:
        scaling_failures_total.labels(
            container_id=container_id,
            resource=resource,
            reason=failure_reason or 'unknown'
        ).inc()

def update_container_resources(container_id, cpu_cores=None, memory_mb=None):
    """Update the gauges for a container's allocated resources.

    Usage figures are collected by the monitor, which the API never sees, so
    there are no usage gauges here.
    """
    if not PROMETHEUS_AVAILABLE:
        return

    if cpu_cores is not None:
        container_cpu_cores.labels(container_id=container_id).set(cpu_cores)
    if memory_mb is not None:
        container_memory_mb.labels(container_id=container_id).set(memory_mb)


# Log warning if Prometheus is not available
if not PROMETHEUS_AVAILABLE:
    logging.warning(
        "Prometheus client not installed. Metrics export disabled. "
        "Install with: pip install prometheus-client"
    )
