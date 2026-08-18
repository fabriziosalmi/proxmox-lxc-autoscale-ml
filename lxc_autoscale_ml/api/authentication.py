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

    Expects the API key in the X-API-Key header. The query parameter form was
    removed: it leaked the key into access logs.
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

        # Header only. Accepting ?api_key= put the secret in the gunicorn
        # access log, in shell history, and in any proxy log in front of it.
        api_key = request.headers.get('X-API-Key')

        if not api_key:
            return jsonify({
                "status": "error",
                "message": "Missing API key. Provide it in the X-API-Key header."
            }), 401

        # Verify API key
        valid_keys = auth_config.get('api_keys', [])
        if not valid_keys:
            current_app.logger.warning("API authentication enabled but no keys configured")
            return jsonify({
                "status": "error",
                "message": "API authentication misconfigured"
            }), 500

        # Constant-time comparison. compare_digest raises TypeError on a
        # non-ASCII str, so a configured key containing e.g. a curly quote made
        # EVERY request fail with a 500 and a traceback that never named the
        # key. Compare bytes instead.
        try:
            provided = api_key.encode("utf-8")
            key_valid = any(
                hmac.compare_digest(provided, str(valid_key).encode("utf-8"))
                for valid_key in valid_keys
            )
        except (AttributeError, UnicodeError):
            key_valid = False

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
