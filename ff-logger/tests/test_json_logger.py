"""
Tests for JSONLogger implementation.
"""

import io
import json
import logging

from ff_logger import JSONLogger


def test_json_logger_outputs_valid_json():
    """Test that JSONLogger outputs valid JSON lines."""
    stream = io.StringIO()
    logger = JSONLogger(
        name="test.json",
        level=logging.INFO,
        stream=stream,
        include_timestamp=False,  # Disable for predictable output
    )

    logger.info("Test message")

    output = stream.getvalue().strip()
    # Should be valid JSON
    data = json.loads(output)

    assert data["message"] == "Test message"
    assert data["level"] == "INFO"
    assert data["logger"] == "test.json"


def test_json_logger_with_context():
    """Test JSONLogger with permanent context fields."""
    stream = io.StringIO()
    logger = JSONLogger(
        name="test.context",
        level=logging.INFO,
        context={"service": "api", "version": "1.0.0"},
        stream=stream,
        include_timestamp=False,
    )

    logger.info("Processing request")

    output = stream.getvalue().strip()
    data = json.loads(output)

    assert data["message"] == "Processing request"
    assert data["service"] == "api"
    assert data["version"] == "1.0.0"


def test_json_logger_with_kwargs():
    """Test JSONLogger with runtime kwargs."""
    stream = io.StringIO()
    logger = JSONLogger(
        name="test.kwargs", level=logging.INFO, stream=stream, include_timestamp=False
    )

    logger.info("Request completed", duration=35, status_code=200, success=True)

    output = stream.getvalue().strip()
    data = json.loads(output)

    assert data["message"] == "Request completed"
    assert data["duration"] == 35
    assert data["status_code"] == 200
    assert data["success"] is True


def test_json_logger_with_timestamp():
    """Test JSONLogger includes timestamp when enabled."""
    stream = io.StringIO()
    logger = JSONLogger(
        name="test.timestamp", level=logging.INFO, stream=stream, include_timestamp=True
    )

    logger.info("Test message")

    output = stream.getvalue().strip()
    data = json.loads(output)

    assert "timestamp" in data
    # Should be ISO format with timezone
    assert "T" in data["timestamp"]  # ISO format separator


def test_json_logger_with_hostname():
    """Test JSONLogger includes hostname when enabled."""
    stream = io.StringIO()
    logger = JSONLogger(
        name="test.hostname",
        level=logging.INFO,
        stream=stream,
        show_hostname=True,
        include_timestamp=False,
    )

    logger.info("Test message")

    output = stream.getvalue().strip()
    data = json.loads(output)

    assert "hostname" in data
    assert len(data["hostname"]) > 0


def test_json_logger_source_info():
    """Test JSONLogger includes source file information."""
    stream = io.StringIO()
    logger = JSONLogger(
        name="test.source", level=logging.INFO, stream=stream, include_timestamp=False
    )

    logger.info("Test message")

    output = stream.getvalue().strip()
    data = json.loads(output)

    assert "source" in data
    assert "file" in data["source"]
    assert "line" in data["source"]
    assert "function" in data["source"]


def test_json_logger_exception():
    """Test JSONLogger includes exception information."""
    stream = io.StringIO()
    logger = JSONLogger(
        name="test.exception", level=logging.INFO, stream=stream, include_timestamp=False
    )

    try:
        raise ValueError("Test error")
    except ValueError:
        logger.exception("An error occurred")

    output = stream.getvalue().strip()
    data = json.loads(output)

    assert data["message"] == "An error occurred"
    assert data["level"] == "ERROR"
    assert "exception" in data
    assert "ValueError: Test error" in data["exception"]


def test_json_logger_multiple_messages():
    """Test JSONLogger outputs one JSON object per line."""
    stream = io.StringIO()
    logger = JSONLogger(
        name="test.multiple", level=logging.INFO, stream=stream, include_timestamp=False
    )

    logger.info("First message")
    logger.info("Second message")
    logger.info("Third message")

    lines = stream.getvalue().strip().split("\n")
    assert len(lines) == 3

    # Each line should be valid JSON
    for line in lines:
        data = json.loads(line)
        assert "message" in data


def test_json_logger_bind():
    """Test bind() creates new logger with merged context."""
    stream = io.StringIO()
    logger = JSONLogger(
        name="test.bind",
        level=logging.INFO,
        context={"service": "api"},
        stream=stream,
        include_timestamp=False,
    )

    request_logger = logger.bind(request_id="abc123")
    request_logger.info("Processing")

    output = stream.getvalue().strip()
    data = json.loads(output)

    assert data["service"] == "api"
    assert data["request_id"] == "abc123"
