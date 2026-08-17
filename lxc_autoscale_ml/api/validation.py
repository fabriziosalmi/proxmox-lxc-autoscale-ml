"""Input validation utilities for API endpoints."""
import re
from flask import jsonify, request
from functools import wraps

# Accepted alternative spellings for a field. The canonical name is the key;
# requests may use any of the aliases instead. This lets the API speak the
# accurate "lxc" vocabulary while staying compatible with the historical
# "vm" one that existing deployments send.
FIELD_ALIASES = {
    'vm_id': ('lxc_id', 'container_id'),
    'new_vm_id': ('new_lxc_id',),
    'new_vm_name': ('new_lxc_name', 'hostname'),
}

class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass

def validate_lxc_id(lxc_id):
    """
    Validate LXC container ID.

    Args:
        lxc_id: Container ID to validate (can be str or int)

    Returns:
        int: Validated container ID

    Raises:
        ValidationError: If the container ID is invalid
    """
    try:
        lxc_id_int = int(lxc_id)
    except (ValueError, TypeError, OverflowError):
        raise ValidationError(f"Invalid container ID format: {lxc_id}")
    if lxc_id_int < 100 or lxc_id_int > 999999:
        raise ValidationError(f"Container ID must be between 100 and 999999, got {lxc_id_int}")
    return lxc_id_int

# Backwards-compatible alias: the codebase historically called containers "VMs".
validate_vm_id = validate_lxc_id

def validate_cores(cores):
    """
    Validate CPU cores value.
    
    Args:
        cores: Number of CPU cores
        
    Returns:
        int: Validated cores
        
    Raises:
        ValidationError: If cores value is invalid
    """
    try:
        cores_int = int(cores)
        if cores_int < 1 or cores_int > 128:
            raise ValidationError(f"Cores must be between 1 and 128, got {cores_int}")
        return cores_int
    except (ValueError, TypeError, OverflowError):
        raise ValidationError(f"Invalid cores format: {cores}")

def validate_memory(memory):
    """
    Validate memory value in MB.
    
    Args:
        memory: Memory in MB
        
    Returns:
        int: Validated memory value
        
    Raises:
        ValidationError: If memory value is invalid
    """
    try:
        memory_int = int(memory)
        if memory_int < 64 or memory_int > 1048576:  # 64MB to 1TB
            raise ValidationError(f"Memory must be between 64 and 1048576 MB, got {memory_int}")
        return memory_int
    except (ValueError, TypeError, OverflowError):
        raise ValidationError(f"Invalid memory format: {memory}")

def validate_disk_size(disk_size):
    """
    Validate disk size in GB.
    
    Args:
        disk_size: Disk size in GB
        
    Returns:
        int: Validated disk size
        
    Raises:
        ValidationError: If disk size is invalid
    """
    try:
        disk_int = int(disk_size)
        if disk_int < 1 or disk_int > 10240:  # 1GB to 10TB
            raise ValidationError(f"Disk size must be between 1 and 10240 GB, got {disk_int}")
        return disk_int
    except (ValueError, TypeError, OverflowError):
        raise ValidationError(f"Invalid disk size format: {disk_size}")

def validate_snapshot_name(snapshot_name):
    """
    Validate snapshot name.
    
    Args:
        snapshot_name: Snapshot name string
        
    Returns:
        str: Validated snapshot name
        
    Raises:
        ValidationError: If snapshot name is invalid
    """
    if not snapshot_name or not isinstance(snapshot_name, str):
        raise ValidationError("Snapshot name must be a non-empty string")
    
    # Allow alphanumeric, hyphens, underscores, max 40 chars
    if not re.match(r'^[a-zA-Z0-9_-]{1,40}$', snapshot_name):
        raise ValidationError(
            f"Snapshot name must contain only alphanumeric characters, "
            f"hyphens, and underscores (max 40 chars): {snapshot_name}"
        )
    
    return snapshot_name

def validate_hostname(hostname):
    """
    Validate a container hostname.

    Underscores are accepted for convenience and normalised to hyphens, because
    ``pct`` rejects them but callers have historically passed names like
    ``cloned_container``.

    Args:
        hostname: Hostname string

    Returns:
        str: Validated, RFC 1123 compliant hostname

    Raises:
        ValidationError: If hostname is invalid
    """
    if not hostname or not isinstance(hostname, str):
        raise ValidationError("Hostname must be a non-empty string")

    normalised = hostname.replace('_', '-')

    # RFC 1123 compliant hostname
    if not re.match(r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$', normalised, re.IGNORECASE):
        raise ValidationError(
            f"Hostname must be RFC 1123 compliant "
            f"(alphanumeric and hyphens, max 63 chars): {hostname}"
        )

    return normalised

def validate_node_name(node_name):
    """
    Validate a Proxmox node name.

    Args:
        node_name: Node name string

    Returns:
        str: Validated node name

    Raises:
        ValidationError: If the node name is invalid
    """
    if not node_name or not isinstance(node_name, str):
        raise ValidationError("Node name must be a non-empty string")

    if not re.match(r'^[a-z0-9]([a-z0-9.-]{0,61}[a-z0-9])?$', node_name, re.IGNORECASE):
        raise ValidationError(
            f"Node name must be alphanumeric with hyphens or dots (max 63 chars): {node_name}"
        )

    return node_name

def extract_request_data():
    """
    Collect request parameters from the query string and the JSON body.

    ``request.get_json(silent=True)`` returns ``None`` instead of aborting the
    request when there is no body or the Content-Type is not JSON, which is the
    normal situation for a GET. Reading ``request.json`` directly there raises
    and Flask turns that into a 400/415 before the view ever runs.

    Returns:
        dict: Merged parameters, with JSON body values taking precedence.
    """
    data = request.args.to_dict()

    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        data.update(payload)

    return data

def lookup_field(data, field):
    """
    Read ``field`` from ``data``, falling back to its registered aliases.

    Returns:
        tuple: (found, value)
    """
    if field in data:
        return True, data[field]

    for alias in FIELD_ALIASES.get(field, ()):
        if alias in data:
            return True, data[alias]

    return False, None

def validate_request(validation_rules, optional_fields=None):
    """
    Decorator to validate request data against rules.

    Data is read from the query string and the JSON body alike, so the same
    endpoint works with ``?lxc_id=104`` and with a JSON payload.

    Args:
        validation_rules: Dict mapping field names to validation functions
        optional_fields: Iterable of field names that may be omitted

    Example:
        @validate_request({
            'vm_id': validate_lxc_id,
            'cores': validate_cores
        })
        def scale_cores():
            ...
    """
    optional = set(optional_fields or ())

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            data = extract_request_data()

            validated_data = {}
            errors = []

            for field, validator in validation_rules.items():
                found, value = lookup_field(data, field)
                if not found:
                    if field not in optional:
                        errors.append(f"Missing required field: {field}")
                    continue

                try:
                    validated_data[field] = validator(value)
                except ValidationError as e:
                    errors.append(str(e))

            if errors:
                return jsonify({
                    "status": "error",
                    "message": "Validation failed",
                    "errors": errors
                }), 400

            # Inject validated data into request context
            request.validated_data = validated_data

            return f(*args, **kwargs)

        return decorated_function
    return decorator
