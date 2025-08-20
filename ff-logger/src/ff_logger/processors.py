"""
Custom structlog processors for ff-logger.

These processors can be used to add custom logic to log processing.
"""

import hashlib
import re
from re import Pattern
from typing import Any


def filter_secrets(
    logger: Any,
    name: str,
    event_dict: dict[str, Any],
    patterns: list[Pattern] | None = None,
) -> dict[str, Any]:
    """
    Filter sensitive information from logs.

    Args:
        logger: Logger instance
        name: Logger name
        event_dict: Event dictionary
        patterns: Optional list of regex patterns to match secrets

    Returns:
        Filtered event dictionary
    """
    if patterns is None:
        # Default patterns for common secrets
        patterns = [
            re.compile(r'(password|passwd|pwd)["\']?\s*[:=]\s*["\']?([^"\'\s]+)', re.I),
            re.compile(r'(token|api_key|apikey)["\']?\s*[:=]\s*["\']?([^"\'\s]+)', re.I),
            re.compile(r'(secret|private_key)["\']?\s*[:=]\s*["\']?([^"\'\s]+)', re.I),
            re.compile(r"Bearer\s+([A-Za-z0-9\-._~+/]+)", re.I),
            re.compile(r"([A-Za-z0-9+/]{40,}={0,2})"),  # Base64 encoded strings
        ]

    def _filter_value(value: Any) -> Any:
        """Recursively filter sensitive values."""
        if isinstance(value, str):
            # Check for exact matches of sensitive keys
            lower_value = value.lower()
            sensitive_keys = [
                "password",
                "passwd",
                "pwd",
                "token",
                "api_key",
                "apikey",
                "secret",
                "private_key",
            ]
            for key in sensitive_keys:
                if key in lower_value:
                    return "***REDACTED***"

            # Also check for patterns like Bearer tokens
            if "bearer" in lower_value.lower():
                return re.sub(
                    r"Bearer\s+[A-Za-z0-9\-._~+/]+", "Bearer ***REDACTED***", value, flags=re.I
                )
            return value
        elif isinstance(value, dict):
            return {k: _filter_value(v) for k, v in value.items()}
        elif isinstance(value, list | tuple):
            return type(value)(_filter_value(item) for item in value)
        return value

    # Filter the event message
    if "event" in event_dict:
        event_dict["event"] = _filter_value(event_dict["event"])

    # Filter all other values
    sensitive_keys = [
        "password",
        "passwd",
        "pwd",
        "token",
        "api_key",
        "apikey",
        "secret",
        "private_key",
    ]
    for key, value in event_dict.items():
        if key != "event":
            # Check if the key itself is sensitive
            if any(k in key.lower() for k in sensitive_keys):
                event_dict[key] = "***REDACTED***"
            else:
                event_dict[key] = _filter_value(value)

    return event_dict


def add_request_id(
    logger: Any,
    name: str,
    event_dict: dict[str, Any],
    request_id_key: str = "request_id",
) -> dict[str, Any]:
    """
    Add request ID from context if available.

    Useful for web applications to track requests across logs.

    Args:
        logger: Logger instance
        name: Logger name
        event_dict: Event dictionary
        request_id_key: Key to look for request ID

    Returns:
        Event dictionary with request ID if available
    """
    # Try to get request ID from various sources
    import contextvars

    # Check if there's a context variable for request ID
    try:
        request_id_var = contextvars.ContextVar(request_id_key)
        request_id = request_id_var.get()
        if request_id:
            event_dict[request_id_key] = request_id
    except (LookupError, AttributeError):
        pass

    # Check if it's already in the event dict context
    if hasattr(logger, "_context") and request_id_key in logger._context:
        event_dict[request_id_key] = logger._context[request_id_key]

    return event_dict


def add_correlation_id(
    logger: Any,
    name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """
    Add a correlation ID to track related log entries.

    Args:
        logger: Logger instance
        name: Logger name
        event_dict: Event dictionary

    Returns:
        Event dictionary with correlation ID
    """
    import uuid

    # Check if correlation ID already exists
    if "correlation_id" not in event_dict:
        # Try to get from logger context
        if hasattr(logger, "_context") and "correlation_id" in logger._context:
            event_dict["correlation_id"] = logger._context["correlation_id"]
        else:
            # Generate new correlation ID
            event_dict["correlation_id"] = str(uuid.uuid4())

    return event_dict


def hash_user_data(
    logger: Any,
    name: str,
    event_dict: dict[str, Any],
    fields_to_hash: list[str] | None = None,
) -> dict[str, Any]:
    """
    Hash sensitive user data for privacy compliance.

    Args:
        logger: Logger instance
        name: Logger name
        event_dict: Event dictionary
        fields_to_hash: List of field names to hash

    Returns:
        Event dictionary with hashed user data
    """
    if fields_to_hash is None:
        fields_to_hash = ["email", "user_email", "username", "user_id", "ip_address"]

    def _hash_value(value: str) -> str:
        """Create a consistent hash of a value."""
        return hashlib.sha256(value.encode()).hexdigest()[:16]

    for field in fields_to_hash:
        if field in event_dict and isinstance(event_dict[field], str):
            event_dict[f"{field}_hash"] = _hash_value(event_dict[field])
            event_dict[field] = "***HASHED***"

    return event_dict


def add_environment(
    logger: Any,
    name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """
    Add environment information to logs.

    Args:
        logger: Logger instance
        name: Logger name
        event_dict: Event dictionary

    Returns:
        Event dictionary with environment info
    """
    import os

    # Add environment from env variable
    if env := os.getenv("ENVIRONMENT", os.getenv("ENV")):
        event_dict["environment"] = env

    # Add deployment info if available
    if deployment := os.getenv("DEPLOYMENT_ID"):
        event_dict["deployment_id"] = deployment

    if version := os.getenv("APP_VERSION"):
        event_dict["app_version"] = version

    return event_dict


def rate_limit_logs(
    logger: Any,
    name: str,
    event_dict: dict[str, Any],
    max_per_second: int = 100,
) -> dict[str, Any] | None:
    """
    Rate limit log output to prevent log flooding.

    Args:
        logger: Logger instance
        name: Logger name
        event_dict: Event dictionary
        max_per_second: Maximum logs per second

    Returns:
        Event dictionary or None if rate limited
    """
    import time
    from collections import deque

    # Use a class variable to store timestamps
    if not hasattr(rate_limit_logs, "_timestamps"):
        rate_limit_logs._timestamps = deque(maxlen=max_per_second)

    current_time = time.time()

    # Remove old timestamps
    while rate_limit_logs._timestamps and rate_limit_logs._timestamps[0] < current_time - 1:
        rate_limit_logs._timestamps.popleft()

    # Check if we're over the limit
    if len(rate_limit_logs._timestamps) >= max_per_second:
        return None  # Drop this log

    # Add current timestamp
    rate_limit_logs._timestamps.append(current_time)

    return event_dict


def add_performance_metrics(
    logger: Any,
    name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """
    Add performance metrics to logs.

    Args:
        logger: Logger instance
        name: Logger name
        event_dict: Event dictionary

    Returns:
        Event dictionary with performance metrics
    """
    import os

    import psutil

    try:
        # Add memory usage
        process = psutil.Process(os.getpid())
        event_dict["memory_mb"] = process.memory_info().rss / 1024 / 1024
        event_dict["cpu_percent"] = process.cpu_percent()

        # Add system metrics
        event_dict["system_cpu_percent"] = psutil.cpu_percent()
        event_dict["system_memory_percent"] = psutil.virtual_memory().percent
    except Exception:
        # Don't fail logging if we can't get metrics
        pass

    return event_dict
