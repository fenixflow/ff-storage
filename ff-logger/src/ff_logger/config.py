"""
Configuration system for ff-logger.

Supports environment variables, config files, and programmatic configuration.
"""

import json
import os
from pathlib import Path
from typing import Any

import structlog

from .base import ScopedLogger
from .console import ConsoleLogger
from .database import DatabaseLogger
from .json import JSONLogger
from .null import NullLogger

# Global configuration
_GLOBAL_CONFIG: dict[str, Any] = {
    "level": "INFO",
    "format": "console",
    "add_timestamp": True,
    "add_hostname": False,
    "add_process_info": False,
    "colors": True,
}

# Logger type mapping
_LOGGER_TYPES = {
    "console": ConsoleLogger,
    "json": JSONLogger,
    "database": DatabaseLogger,
    "null": NullLogger,
    "none": NullLogger,  # Alias for null
}


def configure_logging(
    level: str | None = None,
    format: str | None = None,
    add_timestamp: bool | None = None,
    add_hostname: bool | None = None,
    add_process_info: bool | None = None,
    colors: bool | None = None,
    config_file: str | Path | None = None,
    use_env: bool = True,
) -> None:
    """
    Configure global logging settings.

    Args:
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format: Output format (console, json, null)
        add_timestamp: Whether to include timestamps
        add_hostname: Whether to include hostname
        add_process_info: Whether to include process/thread info
        colors: Whether to use colors in console output
        config_file: Path to JSON config file
        use_env: Whether to read from environment variables
    """
    global _GLOBAL_CONFIG

    # Load from config file if provided
    if config_file:
        config_path = Path(config_file)
        if config_path.exists():
            with open(config_path) as f:
                file_config = json.load(f)
                _GLOBAL_CONFIG.update(file_config)

    # Load from environment variables if enabled
    if use_env:
        env_config = _load_env_config()
        _GLOBAL_CONFIG.update(env_config)

    # Apply explicit arguments (highest priority)
    if level is not None:
        _GLOBAL_CONFIG["level"] = level.upper()
    if format is not None:
        _GLOBAL_CONFIG["format"] = format.lower()
    if add_timestamp is not None:
        _GLOBAL_CONFIG["add_timestamp"] = add_timestamp
    if add_hostname is not None:
        _GLOBAL_CONFIG["add_hostname"] = add_hostname
    if add_process_info is not None:
        _GLOBAL_CONFIG["add_process_info"] = add_process_info
    if colors is not None:
        _GLOBAL_CONFIG["colors"] = colors

    # Configure structlog globally
    _configure_structlog()


def _load_env_config() -> dict[str, Any]:
    """Load configuration from environment variables."""
    config = {}

    # FF_LOG_LEVEL
    if level := os.getenv("FF_LOG_LEVEL"):
        config["level"] = level.upper()

    # FF_LOG_FORMAT
    if format := os.getenv("FF_LOG_FORMAT"):
        config["format"] = format.lower()

    # FF_LOG_ADD_TIMESTAMP
    if add_timestamp := os.getenv("FF_LOG_ADD_TIMESTAMP"):
        config["add_timestamp"] = add_timestamp.lower() in ("true", "1", "yes")

    # FF_LOG_ADD_HOSTNAME
    if add_hostname := os.getenv("FF_LOG_ADD_HOSTNAME"):
        config["add_hostname"] = add_hostname.lower() in ("true", "1", "yes")

    # FF_LOG_ADD_PROCESS_INFO
    if add_process := os.getenv("FF_LOG_ADD_PROCESS_INFO"):
        config["add_process_info"] = add_process.lower() in ("true", "1", "yes")

    # FF_LOG_COLORS
    if colors := os.getenv("FF_LOG_COLORS"):
        config["colors"] = colors.lower() in ("true", "1", "yes")

    return config


def _configure_structlog() -> None:
    """Configure structlog based on global settings."""
    processors = []

    # Add standard processors
    processors.extend(
        [
            structlog.stdlib.add_log_level,
        ]
    )

    # Add timestamp if enabled
    if _GLOBAL_CONFIG.get("add_timestamp", True):
        processors.append(structlog.processors.TimeStamper(fmt="iso"))

    # Add stack info and exception formatting
    processors.extend(
        [
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
        ]
    )

    # Add appropriate renderer based on format
    format = _GLOBAL_CONFIG.get("format", "console")
    if format == "json":
        processors.append(structlog.processors.JSONRenderer())
    elif format == "console":
        colors = _GLOBAL_CONFIG.get("colors", True)
        processors.append(structlog.dev.ConsoleRenderer(colors=colors))

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(
    name: str, logger_type: str | None = None, **kwargs: Any
) -> ScopedLogger | ConsoleLogger | JSONLogger | DatabaseLogger | NullLogger:
    """
    Get a logger instance based on configuration.

    Args:
        name: Logger name/scope
        logger_type: Override logger type (console, json, database, null)
        **kwargs: Additional arguments for logger constructor

    Returns:
        Logger instance of the appropriate type

    Example:
        # Uses global config
        logger = get_logger("my_service")

        # Override type
        logger = get_logger("my_service", logger_type="json")

        # With custom settings
        logger = get_logger("my_service", add_hostname=True)
    """
    # Determine logger type
    if logger_type is None:
        logger_type = _GLOBAL_CONFIG.get("format", "console")

    # Get logger class
    logger_class = _LOGGER_TYPES.get(logger_type.lower())
    if logger_class is None:
        raise ValueError(f"Unknown logger type: {logger_type}")

    # Apply global config to kwargs if not specified
    if logger_class in (ConsoleLogger, JSONLogger):
        if "add_hostname" not in kwargs:
            kwargs["add_hostname"] = _GLOBAL_CONFIG.get("add_hostname", False)

    if logger_class == ConsoleLogger:
        if "colors" not in kwargs:
            kwargs["colors"] = _GLOBAL_CONFIG.get("colors", True)

    if logger_class == JSONLogger:
        if "add_process_info" not in kwargs:
            kwargs["add_process_info"] = _GLOBAL_CONFIG.get("add_process_info", False)

    # Create and return logger
    return logger_class(name, **kwargs)


def get_config() -> dict[str, Any]:
    """Get current global configuration."""
    return _GLOBAL_CONFIG.copy()


def reset_config() -> None:
    """Reset configuration to defaults."""
    global _GLOBAL_CONFIG
    _GLOBAL_CONFIG = {
        "level": "INFO",
        "format": "console",
        "add_timestamp": True,
        "add_hostname": False,
        "add_process_info": False,
        "colors": True,
    }
    _configure_structlog()
