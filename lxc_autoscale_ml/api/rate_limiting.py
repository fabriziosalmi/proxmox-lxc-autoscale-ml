from functools import wraps
from flask import request, jsonify, current_app
import time
import threading

# Simple in-memory rate limiting for demonstration purposes
rate_limit_data = {}
# Lock to ensure thread-safe access to the shared rate_limit_data dictionary
_rate_limit_lock = threading.Lock()

def rate_limit(f):
    """
    Rate limiting decorator with smart exemptions.

    Features:
    - Exempts localhost/127.0.0.1 (internal ML service)
    - Per-IP tracking with sliding window
    - Configurable limits per endpoint
    - Clear error messages with retry-after header
    - Thread-safe access to shared state
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr
        # Use .get with a default to avoid KeyError if the config is missing
        rate_limiting_config = current_app.config.get('RATE_LIMITING', {})

        # Exempt localhost - ML service makes many requests
        if client_ip in ['127.0.0.1', '::1', 'localhost']:
            return f(*args, **kwargs)

        # Check if rate limiting is disabled (default to enabled when config missing)
        if not rate_limiting_config.get('enabled', True):
            return f(*args, **kwargs)

        current_time = time.time()
        time_window = rate_limiting_config.get('time_window_seconds', 60)
        max_requests = rate_limiting_config.get('max_requests_per_minute', 60)

        # Only the bookkeeping is serialised. The wrapped view runs outside the
        # lock: scaling calls shell out to `pct` and can take seconds, and
        # holding the lock across them would serialise the whole API.
        with _rate_limit_lock:
            # Drop access times that fell out of the sliding window
            access_times = [
                t for t in rate_limit_data.get(client_ip, [])
                if current_time - t < time_window
            ]

            if len(access_times) >= max_requests:
                rate_limit_data[client_ip] = access_times
                oldest_request = min(access_times)
                retry_after = int(time_window - (current_time - oldest_request)) + 1
                limited = (retry_after, oldest_request)
            else:
                access_times.append(current_time)
                rate_limit_data[client_ip] = access_times
                limited = None

            remaining = max(0, max_requests - len(access_times))

        if limited is not None:
            retry_after, oldest_request = limited
            response = jsonify({
                "status": "error",
                "error": "Rate limit exceeded. Please try again later.",
                "retry_after_seconds": retry_after,
                "limit": max_requests,
                "window_seconds": time_window
            })
            response.headers['Retry-After'] = str(retry_after)
            response.headers['X-RateLimit-Limit'] = str(max_requests)
            response.headers['X-RateLimit-Remaining'] = '0'
            response.headers['X-RateLimit-Reset'] = str(int(oldest_request + time_window))
            return response, 429

        response = f(*args, **kwargs)
        if hasattr(response, 'headers'):
            response.headers['X-RateLimit-Limit'] = str(max_requests)
            response.headers['X-RateLimit-Remaining'] = str(remaining)

        return response

    return decorated_function
