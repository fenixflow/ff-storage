#!/usr/bin/env python3
"""
Example demonstrating production-ready logging setup with ff-logger.

Shows best practices for setting up logging in production applications,
including error handling, performance considerations, and monitoring.

Created by Ben Moag (Fenixflow)
"""

import logging
import os
from dataclasses import dataclass
from enum import Enum

from ff_logger import ConsoleLogger, FileLogger, JSONLogger, NullLogger


class LogFormat(Enum):
    """Supported log formats."""

    CONSOLE = "console"
    JSON = "json"
    FILE = "file"
    NULL = "null"


@dataclass
class LogConfig:
    """Logging configuration."""

    format: LogFormat
    level: str = "INFO"
    name: str = "app"
    file_path: str | None = None
    rotation_type: str = "time"
    rotation_interval: str = "midnight"
    backup_count: int = 7
    show_hostname: bool = True
    colors: bool = True
    context: dict = None


def create_logger(config: LogConfig):
    """
    Create a logger instance based on configuration.

    This is the recommended pattern for production applications.
    """
    # Set up base context
    context = config.context or {}

    # Add standard production context
    context.update(
        {
            "environment": os.getenv("ENVIRONMENT", "production"),
            "app_version": os.getenv("APP_VERSION", "unknown"),
            "hostname": os.getenv("HOSTNAME", "unknown"),
        }
    )

    # Parse log level
    log_level = getattr(logging, config.level.upper(), logging.INFO)

    # Create appropriate logger based on format
    if config.format == LogFormat.CONSOLE:
        return ConsoleLogger(
            name=config.name,
            level=log_level,
            colors=config.colors and os.isatty(1),  # Only colors if TTY
            show_hostname=config.show_hostname,
            context=context,
        )

    elif config.format == LogFormat.JSON:
        return JSONLogger(
            name=config.name,
            level=log_level,
            show_hostname=config.show_hostname,
            include_timestamp=True,
            context=context,
        )

    elif config.format == LogFormat.FILE:
        if not config.file_path:
            config.file_path = f"/var/log/{config.name}.log"

        return FileLogger(
            name=config.name,
            filename=config.file_path,
            level=log_level,
            rotation_type=config.rotation_type,
            rotation_interval=config.rotation_interval,
            backup_count=config.backup_count,
            context=context,
        )

    else:  # NULL or unknown
        return NullLogger()


def get_logger_from_env():
    """
    Create logger from environment variables.

    This is useful for containerized applications.
    """
    # Read configuration from environment
    log_format = os.getenv("LOG_FORMAT", "json").lower()
    log_level = os.getenv("LOG_LEVEL", "INFO")
    app_name = os.getenv("APP_NAME", "app")

    # Map environment string to enum
    format_map = {
        "console": LogFormat.CONSOLE,
        "json": LogFormat.JSON,
        "file": LogFormat.FILE,
        "null": LogFormat.NULL,
        "none": LogFormat.NULL,
    }

    config = LogConfig(
        format=format_map.get(log_format, LogFormat.JSON),
        level=log_level,
        name=app_name,
        file_path=os.getenv("LOG_FILE"),
        show_hostname=os.getenv("LOG_HOSTNAME", "true").lower() == "true",
        colors=os.getenv("LOG_COLORS", "true").lower() == "true",
    )

    return create_logger(config)


class ApplicationLogger:
    """
    Production-ready logger wrapper with fallback and error handling.
    """

    def __init__(self, config: LogConfig):
        self.config = config
        self._logger = None
        self._fallback_logger = NullLogger()
        self._initialize()

    def _initialize(self):
        """Initialize logger with error handling."""
        try:
            self._logger = create_logger(self.config)
        except Exception as e:
            # If logger creation fails, use console as fallback
            print(f"Failed to create configured logger: {e}")
            try:
                self._logger = ConsoleLogger(name=self.config.name, level=logging.ERROR)
                self._logger.error(
                    "Failed to create configured logger", error=str(e), fallback="console"
                )
            except Exception:
                # If even console fails, use null logger
                self._logger = self._fallback_logger

    def get_logger(self):
        """Get the logger instance."""
        return self._logger or self._fallback_logger

    def bind(self, **kwargs):
        """Create a bound logger with additional context."""
        logger = self.get_logger()
        if hasattr(logger, "bind"):
            return logger.bind(**kwargs)
        return logger


def demonstrate_production_setup():
    """Demonstrate production logging setup."""

    # 1. Development environment (console with colors)
    dev_config = LogConfig(
        format=LogFormat.CONSOLE,
        level="DEBUG",
        name="dev_app",
        colors=True,
        context={"env": "development"},
    )
    dev_logger = create_logger(dev_config)
    dev_logger.debug("Development logger initialized")
    dev_logger.info("This is a development message with colors")

    # 2. Production environment (JSON for log aggregation)
    prod_config = LogConfig(
        format=LogFormat.JSON,
        level="INFO",
        name="prod_app",
        show_hostname=True,
        context={"env": "production", "region": "us-east-1", "service": "api"},
    )
    prod_logger = create_logger(prod_config)
    prod_logger.info("Production logger initialized", startup=True, config="loaded")

    # 3. Request handling with context
    handle_request(prod_logger)

    # 4. Error handling demonstration
    demonstrate_error_handling(prod_logger)


def handle_request(base_logger):
    """Simulate request handling with proper logging."""
    import time
    import uuid

    # Create request-scoped logger
    request_id = str(uuid.uuid4())
    request_logger = base_logger.bind(request_id=request_id, path="/api/users", method="GET")

    start_time = time.time()
    request_logger.info("Request started")

    try:
        # Simulate processing
        time.sleep(0.1)

        # Log successful response
        duration = (time.time() - start_time) * 1000
        request_logger.info("Request completed", status=200, duration_ms=round(duration, 2))

    except Exception as e:
        duration = (time.time() - start_time) * 1000
        request_logger.error(
            "Request failed", status=500, duration_ms=round(duration, 2), error=str(e)
        )


def demonstrate_error_handling(logger):
    """Demonstrate proper error logging in production."""

    # 1. Expected errors (log as warnings or info)
    try:
        validate_user_input({"age": -1})
    except ValueError as e:
        logger.warning("Invalid user input", error=str(e), error_type="validation")

    # 2. Unexpected errors (log with full traceback)
    try:
        risky_operation()
    except Exception:
        logger.exception("Unexpected error in risky operation")

    # 3. Critical errors (log and potentially alert)
    try:
        critical_operation()
    except Exception as e:
        logger.critical(
            "Critical operation failed", error=str(e), alert=True, requires_immediate_attention=True
        )


def validate_user_input(data):
    """Validate user input."""
    if data.get("age", 0) < 0:
        raise ValueError("Age cannot be negative")


def risky_operation():
    """Simulate an operation that might fail."""
    raise RuntimeError("Simulated unexpected error")


def critical_operation():
    """Simulate a critical operation."""
    raise Exception("Database connection lost")


if __name__ == "__main__":
    print("=== Production Logging Setup Demo ===\n")
    demonstrate_production_setup()

    print("\n=== Environment-based Configuration ===")
    # Set some environment variables for demo
    os.environ["LOG_FORMAT"] = "json"
    os.environ["LOG_LEVEL"] = "INFO"
    os.environ["APP_NAME"] = "fenix-api"

    env_logger = get_logger_from_env()
    env_logger.info("Logger created from environment variables")

    print("\n=== Application Logger with Fallback ===")
    app_config = LogConfig(format=LogFormat.JSON, level="INFO", name="fenix-app")
    app_logger_wrapper = ApplicationLogger(app_config)
    app_logger = app_logger_wrapper.get_logger()
    app_logger.info("Application logger ready", has_fallback=True, production_ready=True)
