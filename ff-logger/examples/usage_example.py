#!/usr/bin/env python3
"""
Example usage of ff-logger package showing different logger types
and the scoped, instance-based pattern.
"""

from ff_logger import (
    ConsoleLogger,
    FileLogger,
    JSONLogger,
    NullLogger,
)

# Note: With v0.3.0+, you don't need to import logging for basic use!
# You can use string levels like "INFO", "DEBUG", etc.


def main():
    print("=" * 60)
    print("FF-LOGGER USAGE EXAMPLES")
    print("=" * 60)

    # Example 1: Console Logger with string levels (new in v0.3.0)
    print("\n1. ConsoleLogger with string levels and context:")
    console_logger = ConsoleLogger(
        name="app.main",
        level="INFO",  # String levels are now supported! (v0.3.0+)
        context={"service": "example-app", "environment": "development"},
    )

    console_logger.info("Application started")
    console_logger.info("Processing request", request_id="req-123", user_id=42)
    console_logger.warning("Slow response time", duration=1500, endpoint="/api/users")

    # Example 2: Binding context (simplified in v0.3.0)
    print("\n2. Context binding (now modifies in place):")
    # bind() now modifies the logger in place and returns self for chaining
    console_logger.bind(request_id="req-456", user_id=100, ip_address="192.168.1.1")

    console_logger.info("Starting request processing")
    console_logger.info("Database query executed", query_time=25)
    console_logger.info("Request completed", status_code=200)

    # You can also chain bind() calls
    console_logger.bind(session_id="xyz-789").info("Session established")

    # Example 3: JSON Logger with case-insensitive string levels
    print("\n3. JSONLogger with case-insensitive levels:")
    json_logger = JSONLogger(
        name="app.api",
        level="debug",  # Case-insensitive! "debug" == "DEBUG"
        context={"service": "api", "version": "1.0.0"},
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

    # Example 5: File Logger with string levels
    print("\n5. FileLogger with string levels:")
    file_logger = FileLogger(
        name="app.file",
        filename="/tmp/example_app.log",
        level="WARNING",  # String level
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

    # Example 7: Flexible level formats (new in v0.3.0)
    print("\n7. Different ways to specify log levels:")

    # All of these are equivalent:
    ConsoleLogger("test1", level="INFO")
    ConsoleLogger("test2", level="info")  # Case-insensitive
    ConsoleLogger("test3", level=20)  # Numeric value

    # WARN is an alias for WARNING
    logger4 = ConsoleLogger("test4", level="WARN")
    logger4.warning("This works with WARN level")

    print("  All loggers created successfully!")

    print("\n" + "=" * 60)
    print("Examples completed!")
    print("\nNew in v0.3.0:")
    print('  - String log levels ("INFO", "DEBUG", etc.)')
    print('  - Case-insensitive levels ("info" == "INFO")')
    print("  - Simplified bind() that modifies in place")
    print("  - Context validation with helpful errors")


if __name__ == "__main__":
    main()
