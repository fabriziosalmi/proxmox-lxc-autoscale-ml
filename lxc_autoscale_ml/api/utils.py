from flask import jsonify

# Re-exported so the two historical import paths (`utils` and `error_handling`)
# share one implementation instead of drifting apart.
from error_handling import handle_error  # noqa: F401

def create_response(data=None, message=None, status_code=200):
    response = {
        'status': 'success' if status_code < 400 else 'error',
        'message': message,
        'data': data
    }
    return jsonify(response), status_code
