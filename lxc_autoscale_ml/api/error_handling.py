from flask import jsonify, current_app
import logging

# Centralized error handler
def handle_error(exception, status_code=500):
    error_handling_config = current_app.config.get('ERROR_HANDLING', {})

    # Log the error if logging is enabled
    if error_handling_config.get('log_errors', True):
        logging.error(f"Error occurred: {str(exception)}")

    # Optionally notify on critical errors
    if status_code >= 500 and error_handling_config.get('notify_on_critical_errors', False):
        notify_on_critical_error(exception)

    # Optionally show stack traces (in non-production environments)
    if error_handling_config.get('show_stack_traces', False):
        response = {
            "status": "error",
            "message": str(exception),
            "stack_trace": repr(exception)
        }
    else:
        response = {
            "status": "error",
            "message": "An internal error occurred. Please contact support if the issue persists."
        }

    return jsonify(response), status_code

def notify_on_critical_error(exception):
    """Placeholder for delivering critical-error notifications.

    No transport is configured or implemented. This used to log "Notified
    {recipient} of the error", which is a false statement in the operator's log
    for a message that was never sent -- exactly the kind of thing someone
    relies on during an incident. It now says plainly that nothing was sent.
    """
    error_handling_config = current_app.config.get('ERROR_HANDLING', {})
    recipients = error_handling_config.get('notification_recipients', [])

    logging.warning(
        "notify_on_critical_errors is enabled but no notification transport is "
        "implemented; no message was sent to %s. Error: %s",
        ", ".join(recipients) or "(no recipients configured)",
        exception,
    )
