from functools import wraps
from flask import request, jsonify, current_app
import time

# Simple in-memory rate limiting for demonstration purposes
rate_limit_data = {}

def rate_limit(f):
    """
    Rate limiting decorator with smart exemptions.
    
    Features:
    - Exempts localhost/127.0.0.1 (internal ML service)
    - Per-IP tracking with sliding window
    - Configurable limits per endpoint
    - Clear error messages with retry-after header
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr
        rate_limiting_config = current_app.config['RATE_LIMITING']
        
        # Exempt localhost - ML service makes many requests
        if client_ip in ['127.0.0.1', '::1', 'localhost']:
            return f(*args, **kwargs)
        
        # Check if rate limiting is disabled
        if not rate_limiting_config.get('enabled', True):
            return f(*args, **kwargs)

        if client_ip not in rate_limit_data:
            rate_limit_data[client_ip] = []

        access_times = rate_limit_data[client_ip]
        current_time = time.time()
        
        # Configurable time window (default 60 seconds)
        time_window = rate_limiting_config.get('time_window_seconds', 60)

        # Filter out access times that are older than the time window
        access_times = [t for t in access_times if current_time - t < time_window]
        rate_limit_data[client_ip] = access_times
        
        max_requests = rate_limiting_config.get('max_requests_per_minute', 60)

        if len(access_times) >= max_requests:
            # Calculate retry-after time
            oldest_request = min(access_times)
            retry_after = int(time_window - (current_time - oldest_request)) + 1
            
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

        access_times.append(current_time)
        
        # Add rate limit headers to successful responses
        response = f(*args, **kwargs)
        if hasattr(response, 'headers'):
            response.headers['X-RateLimit-Limit'] = str(max_requests)
            response.headers['X-RateLimit-Remaining'] = str(max_requests - len(access_times))
        
        return response
    
    return decorated_function
