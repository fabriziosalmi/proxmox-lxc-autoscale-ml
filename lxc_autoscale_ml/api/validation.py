"""Input validation utilities for API endpoints."""
import re
from flask import jsonify
from functools import wraps

class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass

def validate_vm_id(vm_id):
    """
    Validate VM/Container ID.
    
    Args:
        vm_id: VM ID to validate (can be str or int)
        
    Returns:
        int: Validated VM ID
        
    Raises:
        ValidationError: If VM ID is invalid
    """
    try:
        vm_id_int = int(vm_id)
        if vm_id_int < 100 or vm_id_int > 999999:
            raise ValidationError(f"VM ID must be between 100 and 999999, got {vm_id_int}")
        return vm_id_int
    except (ValueError, TypeError):
        raise ValidationError(f"Invalid VM ID format: {vm_id}")

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
    except (ValueError, TypeError):
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
    except (ValueError, TypeError):
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
    except (ValueError, TypeError):
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
    Validate container hostname.
    
    Args:
        hostname: Hostname string
        
    Returns:
        str: Validated hostname
        
    Raises:
        ValidationError: If hostname is invalid
    """
    if not hostname or not isinstance(hostname, str):
        raise ValidationError("Hostname must be a non-empty string")
    
    # RFC 1123 compliant hostname
    if not re.match(r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$', hostname, re.IGNORECASE):
        raise ValidationError(
            f"Hostname must be RFC 1123 compliant "
            f"(alphanumeric and hyphens, max 63 chars): {hostname}"
        )
    
    return hostname

def validate_request(validation_rules):
    """
    Decorator to validate request data against rules.
    
    Args:
        validation_rules: Dict mapping field names to validation functions
        
    Example:
        @validate_request({
            'vm_id': validate_vm_id,
            'cores': validate_cores
        })
        def scale_cores():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import request
            
            # Get data from JSON body or query params
            data = request.json if request.json else request.args.to_dict()
            
            validated_data = {}
            errors = []
            
            for field, validator in validation_rules.items():
                if field not in data:
                    errors.append(f"Missing required field: {field}")
                    continue
                
                try:
                    validated_data[field] = validator(data[field])
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
