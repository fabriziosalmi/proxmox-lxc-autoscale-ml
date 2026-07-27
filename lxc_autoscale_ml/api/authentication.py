"""Simple API authentication middleware."""
import os
from functools import wraps
from flask import request, jsonify, current_app
import hashlib
import hmac

def generate_api_key():
    """Generate a random API key."""
    return os.urandom(32).hex()

def hash_api_key(api_key):
    """Hash an API key for secure storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()

def verify_api_key(provided_key, stored_hash):
    """Verify an API key against stored hash."""
    return hmac.compare_digest(hash_api_key(provided_key), stored_hash)

def require_api_key(f):
    """
    Decorator to require API key authentication.
    
    Expects API key in X-API-Key header or api_key query parameter.
    Configure API keys in lxc_autoscale_api.yaml under 'api_keys' section.
    
    Example config:
        authentication:
            enabled: true
            api_keys:
                - "your-secret-api-key-here"
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_config = current_app.config.get('AUTHENTICATION', {})
        
        # Check if authentication is enabled
        if not auth_config.get('enabled', False):
            return f(*args, **kwargs)
        
        # Get API key from header or query param
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if not api_key:
            return jsonify({
                "status": "error",
                "message": "Missing API key. Provide via X-API-Key header or api_key parameter."
            }), 401
        
        # Verify API key
        valid_keys = auth_config.get('api_keys', [])
        if not valid_keys:
            current_app.logger.warning("API authentication enabled but no keys configured")
            return jsonify({
                "status": "error",
                "message": "API authentication misconfigured"
            }), 500
        
        # Filter out invalid (non-string or empty) keys to prevent TypeError in compare_digest
        valid_keys = [k for k in valid_keys if isinstance(k, str) and len(k) > 0]
        if not valid_keys:
            current_app.logger.warning("API authentication enabled but no valid keys configured")
            return jsonify({
                "status": "error",
                "message": "API authentication misconfigured"
            }), 500
        
        # Simple constant-time comparison
        key_valid = any(hmac.compare_digest(api_key, valid_key) for valid_key in valid_keys)
        
        if not key_valid:
            current_app.logger.warning(f"Invalid API key attempt from {request.remote_addr}")
            return jsonify({
                "status": "error",
                "message": "Invalid API key"
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated_function

def get_client_identifier():
    """Get a unique identifier for the client making the request."""
    # Use API key + IP for rate limiting when auth is enabled
    api_key = request.headers.get('X-API-Key', 'anonymous')
    return f"{request.remote_addr}:{api_key[:8]}"
