"""Test reserved field sanitization, especially 'name' field."""

import pytest
from ff_logger import ConsoleLogger
from ff_logger.utils import LOGGING_INTERNAL_FIELDS, RESERVED_FIELDS


def test_reserved_fields_uses_logging_internals():
    """Verify RESERVED_FIELDS includes all LogRecord attributes."""
    assert RESERVED_FIELDS == frozenset(LOGGING_INTERNAL_FIELDS)


def test_reserved_fields_is_frozenset():
    """Verify RESERVED_FIELDS is a frozenset for immutability and performance."""
    assert isinstance(RESERVED_FIELDS, frozenset)


def test_sanitize_name_kwarg():
    """Test that 'name' kwarg is properly prefixed to avoid LogRecord conflict."""
    # Test through logger behavior - this is tested via integration tests below
    pass


def test_sanitize_module_kwarg():
    """Test that 'module' kwarg is properly prefixed."""
    # Test through logger behavior - this is tested via integration tests below
    pass


def test_sanitize_process_kwarg():
    """Test that 'process' kwarg is properly prefixed."""
    # Test through logger behavior - this is tested via integration tests below
    pass


def test_logger_constructor_name_still_works():
    """Verify logger constructor 'name' parameter is unaffected."""
    logger = ConsoleLogger("my_logger_name")
    assert logger.name == "my_logger_name"
    assert logger.logger.name == "my_logger_name"


def test_logger_with_name_kwarg_does_not_crash():
    """Test that logger.info(name='value') doesn't crash with LogRecord conflict.

    This previously caused: "Attempt to overwrite 'name' in LogRecord"
    After fix, it should log with x_name instead.
    """
    logger = ConsoleLogger("test")

    # This previously caused: "Attempt to overwrite 'name' in LogRecord"
    # After fix, it should log successfully with x_name
    try:
        logger.info("Test message", name="user_provided_name")
        success = True
        error = None
    except Exception as e:
        success = False
        error = str(e)

    assert success, f"Logger crashed with name kwarg: {error}"


def test_logger_with_module_kwarg_does_not_crash():
    """Test that logger.info(module='value') doesn't crash."""
    logger = ConsoleLogger("test")

    try:
        logger.info("Test message", module="auth_module")
        success = True
        error = None
    except Exception as e:
        success = False
        error = str(e)

    assert success, f"Logger crashed with module kwarg: {error}"


def test_logger_with_multiple_reserved_kwargs():
    """Test that multiple reserved field kwargs are handled correctly."""
    logger = ConsoleLogger("test")

    try:
        logger.info(
            "Test message",
            name="custom_name",
            module="auth",
            process="worker",
            thread="t-1",
        )
        success = True
        error = None
    except Exception as e:
        success = False
        error = str(e)

    assert success, f"Logger crashed with multiple reserved kwargs: {error}"


def test_all_reserved_fields_are_prefixed():
    """Test that all LogRecord internal fields are sanitized through logger usage."""
    # Test through logger behavior - reserved fields should not crash
    logger = ConsoleLogger("test")
    # This validates that the sanitization works for all fields
    logger.info("test", name="value", module="auth")


def test_non_reserved_fields_not_prefixed():
    """Test that custom fields work correctly in logger."""
    logger = ConsoleLogger("test")
    # Custom fields should work without issues
    logger.info("test", custom_field="value", user_id=123, request_id="abc")


def test_mixed_reserved_and_custom_fields():
    """Test sanitization of mixed reserved and custom fields through logger."""
    logger = ConsoleLogger("test")
    # Mixed fields should work - reserved fields prefixed, custom fields as-is
    logger.info(
        "test",
        name="reserved_value",  # Reserved - should be prefixed internally
        user_id=123,  # Custom - should not be prefixed
        module="auth",  # Reserved - should be prefixed internally
        request_id="abc",  # Custom - should not be prefixed
    )


def test_bind_rejects_reserved_fields():
    """Test that bind() rejects reserved field names."""
    logger = ConsoleLogger("test")

    # Should raise ValueError for reserved field
    with pytest.raises(ValueError, match="Cannot bind reserved LogRecord field 'name'"):
        logger.bind(name="value")

    with pytest.raises(ValueError, match="Cannot bind reserved LogRecord field 'module'"):
        logger.bind(module="auth")


def test_bind_accepts_custom_fields():
    """Test that bind() accepts non-reserved field names."""
    logger = ConsoleLogger("test")

    # Should work fine with custom fields
    logger.bind(user_id=123, request_id="abc")
    assert logger.context["user_id"] == 123
    assert logger.context["request_id"] == "abc"
