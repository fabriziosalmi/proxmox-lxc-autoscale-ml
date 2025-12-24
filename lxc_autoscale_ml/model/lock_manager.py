import os
import sys
import logging
import time

def create_lock_file(lock_file):
    """
    Create a lock file with PID to prevent multiple instances.
    Automatically cleans up stale locks from crashed processes.
    
    Args:
        lock_file: Path to the lock file
        
    Raises:
        SystemExit: If another instance is already running
    """
    # Check if lock file exists
    if os.path.exists(lock_file):
        try:
            # Read the PID from the lock file
            with open(lock_file, 'r') as f:
                content = f.read().strip()
                if not content:
                    logging.warning(f"Lock file {lock_file} is empty, removing stale lock")
                    os.remove(lock_file)
                else:
                    old_pid = int(content)
                    
                    # Check if the process is still running
                    try:
                        # Sending signal 0 checks if process exists without killing it
                        os.kill(old_pid, 0)
                        # Process exists, another instance is running
                        logging.error(f"Another instance is already running with PID {old_pid}. Exiting.")
                        sys.exit(1)
                    except OSError:
                        # Process doesn't exist, it's a stale lock
                        lock_age = time.time() - os.path.getmtime(lock_file)
                        logging.warning(
                            f"Removing stale lock file (PID {old_pid} not running, "
                            f"lock age: {lock_age:.0f}s)"
                        )
                        os.remove(lock_file)
        except (ValueError, IOError) as e:
            logging.warning(f"Error reading lock file {lock_file}: {e}, removing it")
            try:
                os.remove(lock_file)
            except OSError:
                pass
    
    # Create new lock file with current PID
    with open(lock_file, 'w') as lf:
        lf.write(str(os.getpid()))
    logging.info(f"Lock file created at {lock_file} with PID {os.getpid()}.")

def remove_lock_file(lock_file):
    if os.path.exists(lock_file):
        os.remove(lock_file)
        logging.info(f"Lock file {lock_file} removed.")
    else:
        logging.warning(f"Lock file {lock_file} was not found.")
