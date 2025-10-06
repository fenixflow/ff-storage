"""
Utility functions and constants for ff-logger.
"""

import inspect
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID


def normalize_level(level: int | str) -> int:
    """
    Convert string or int level to logging constant.

    Args:
        level: Log level as int or string (case-insensitive)

    Returns:
        Integer logging level constant
    """
    if isinstance(level, str):
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "WARN": logging.WARNING,  # Common alias
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return level_map.get(level.upper(), logging.INFO)
    return level


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

# Reserved LogRecord fields that will be prefixed with 'x_' to avoid conflicts
# Uses LOGGING_INTERNAL_FIELDS for comprehensive coverage of all Python logging internals
RESERVED_FIELDS = frozenset(LOGGING_INTERNAL_FIELDS)


def _json_default(o: Any) -> Any:
    """
    JSON encoder default function for non-standard types.

    Args:
        o: Object to encode

    Returns:
        JSON-serializable representation of the object
    """
    if isinstance(o, datetime | date):
        return o.isoformat()
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, UUID | Path):
        return str(o)
    if isinstance(o, Decimal):
        return float(o)
    try:
        return str(o)
    except Exception:
        return repr(o)


def _safe_json_dumps(obj: Any) -> str:
    """
    Safely dump object to JSON string, never raising exceptions.

    Args:
        obj: Object to serialize

    Returns:
        JSON string, or fallback error representation if serialization fails
    """
    try:
        return json.dumps(obj, ensure_ascii=False, allow_nan=False, default=_json_default)
    except Exception as e:
        return json.dumps({"_ff_json_fallback": True, "error": repr(e), "payload": repr(obj)})


def _resolve(v: Any) -> Any:
    """
    Resolve lazy values by calling callables.

    Args:
        v: Value to resolve (callable or non-callable)

    Returns:
        Resolved value
    """
    return v() if callable(v) else v


def _format(msg: str, args: tuple) -> str:
    """
    Safely format message with args, catching format errors.

    Args:
        msg: Message format string
        args: Arguments for formatting

    Returns:
        Formatted message, or message with error notation if formatting fails
    """
    if not args:
        return msg
    try:
        return msg % args
    except Exception as e:
        return f"{msg} [format_error={e!r}]"


def _caller_fields(stacklevel: int = 2) -> dict[str, Any]:
    """
    Extract caller metadata from the stack.

    Args:
        stacklevel: How many frames up the stack to look

    Returns:
        Dictionary with file, line, and func fields
    """
    try:
        frame = inspect.stack()[stacklevel]
        return {"file": frame.filename, "line": frame.lineno, "func": frame.function}
    except Exception:
        return {}


def _sanitize_keys(d: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize dictionary keys by prefixing reserved fields.

    Args:
        d: Dictionary with potentially reserved keys

    Returns:
        Dictionary with reserved keys prefixed with 'x_'
    """
    out = {}
    for k, v in d.items():
        k2 = f"x_{k}" if k in RESERVED_FIELDS else k
        out[k2] = v
    return out


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
