"""
Tests for NullLogger implementation.
"""

import time

from ff_logger import NullLogger


def test_null_logger_class_methods():
    """Test that NullLogger can be used directly as a class without instantiation."""
    # These should all complete instantly without doing anything
    NullLogger.debug("Debug message")
    NullLogger.info("Info message")
    NullLogger.warning("Warning message")
    NullLogger.error("Error message")
    NullLogger.critical("Critical message")
    NullLogger.exception("Exception message")
    NullLogger.log(10, "Log message")

    # No assertions needed - just verify no errors occur


def test_null_logger_as_default_parameter():
    """Test that NullLogger can be used as a default parameter."""

    def process_data(data, logger=NullLogger):
        logger.info("Processing data: %s", data)
        logger.debug("Debug info")
        return data * 2

    # Should work without passing a logger
    result = process_data(5)
    assert result == 10

    # Should also work with an instantiated logger (backward compatibility)
    result = process_data(5, logger=NullLogger())
    assert result == 10


def test_null_logger_backward_compatibility():
    """Test that NullLogger still works when instantiated (backward compatibility)."""
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


def test_null_logger_bind_returns_class():
    """Test that bind() returns the NullLogger class itself."""
    # Class method usage
    bound_logger = NullLogger.bind(request_id="abc123")
    assert bound_logger is NullLogger

    # Should be able to use the "bound" logger immediately
    bound_logger.info("Test message")

    # Instance method usage (backward compatibility)
    logger = NullLogger(name="test.null")
    bound_logger = logger.bind(request_id="abc123")
    # Should return the class, not a new instance
    assert bound_logger is NullLogger


def test_null_logger_performance():
    """Test that NullLogger has minimal overhead."""
    # Time 100,000 log calls - should be very fast
    start = time.perf_counter()
    for i in range(100_000):
        NullLogger.info("Message %d", i, extra_field=i * 2)
    elapsed = time.perf_counter() - start

    # Should complete in well under a second
    assert elapsed < 1.0, f"NullLogger took {elapsed:.3f}s for 100k calls"


def test_null_logger_compatibility_methods():
    """Test compatibility methods for standard logging interface."""
    # Class method usage
    assert NullLogger.isEnabledFor(10) is False
    NullLogger.setLevel(20)
    NullLogger.addHandler(None)
    NullLogger.removeHandler(None)

    assert NullLogger.get_logger() is NullLogger

    # Instance method usage (backward compatibility)
    logger = NullLogger(name="test.compat")
    assert logger.isEnabledFor(10) is False
    logger.setLevel(20)
    logger.addHandler(None)
    logger.removeHandler(None)


def test_null_logger_repr():
    """Test string representation of NullLogger."""
    # Instance repr
    logger = NullLogger(name="test.repr")
    repr_str = repr(logger)
    assert "NullLogger" in repr_str

    # Class repr (if needed in future)
    # This would need special handling in Python


def test_null_logger_accepts_any_arguments():
    """Test NullLogger accepts any arguments without errors."""
    # Should accept any arguments in __init__
    logger = NullLogger(
        name="test.context",
        level=10,
        context={"service": "api", "environment": "production"},
        extra_param="ignored",
        another_param=123,
    )

    # Should still work as expected
    logger.info("Test message", user_id=123)

    # Parameterless instantiation should work
    logger = NullLogger()
    logger.info("Test message")


def test_null_logger_mixed_usage():
    """Test that class and instance methods can be mixed."""
    # Start with class method
    NullLogger.info("Class method call")

    # Create instance
    logger = NullLogger("test")
    logger.info("Instance method call")

    # Back to class method
    NullLogger.error("Another class method call")

    # All should work without errors
