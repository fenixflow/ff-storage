#!/usr/bin/env python3
"""
Example usage of ff-logger package showing different logger types
and the scoped, instance-based pattern.
"""

import logging

from ff_logger import (
    ConsoleLogger,
    FileLogger,
    JSONLogger,
    NullLogger,
)


def main():
    print("=" * 60)
    print("FF-LOGGER USAGE EXAMPLES")
    print("=" * 60)

    # Example 1: Console Logger with colors
    print("\n1. ConsoleLogger with colors and context:")
    console_logger = ConsoleLogger(
        name="app.main",
        level=logging.INFO,
        context={"service": "example-app", "environment": "development"},
    )

    console_logger.info("Application started")
    console_logger.info("Processing request", request_id="req-123", user_id=42)
    console_logger.warning("Slow response time", duration=1500, endpoint="/api/users")

    # Example 2: Binding context for request-scoped logging
    print("\n2. Bound logger for request scope:")
    request_logger = console_logger.bind(
        request_id="req-456", user_id=100, ip_address="192.168.1.1"
    )

    request_logger.info("Starting request processing")
    request_logger.info("Database query executed", query_time=25)
    request_logger.info("Request completed", status_code=200)

    # Example 3: JSON Logger for structured logging
    print("\n3. JSONLogger for structured output:")
    json_logger = JSONLogger(
        name="app.api", level=logging.DEBUG, context={"service": "api", "version": "1.0.0"}
    )

    json_logger.debug("Debug information", component="auth", action="validate_token")
    json_logger.info("User authenticated", user_id=123, method="oauth2")
    json_logger.error("Database connection failed", retry_count=3, error_code="DB_CONN_FAIL")

    # Example 4: Switching loggers at runtime
    print("\n4. Logger switching (e.g., for testing):")

    def process_data(data, logger=NullLogger):
        """Function that accepts any logger, defaults to NullLogger."""
        logger.info("Starting data processing")
        logger.debug("Loading data from source", source="database")
        logger.info("Data processed successfully", records=len(data))
        return data

    # Use with console logger
    print("  With ConsoleLogger:")
    process_data([1, 2, 3], logger=console_logger)

    # Use default NullLogger (no output)
    print("  With default NullLogger (no output):")
    _ = process_data([4, 5, 6])  # Silent by default

    # Can also use NullLogger directly as a class
    print("  Direct class usage:")
    NullLogger.info("This message goes nowhere")
    NullLogger.error("Neither does this error")

    # Example 5: File Logger with rotation
    print("\n5. FileLogger with rotation:")
    file_logger = FileLogger(
        name="app.file",
        filename="/tmp/example_app.log",
        level=logging.INFO,
        context={"service": "file-example"},
        rotation_type="size",
        max_bytes=1024 * 1024,  # 1MB
        backup_count=3,
    )

    file_logger.info("Logging to file - This goes to /tmp/example_app.log")
    print(f"  Log written to: {file_logger.get_current_log_file()}")

    # Example 6: Exception logging
    print("\n6. Exception logging with traceback:")
    try:
        _ = 10 / 0
    except ZeroDivisionError:
        console_logger.exception("Math error occurred", operation="division")

    print("\n" + "=" * 60)
    print("Examples completed!")


if __name__ == "__main__":
    main()
