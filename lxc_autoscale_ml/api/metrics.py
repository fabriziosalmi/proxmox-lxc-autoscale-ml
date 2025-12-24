"""Prometheus metrics exporter for LXC AutoScale."""
try:
    from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
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
    
    container_cpu_usage_percent = Gauge(
        'lxc_autoscale_container_cpu_usage_percent',
        'Current CPU usage percentage',
        ['container_id']
    )
    
    container_memory_usage_mb = Gauge(
        'lxc_autoscale_container_memory_usage_mb',
        'Current memory usage in MB',
        ['container_id']
    )
    
    # Model Metrics
    model_predictions_total = Counter(
        'lxc_autoscale_model_predictions_total',
        'Total ML model predictions',
        ['container_id', 'prediction']
    )
    
    model_confidence = Histogram(
        'lxc_autoscale_model_confidence',
        'ML model confidence scores',
        ['container_id']
    )
    
    # Circuit Breaker Metrics
    circuit_breaker_state = Gauge(
        'lxc_autoscale_circuit_breaker_state',
        'Circuit breaker state (0=closed, 1=open)',
        ['service']
    )
    
    circuit_breaker_failures = Counter(
        'lxc_autoscale_circuit_breaker_failures_total',
        'Total circuit breaker failures',
        ['service']
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

def update_container_resources(container_id, cpu_cores=None, memory_mb=None, 
                               cpu_usage=None, memory_usage=None):
    """Update container resource metrics."""
    if not PROMETHEUS_AVAILABLE:
        return
    
    if cpu_cores is not None:
        container_cpu_cores.labels(container_id=container_id).set(cpu_cores)
    if memory_mb is not None:
        container_memory_mb.labels(container_id=container_id).set(memory_mb)
    if cpu_usage is not None:
        container_cpu_usage_percent.labels(container_id=container_id).set(cpu_usage)
    if memory_usage is not None:
        container_memory_usage_mb.labels(container_id=container_id).set(memory_usage)

def record_model_prediction(container_id, prediction, confidence):
    """Record ML model prediction metrics."""
    if not PROMETHEUS_AVAILABLE:
        return
    
    prediction_label = 'anomaly' if prediction == -1 else 'normal'
    model_predictions_total.labels(
        container_id=container_id,
        prediction=prediction_label
    ).inc()
    model_confidence.labels(container_id=container_id).observe(confidence)

def update_circuit_breaker_state(service, is_open):
    """Update circuit breaker state metric."""
    if not PROMETHEUS_AVAILABLE:
        return
    
    circuit_breaker_state.labels(service=service).set(1 if is_open else 0)

def record_circuit_breaker_failure(service):
    """Record circuit breaker failure."""
    if not PROMETHEUS_AVAILABLE:
        return
    
    circuit_breaker_failures.labels(service=service).inc()

# Log warning if Prometheus is not available
if not PROMETHEUS_AVAILABLE:
    logging.warning(
        "Prometheus client not installed. Metrics export disabled. "
        "Install with: pip install prometheus-client"
    )
