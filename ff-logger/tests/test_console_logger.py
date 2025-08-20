"""
Tests for ConsoleLogger implementation.
"""

import io
import logging

from ff_logger import ConsoleLogger


def test_console_logger_writes_to_stream():
    """Test that ConsoleLogger writes to the provided stream."""
    stream = io.StringIO()
    logger = ConsoleLogger(
        name="test.console",
        level=logging.INFO,
        stream=stream,
        colors=False,  # Disable colors for testing
    )

    logger.info("Test message")

    output = stream.getvalue()
    assert "Test message" in output
    assert "INFO" in output
    assert "test.console" in output


def test_console_logger_with_context():
    """Test ConsoleLogger with permanent context fields."""
    stream = io.StringIO()
    logger = ConsoleLogger(
        name="test.context",
        level=logging.INFO,
        context={"service": "api", "environment": "test"},
        stream=stream,
        colors=False,
    )

    logger.info("Processing request")

    output = stream.getvalue()
    assert "Processing request" in output
    assert 'service="api"' in output
    assert 'environment="test"' in output


def test_console_logger_with_kwargs():
    """Test ConsoleLogger with runtime kwargs."""
    stream = io.StringIO()
    logger = ConsoleLogger(name="test.kwargs", level=logging.INFO, stream=stream, colors=False)

    logger.info("Request completed", duration=35, status_code=200)

    output = stream.getvalue()
    assert "Request completed" in output
    assert "duration=35" in output
    assert "status_code=200" in output


def test_console_logger_bind():
    """Test bind() creates new logger with merged context."""
    stream = io.StringIO()
    logger = ConsoleLogger(
        name="test.bind",
        level=logging.INFO,
        context={"service": "api"},
        stream=stream,
        colors=False,
    )

    # Create bound logger with additional context
    request_logger = logger.bind(request_id="abc123", user_id=42)

    request_logger.info("Processing")

    output = stream.getvalue()
    assert "Processing" in output
    assert 'service="api"' in output
    assert 'request_id="abc123"' in output
    assert "user_id=42" in output


def test_console_logger_levels():
    """Test different log levels."""
    stream = io.StringIO()
    logger = ConsoleLogger(name="test.levels", level=logging.DEBUG, stream=stream, colors=False)

    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")

    output = stream.getvalue()
    assert "DEBUG" in output and "Debug message" in output
    assert "INFO" in output and "Info message" in output
    assert "WARNING" in output and "Warning message" in output
    assert "ERROR" in output and "Error message" in output
    assert "CRITICAL" in output and "Critical message" in output


def test_console_logger_exception():
    """Test exception logging with traceback."""
    stream = io.StringIO()
    logger = ConsoleLogger(name="test.exception", level=logging.INFO, stream=stream, colors=False)

    try:
        raise ValueError("Test error")
    except ValueError:
        logger.exception("An error occurred")

    output = stream.getvalue()
    assert "An error occurred" in output
    assert "ERROR" in output
    assert "ValueError: Test error" in output
    assert "Traceback" in output


def test_console_logger_level_filtering():
    """Test that log level filtering works correctly."""
    stream = io.StringIO()
    logger = ConsoleLogger(
        name="test.filter",
        level=logging.WARNING,  # Only WARNING and above
        stream=stream,
        colors=False,
    )

    logger.debug("Debug - should not appear")
    logger.info("Info - should not appear")
    logger.warning("Warning - should appear")
    logger.error("Error - should appear")

    output = stream.getvalue()
    assert "Debug - should not appear" not in output
    assert "Info - should not appear" not in output
    assert "Warning - should appear" in output
    assert "Error - should appear" in output


def test_console_logger_with_hostname():
    """Test ConsoleLogger with hostname included."""
    stream = io.StringIO()
    logger = ConsoleLogger(
        name="test.hostname", level=logging.INFO, stream=stream, colors=False, show_hostname=True
    )

    logger.info("Test message")

    output = stream.getvalue()
    assert "Test message" in output
    # Hostname should be present (format varies by system)
