import logging
import os
import sys
import time

# Bounded so that a pathological loop of "stale lock removed, recreated by
# someone else" cannot spin forever.
MAX_ACQUIRE_ATTEMPTS = 3


def _process_is_running(pid):
    try:
        # Signal 0 checks for existence without touching the process.
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # It exists, it just belongs to someone else.
        return True
    except OSError:
        return True
    return True


def _clear_if_stale(lock_file):
    """Remove the lock if the process that wrote it is gone.

    Returns:
        bool: True if the lock was removed and acquiring can be retried.
    """
    try:
        with open(lock_file) as f:
            content = f.read().strip()
    except FileNotFoundError:
        # Someone else cleaned it up; retry.
        return True
    except OSError as e:
        logging.warning(f"Error reading lock file {lock_file}: {e}, removing it")
        content = ""

    if not content:
        logging.warning(f"Lock file {lock_file} is empty, removing stale lock")
    else:
        try:
            old_pid = int(content)
        except ValueError:
            logging.warning(f"Lock file {lock_file} holds {content!r}, removing stale lock")
        else:
            if _process_is_running(old_pid):
                logging.error(
                    f"Another instance is already running with PID {old_pid}. Exiting.")
                return False
            try:
                lock_age = time.time() - os.path.getmtime(lock_file)
                logging.warning(
                    f"Removing stale lock file (PID {old_pid} not running, "
                    f"lock age: {lock_age:.0f}s)"
                )
            except OSError:
                pass

    try:
        os.remove(lock_file)
    except FileNotFoundError:
        pass
    except OSError as e:
        logging.error(f"Could not remove stale lock file {lock_file}: {e}")
        return False
    return True


def create_lock_file(lock_file):
    """
    Create a lock file holding this PID, to prevent multiple instances.

    The file is created with O_CREAT | O_EXCL so that the check and the create
    are one atomic step. Testing os.path.exists() first and opening afterwards
    left a window in which two instances starting together both saw no lock and
    both proceeded to scale the same containers.

    Stale locks from a crashed process are detected and cleared.

    Args:
        lock_file: Path to the lock file

    Raises:
        SystemExit: If another instance is already running
    """
    for _ in range(MAX_ACQUIRE_ATTEMPTS):
        try:
            fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            if not _clear_if_stale(lock_file):
                sys.exit(1)
            continue
        except OSError as e:
            logging.error(f"Could not create lock file {lock_file}: {e}")
            sys.exit(1)

        with os.fdopen(fd, "w") as lock:
            lock.write(str(os.getpid()))
        logging.info(f"Lock file created at {lock_file} with PID {os.getpid()}.")
        return

    logging.error(
        f"Could not acquire {lock_file} after {MAX_ACQUIRE_ATTEMPTS} attempts. Exiting.")
    sys.exit(1)


def remove_lock_file(lock_file):
    try:
        os.remove(lock_file)
    except FileNotFoundError:
        logging.warning(f"Lock file {lock_file} was not found.")
    except OSError as e:
        logging.error(f"Could not remove lock file {lock_file}: {e}")
    else:
        logging.info(f"Lock file {lock_file} removed.")
