"""
Tests for v0.4.0 features: thread-safety, lazy evaluation, robust JSON, etc.
"""

import io
import json
import logging
import threading
import time
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from uuid import uuid4

from ff_logger import ConsoleLogger, JSONLogger, ScopedLogger


# Test 1: Thread-safe bind()
def test_bind_thread_safety():
    """Test that bind() is thread-safe with concurrent updates."""
    logger = ScopedLogger(name="test.thread_safe", level=logging.INFO)
    results = []

    def bind_worker(worker_id):
        for i in range(10):
            logger.bind(**{f"worker_{worker_id}_key_{i}": f"value_{i}"})
            time.sleep(0.001)  # Small delay to encourage race conditions
        results.append(worker_id)

    threads = [threading.Thread(target=bind_worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All workers should complete without errors
    assert len(results) == 5
    # Context should have all worker fields (5 workers * 10 keys each)
    assert len(logger.context) == 50


# Test 2: context() context manager
def test_context_manager_temporary_fields():
    """Test that temp_context() adds temporary fields and restores state."""
    logger = ScopedLogger(name="test.context_mgr", context={"permanent": "value"})

    # Initial state
    assert logger.context == {"permanent": "value"}

    # Add temporary context
    with logger.temp_context(temp_field="temp_value", request_id="123"):
        # Inside context, both fields present
        assert logger.context == {
            "permanent": "value",
            "temp_field": "temp_value",
            "request_id": "123",
        }

    # After context, temp fields removed
    assert logger.context == {"permanent": "value"}


def test_context_manager_restores_overridden_values():
    """Test that temp_context() properly restores overridden values."""
    logger = ScopedLogger(name="test.restore", context={"field": "original"})

    with logger.temp_context(field="override", new_field="new"):
        assert logger.context["field"] == "override"
        assert logger.context["new_field"] == "new"

    # Original value restored, new field removed
    assert logger.context == {"field": "original"}


# Test 3: Lazy evaluation with level guard
def test_lazy_evaluation_with_level_guard():
    """Test that callables are not evaluated when level is disabled."""
    stream = io.StringIO()
    logger = ConsoleLogger(name="test.lazy", level="ERROR", stream=stream)

    call_count = 0

    def expensive_computation():
        nonlocal call_count
        call_count += 1
        return "expensive_value"

    # Log at DEBUG level (disabled) - should NOT call the function
    logger.debug("Debug message", expensive_field=expensive_computation)
    assert call_count == 0

    # Log at ERROR level (enabled) - SHOULD call the function
    logger.error("Error message", expensive_field=expensive_computation)
    assert call_count == 1


def test_lazy_evaluation_resolves_callables():
    """Test that callables are resolved before logging."""
    stream = io.StringIO()
    logger = ConsoleLogger(name="test.resolve", level="INFO", stream=stream)

    logger.info("Message", lazy_value=lambda: "computed_value", static_value="static")

    output = stream.getvalue()
    assert "lazy_value" in output
    assert "computed_value" in output
    assert "static_value" in output


# Test 4: Robust JSON serialization
class Color(Enum):
    RED = "red"
    BLUE = "blue"


def test_json_serialization_handles_datetime():
    """Test JSON logger serializes datetime correctly."""
    stream = io.StringIO()
    logger = JSONLogger(name="test.json_datetime", level="INFO", stream=stream)

    now = datetime.now()
    logger.info("Datetime test", timestamp=now)

    output = stream.getvalue()
    data = json.loads(output)
    assert "timestamp" in data
    assert isinstance(data["timestamp"], str)  # Should be ISO format


def test_json_serialization_handles_uuid():
    """Test JSON logger serializes UUID correctly."""
    stream = io.StringIO()
    logger = JSONLogger(name="test.json_uuid", level="INFO", stream=stream)

    test_uuid = uuid4()
    logger.info("UUID test", user_id=test_uuid)

    output = stream.getvalue()
    data = json.loads(output)
    assert "user_id" in data
    assert data["user_id"] == str(test_uuid)


def test_json_serialization_handles_decimal():
    """Test JSON logger serializes Decimal correctly."""
    stream = io.StringIO()
    logger = JSONLogger(name="test.json_decimal", level="INFO", stream=stream)

    price = Decimal("19.99")
    logger.info("Decimal test", price=price)

    output = stream.getvalue()
    data = json.loads(output)
    assert "price" in data
    assert isinstance(data["price"], float)
    assert abs(data["price"] - 19.99) < 0.01


def test_json_serialization_handles_path():
    """Test JSON logger serializes Path correctly."""
    stream = io.StringIO()
    logger = JSONLogger(name="test.json_path", level="INFO", stream=stream)

    path = Path("/tmp/test.txt")
    logger.info("Path test", file_path=path)

    output = stream.getvalue()
    data = json.loads(output)
    assert "file_path" in data
    assert data["file_path"] == "/tmp/test.txt"


def test_json_serialization_handles_enum():
    """Test JSON logger serializes Enum correctly."""
    stream = io.StringIO()
    logger = JSONLogger(name="test.json_enum", level="INFO", stream=stream)

    logger.info("Enum test", color=Color.RED)

    output = stream.getvalue()
    data = json.loads(output)
    assert "color" in data
    assert data["color"] == "red"


def test_json_serialization_never_crashes():
    """Test JSON logger falls back gracefully for un-serializable objects."""
    stream = io.StringIO()
    logger = JSONLogger(name="test.json_safe", level="INFO", stream=stream)

    class WeirdObject:
        def __repr__(self):
            return "<WeirdObject>"

    # Should not crash
    logger.info("Safe test", weird_obj=WeirdObject())

    output = stream.getvalue()
    data = json.loads(output)
    assert "weird_obj" in data
    # Should either be stringified or in the repr


# Test 5: Reserved key sanitization
def test_reserved_key_sanitization():
    """Test that reserved LogRecord fields are prefixed with x_ and still appear."""
    stream = io.StringIO()
    logger = ConsoleLogger(name="test.reserved", level="INFO", stream=stream)

    # Use reserved keys as context (v0.4.1: all LogRecord internals are reserved)
    # 'name' is the most critical one as it causes "Attempt to overwrite 'name' in LogRecord"
    logger.info("Test message", name="custom_name", module="custom_module")

    output = stream.getvalue()
    # The original LogRecord fields should be unaffected
    assert "INFO" in output
    assert "test.reserved" in output  # Original logger name
    # Custom fields should be prefixed to avoid conflicts
    assert "x_name" in output
    assert "x_module" in output


# Test 6: Nested context managers
def test_nested_context_managers():
    """Test that nested temp_context() calls work correctly."""
    logger = ScopedLogger(name="test.nested", context={"base": "value"})

    with logger.temp_context(level1="a"):
        assert logger.context == {"base": "value", "level1": "a"}

        with logger.temp_context(level2="b"):
            assert logger.context == {"base": "value", "level1": "a", "level2": "b"}

        # Inner context exited
        assert logger.context == {"base": "value", "level1": "a"}

    # All contexts exited
    assert logger.context == {"base": "value"}


# Test 7: temp_context() with bind() interaction
def test_context_and_bind_interaction():
    """Test that temp_context() and bind() work together correctly."""
    logger = ScopedLogger(name="test.interaction")

    logger.bind(permanent="value")
    assert logger.context == {"permanent": "value"}

    with logger.temp_context(temporary="temp"):
        # Both permanent and temporary present
        assert logger.context == {"permanent": "value", "temporary": "temp"}

        # bind() inside context adds permanently
        logger.bind(another_permanent="another")
        assert logger.context == {
            "permanent": "value",
            "temporary": "temp",
            "another_permanent": "another",
        }

    # Temporary removed, both permanents remain
    assert logger.context == {"permanent": "value", "another_permanent": "another"}


# Test 8: Level guard performance
def test_level_guard_prevents_work():
    """Test that level guard prevents unnecessary work."""
    stream = io.StringIO()
    logger = ConsoleLogger(name="test.guard", level="WARNING", stream=stream)

    work_done = []

    def track_work():
        work_done.append(1)
        return "value"

    # DEBUG and INFO should be skipped (guard prevents work)
    logger.debug("Debug", field=track_work)
    logger.info("Info", field=track_work)
    assert len(work_done) == 0  # No work done

    # WARNING should execute (guard allows)
    logger.warning("Warning", field=track_work)
    assert len(work_done) == 1  # Work done once
