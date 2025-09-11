#!/usr/bin/env python3
"""
Example demonstrating using multiple logger types simultaneously.

Shows how different logger instances can be used for different purposes
within the same application.

Created by Ben Moag (Fenixflow)
"""

import logging
import os
import tempfile

from ff_logger import ConsoleLogger, FileLogger, JSONLogger, NullLogger


def main():
    # Create temporary directory for file logs
    temp_dir = tempfile.mkdtemp()

    # Set up different loggers for different purposes

    # Console logger for human-readable output
    console = ConsoleLogger(
        name="app", level=logging.INFO, colors=True, context={"component": "main"}
    )

    # JSON logger for structured logs (could be sent to log aggregation)
    audit = JSONLogger(
        name="audit", level=logging.INFO, show_hostname=True, context={"audit": True}
    )

    # File logger for persistent logs
    file_logger = FileLogger(
        name="app",
        filename=os.path.join(temp_dir, "app.log"),
        level=logging.DEBUG,  # Capture everything in file
        rotation_type="size",
        max_bytes=10 * 1024 * 1024,  # 10MB
        backup_count=3,
    )

    # Demonstrate using multiple loggers
    console.info("Application starting")
    audit.info("Application startup", user="system", action="start")
    file_logger.debug("Debug: Initializing components")

    # Process some operations with different logging strategies
    process_user_request(console, audit, file_logger)

    # Demonstrate conditional logging
    verbose_mode = False
    debug_logger = file_logger if verbose_mode else NullLogger

    debug_logger.debug("This will only log if verbose_mode is True")

    # Clean up
    console.info(f"Logs written to {temp_dir}")
    print(f"\nFile logs can be found at: {temp_dir}/app.log")


def process_user_request(console, audit, file_logger):
    """Process a user request with multiple logging strategies."""
    user_id = "user-123"
    action = "update_profile"

    # User-facing message
    console.info("Processing user request", user_id=user_id)

    # Audit trail
    audit.info("User action initiated", user_id=user_id, action=action, ip="192.168.1.100")

    # Detailed debug info
    file_logger.debug(
        "Request details",
        user_id=user_id,
        action=action,
        headers={"User-Agent": "Mozilla/5.0"},
        payload={"name": "John Doe", "email": "john@example.com"},
    )

    # Simulate processing
    try:
        # Some operation
        validate_request(user_id, action)
        console.info("Request validated successfully")
        audit.info("Request validation passed", user_id=user_id, action=action)

        # Process the request
        result = perform_action(user_id, action)

        console.info("Request completed", result=result)
        audit.info(
            "User action completed", user_id=user_id, action=action, result=result, status="success"
        )

    except ValueError as e:
        # Log errors to all loggers with appropriate detail level
        console.error("Request failed", error=str(e))
        audit.error(
            "User action failed", user_id=user_id, action=action, error=str(e), status="error"
        )
        file_logger.exception("Detailed error information")


def validate_request(user_id, action):
    """Validate the request (mock implementation)."""
    if not user_id:
        raise ValueError("Invalid user ID")
    # Validation passed


def perform_action(user_id, action):
    """Perform the requested action (mock implementation)."""
    return {"status": "updated", "user_id": user_id}


def demonstrate_logger_selection():
    """Show how to select different loggers based on configuration."""
    # Configuration (could come from environment or config file)
    config = {
        "log_format": "json",  # or "console", "file", "none"
        "log_level": "INFO",
        "log_file": "/tmp/app.log",
    }

    # Select logger based on configuration
    if config["log_format"] == "console":
        logger = ConsoleLogger(name="app", level=getattr(logging, config["log_level"]))
    elif config["log_format"] == "json":
        logger = JSONLogger(name="app", level=getattr(logging, config["log_level"]))
    elif config["log_format"] == "file":
        logger = FileLogger(
            name="app", filename=config["log_file"], level=getattr(logging, config["log_level"])
        )
    else:  # "none" or any other value
        logger = NullLogger()

    # Use the selected logger
    logger.info("Using configured logger", format=config["log_format"])

    return logger


if __name__ == "__main__":
    main()

    print("\n--- Logger Selection Demo ---")
    demonstrate_logger_selection()
