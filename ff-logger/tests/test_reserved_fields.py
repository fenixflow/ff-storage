"""Test reserved field sanitization, especially 'name' field."""

import pytest
from ff_logger import ConsoleLogger
from ff_logger.utils import LOGGING_INTERNAL_FIELDS, RESERVED_FIELDS, _sanitize_keys


def test_reserved_fields_uses_logging_internals():
    """Verify RESERVED_FIELDS includes all LogRecord attributes."""
    assert RESERVED_FIELDS == frozenset(LOGGING_INTERNAL_FIELDS)


def test_reserved_fields_is_frozenset():
    """Verify RESERVED_FIELDS is a frozenset for immutability and performance."""
    assert isinstance(RESERVED_FIELDS, frozenset)


def test_sanitize_name_kwarg():
    """Test that 'name' kwarg is properly prefixed to avoid LogRecord conflict."""
    result = _sanitize_keys({"name": "user_provided_name"})
    assert result == {"x_name": "user_provided_name"}


def test_sanitize_module_kwarg():
    """Test that 'module' kwarg is properly prefixed."""
    result = _sanitize_keys({"module": "auth"})
    assert result == {"x_module": "auth"}


def test_sanitize_process_kwarg():
    """Test that 'process' kwarg is properly prefixed."""
    result = _sanitize_keys({"process": "worker"})
    assert result == {"x_process": "worker"}


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
    """Test that all LogRecord internal fields are sanitized."""
    # Create a dict with all reserved field names
    test_data = {field: f"value_{field}" for field in LOGGING_INTERNAL_FIELDS}
    result = _sanitize_keys(test_data)

    # All keys should be prefixed
    for key in result:
        assert key.startswith("x_"), f"Field '{key}' was not prefixed"

    # Verify we have the same number of fields
    assert len(result) == len(test_data)


def test_non_reserved_fields_not_prefixed():
    """Test that custom fields are not prefixed."""
    result = _sanitize_keys({"custom_field": "value", "user_id": 123, "request_id": "abc"})

    assert result == {"custom_field": "value", "user_id": 123, "request_id": "abc"}


def test_mixed_reserved_and_custom_fields():
    """Test sanitization of mixed reserved and custom fields."""
    result = _sanitize_keys(
        {
            "name": "reserved_value",  # Reserved - should be prefixed
            "user_id": 123,  # Custom - should not be prefixed
            "module": "auth",  # Reserved - should be prefixed
            "request_id": "abc",  # Custom - should not be prefixed
        }
    )

    assert result == {
        "x_name": "reserved_value",
        "user_id": 123,
        "x_module": "auth",
        "request_id": "abc",
    }


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
