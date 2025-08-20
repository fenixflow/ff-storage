"""
Tests for ScopedLogger base class.
"""

import io
import logging

from ff_logger import ScopedLogger


def test_scoped_logger_initialization():
    """Test ScopedLogger initialization."""
    logger = ScopedLogger(name="test.base", level=logging.INFO)

    assert logger.name == "test.base"
    assert logger.level == logging.INFO
    assert logger.context == {}
    assert logger.logger.level == logging.INFO
    assert logger.logger.propagate is False


def test_scoped_logger_with_context():
    """Test ScopedLogger with initial context."""
    logger = ScopedLogger(
        name="test.context", level=logging.DEBUG, context={"service": "api", "version": "1.0"}
    )

    assert logger.context == {"service": "api", "version": "1.0"}


def test_scoped_logger_get_logger():
    """Test get_logger() returns the underlying logger."""
    logger = ScopedLogger(name="test.get")
    underlying = logger.get_logger()

    assert isinstance(underlying, logging.Logger)
    assert underlying.name == "test.get"


def test_scoped_logger_bind():
    """Test bind() creates new logger with merged context."""
    logger = ScopedLogger(name="test.bind", context={"service": "api"})

    bound = logger.bind(request_id="abc123", user_id=42)

    assert isinstance(bound, ScopedLogger)
    assert bound.name == "test.bind.bound"
    assert bound.context == {"service": "api", "request_id": "abc123", "user_id": 42}


def test_scoped_logger_bind_preserves_handlers():
    """Test bind() preserves handlers from parent logger."""
    logger = ScopedLogger(name="test.handlers")

    # Add a test handler
    handler = logging.StreamHandler(io.StringIO())
    logger.logger.addHandler(handler)

    bound = logger.bind(extra="value")

    # Bound logger should have the same handler
    assert len(bound.logger.handlers) == 1
    assert bound.logger.handlers[0] == handler


def test_scoped_logger_clears_existing_handlers():
    """Test that ScopedLogger clears pre-existing handlers."""
    # Create a logger with a handler
    test_logger = logging.getLogger("test.clear")
    test_logger.addHandler(logging.StreamHandler())

    # Create ScopedLogger with same name
    logger = ScopedLogger(name="test.clear")

    # Should have no handlers (cleared during init)
    assert len(logger.logger.handlers) == 0


def test_scoped_logger_no_propagation():
    """Test that ScopedLogger disables propagation."""
    logger = ScopedLogger(name="test.propagate")

    assert logger.logger.propagate is False


def test_scoped_logger_log_methods():
    """Test that log methods work with a handler attached."""
    stream = io.StringIO()
    logger = ScopedLogger(name="test.methods", level=logging.DEBUG)

    # Add a handler to capture output
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    logger.logger.addHandler(handler)

    # Test all log methods
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")

    output = stream.getvalue()
    assert "DEBUG: Debug message" in output
    assert "INFO: Info message" in output
    assert "WARNING: Warning message" in output
    assert "ERROR: Error message" in output
    assert "CRITICAL: Critical message" in output


def test_scoped_logger_exception():
    """Test exception logging."""
    stream = io.StringIO()
    logger = ScopedLogger(name="test.exception")

    # Add handler
    handler = logging.StreamHandler(stream)
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    logger.logger.addHandler(handler)

    try:
        raise ValueError("Test error")
    except ValueError:
        logger.exception("An error occurred")

    output = stream.getvalue()
    assert "ERROR: An error occurred" in output
    assert "ValueError: Test error" in output
