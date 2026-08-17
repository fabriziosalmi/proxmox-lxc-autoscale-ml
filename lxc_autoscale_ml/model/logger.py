import logging
from logging.handlers import RotatingFileHandler

# Keep 5 rotations of 10 MB each. Without this the log file grows without bound
# on the Proxmox host, and nothing else in the project rotates it.
MAX_LOG_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5


def setup_logging(log_file, log_level="INFO", max_bytes=MAX_LOG_BYTES,
                  backup_count=LOG_BACKUP_COUNT):
    """
    Set up logging to log to both a rotating file and the console.

    :param log_file: Path to the log file.
    :param log_level: The logging level (default is "INFO").
    :param max_bytes: Rotate the log file once it exceeds this size.
    :param backup_count: Number of rotated files to keep.
    """
    # Convert log level string to logging level
    log_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create a logger
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Calling this twice would otherwise attach a second set of handlers and
    # duplicate every log line.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    # Create rotating file handler
    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count
    )
    file_handler.setLevel(log_level)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)

    # Define log format
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
