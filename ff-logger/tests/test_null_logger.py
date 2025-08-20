"""
Tests for NullLogger implementation.
"""

import time

from ff_logger import NullLogger


def test_null_logger_does_nothing():
    """Test that NullLogger methods are no-ops."""
    logger = NullLogger(name="test.null")

    # These should all complete instantly without doing anything
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")
    logger.exception("Exception message")
    logger.log(10, "Log message")

    # No assertions needed - just verify no errors occur


def test_null_logger_bind():
    """Test that bind() returns a new NullLogger."""
    logger = NullLogger(name="test.null", context={"service": "api"})

    bound_logger = logger.bind(request_id="abc123")

    assert isinstance(bound_logger, NullLogger)
    assert bound_logger.name == "test.null.bound"
    assert bound_logger.context == {"service": "api", "request_id": "abc123"}


def test_null_logger_performance():
    """Test that NullLogger has minimal overhead."""
    logger = NullLogger(name="test.perf")

    # Time 100,000 log calls - should be very fast
    start = time.perf_counter()
    for i in range(100_000):
        logger.info("Message %d", i, extra_field=i * 2)
    elapsed = time.perf_counter() - start

    # Should complete in well under a second
    assert elapsed < 1.0, f"NullLogger took {elapsed:.3f}s for 100k calls"


def test_null_logger_compatibility_methods():
    """Test compatibility methods for standard logging interface."""
    logger = NullLogger(name="test.compat")

    # These should all work without errors
    assert logger.isEnabledFor(10) is False
    logger.setLevel(20)
    logger.addHandler(None)
    logger.removeHandler(None)

    assert logger.get_logger() is logger


def test_null_logger_repr():
    """Test string representation of NullLogger."""
    logger = NullLogger(name="test.repr")

    repr_str = repr(logger)
    assert "NullLogger" in repr_str
    assert "test.repr" in repr_str


def test_null_logger_with_context():
    """Test NullLogger accepts context but doesn't use it."""
    logger = NullLogger(
        name="test.context",
        level=10,  # Accepted but ignored
        context={"service": "api", "environment": "production"},
    )

    # Context is stored but not used
    assert logger.context == {"service": "api", "environment": "production"}

    # Logging should still be a no-op
    logger.info("Test message", user_id=123)
