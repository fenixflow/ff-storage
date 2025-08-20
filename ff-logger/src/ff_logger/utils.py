"""
Utility functions and constants for ff-logger.
"""

# Standard logging fields to exclude from extra data when displaying
# These are reserved by Python's logging module and cannot be overridden
LOGGING_INTERNAL_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "funcName",
    "id",
    "levelname",
    "levelno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
    "filename",
    "lineno",
}

# Fields that might conflict with LogRecord attributes
# These will be prefixed with 'x_' to avoid conflicts
RESERVED_FIELDS = {
    "module",
    "name",
    "msg",
    "args",
    "created",
    "filename",
    "funcName",
    "id",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "thread",
    "threadName",
}


def extract_extra_fields(record):
    """
    Extract extra fields from a log record, excluding logging internals.

    Args:
        record: A logging.LogRecord instance

    Returns:
        Dictionary containing only user-provided extra fields
    """
    extra_data = {}
    for key, value in record.__dict__.items():
        if key not in LOGGING_INTERNAL_FIELDS:
            extra_data[key] = value
    return extra_data


def format_extra_fields(extra_data, indent=2):
    """
    Format extra fields for console output.

    Args:
        extra_data: Dictionary of extra fields
        indent: Number of spaces to indent (default: 2)

    Returns:
        Formatted string representation of extra fields
    """
    if not extra_data:
        return ""

    lines = []
    for key, value in extra_data.items():
        # Handle different value types
        if isinstance(value, str):
            formatted_value = f'"{value}"'
        elif isinstance(value, bool):
            formatted_value = str(value).lower()
        elif value is None:
            formatted_value = "null"
        else:
            formatted_value = str(value)

        lines.append(f"{' ' * indent}{key}={formatted_value}")

    return "\n".join(lines)
