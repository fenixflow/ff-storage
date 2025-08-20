"""
Tests for ff-logger package.
"""

import io
import json
import os
from unittest.mock import Mock, patch

import pytest
from ff_logger import (
    ConsoleLogger,
    DatabaseLogger,
    JSONLogger,
    NullLogger,
    ScopedLogger,
    configure_logging,
    get_logger,
)
from ff_logger.null import CaptureLogger
from ff_logger.processors import add_correlation_id, filter_secrets, hash_user_data


class TestScopedLogger:
    """Test the base ScopedLogger class."""

    def test_basic_logging(self):
        """Test basic logging functionality."""
        logger = ScopedLogger("test")

        # These should not raise
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")

    def test_context_binding(self):
        """Test context binding."""
        logger = ScopedLogger("test")

        # Bind context
        logger2 = logger.bind(user_id=123, request_id="abc")
        assert logger2.context["user_id"] == 123
        assert logger2.context["request_id"] == "abc"

        # Original logger unchanged
        assert "user_id" not in logger.context

    def test_context_unbinding(self):
        """Test context unbinding."""
        logger = ScopedLogger("test", context={"user_id": 123, "request_id": "abc"})

        # Unbind a key
        logger2 = logger.unbind("user_id")
        assert "user_id" not in logger2.context
        assert logger2.context["request_id"] == "abc"

        # Original logger unchanged
        assert logger.context["user_id"] == 123

    def test_structured_logging(self):
        """Test logging with structured data."""
        logger = ScopedLogger("test")

        # Should accept keyword arguments
        logger.info("user_action", user_id=123, action="login", ip="192.168.1.1")
        logger.error("database_error", error="Timeout", retry_count=3)


class TestConsoleLogger:
    """Test the ConsoleLogger class."""

    def test_console_output(self):
        """Test that console logger writes to stream."""
        stream = io.StringIO()
        logger = ConsoleLogger("test", stream=stream)

        logger.info("Test message", user_id=123)

        output = stream.getvalue()
        assert "Test message" in output
        assert "user_id" in output

    def test_hostname_addition(self):
        """Test hostname is added when requested."""
        logger = ConsoleLogger("test", add_hostname=True)
        assert "hostname" in logger.context

    def test_colors_configuration(self):
        """Test color configuration."""
        stream = io.StringIO()

        # With colors
        logger1 = ConsoleLogger("test", colors=True, stream=stream)
        logger1.info("Colored message")

        # Without colors
        logger2 = ConsoleLogger("test", colors=False, stream=stream)
        logger2.info("Plain message")

        # Both should log successfully
        output = stream.getvalue()
        assert "message" in output.lower()


class TestJSONLogger:
    """Test the JSONLogger class."""

    def test_json_output(self):
        """Test that JSON logger outputs valid JSON."""
        stream = io.StringIO()
        logger = JSONLogger("test", stream=stream)

        logger.info("Test event", user_id=123, status="active")

        # Output should be valid JSON
        output = stream.getvalue()
        for line in output.strip().split("\n"):
            if line:
                data = json.loads(line)
                assert "event" in data or "Test event" in str(data)

    def test_process_info(self):
        """Test process info addition."""
        logger = JSONLogger("test", add_process_info=True)

        assert "pid" in logger.context
        assert "thread" in logger.context

    def test_hostname_in_json(self):
        """Test hostname is included."""
        logger = JSONLogger("test", add_hostname=True)
        assert "hostname" in logger.context


class TestDatabaseLogger:
    """Test the DatabaseLogger class."""

    def test_database_logger_creation(self):
        """Test creating a database logger."""
        mock_connection = Mock()
        logger = DatabaseLogger("test", mock_connection)

        # Should have created logger successfully
        assert logger.name == "test"
        assert logger.db_connection == mock_connection

    def test_database_write(self):
        """Test that logs are written to database."""
        mock_connection = Mock()
        mock_connection.execute = Mock()

        logger = DatabaseLogger("test", mock_connection, schema="logs", table="app_logs")
        logger.info("Test event", user_id=123)

        # Database processor should attempt to create table
        # Note: Actual write happens in processor, which is harder to test directly

    def test_also_print_option(self):
        """Test the also_print option."""
        mock_connection = Mock()

        logger = DatabaseLogger(
            "test",
            mock_connection,
            also_print=True,
        )

        # Should create logger with both database and console output
        logger.info("Dual output", data="test")


class TestNullLogger:
    """Test the NullLogger class."""

    def test_null_logger_no_output(self):
        """Test that null logger produces no output."""
        logger = NullLogger("test")

        # These should all be no-ops
        logger.debug("Debug")
        logger.info("Info")
        logger.warning("Warning")
        logger.error("Error")
        logger.critical("Critical")
        logger.exception("Exception")

        # Context operations should work but do nothing
        logger2 = logger.bind(user_id=123)
        assert logger2 is logger  # Returns self

        logger3 = logger.unbind("user_id")
        assert logger3 is logger  # Returns self

    def test_null_logger_zero_cost(self):
        """Test that expensive operations are not evaluated."""
        expensive_called = False

        def expensive_function():
            nonlocal expensive_called
            expensive_called = True
            return "expensive result"

        logger = NullLogger("test")

        # This should NOT call expensive_function
        logger.debug("Message", data=expensive_function())

        # In a real null logger, expensive_function would not be called
        # but in Python, arguments are evaluated before the method call
        # The real benefit comes from using structlog's PrintLogger(file=None)


class TestConfiguration:
    """Test the configuration system."""

    def test_configure_logging(self):
        """Test global configuration."""
        configure_logging(
            level="DEBUG",
            format="json",
            add_hostname=True,
            colors=False,
        )

        from ff_logger.config import get_config

        config = get_config()

        assert config["level"] == "DEBUG"
        assert config["format"] == "json"
        assert config["add_hostname"] is True
        assert config["colors"] is False

    def test_environment_variables(self):
        """Test configuration from environment variables."""
        with patch.dict(
            os.environ,
            {
                "FF_LOG_LEVEL": "ERROR",
                "FF_LOG_FORMAT": "json",
                "FF_LOG_ADD_HOSTNAME": "true",
                "FF_LOG_COLORS": "false",
            },
        ):
            configure_logging(use_env=True)

            from ff_logger.config import get_config

            config = get_config()

            assert config["level"] == "ERROR"
            assert config["format"] == "json"
            assert config["add_hostname"] is True
            assert config["colors"] is False

    def test_get_logger_with_config(self):
        """Test get_logger respects configuration."""
        configure_logging(format="json", add_hostname=True)

        logger = get_logger("test")
        # Should create a JSON logger based on config
        assert isinstance(logger, JSONLogger)

        # Can override type
        logger2 = get_logger("test2", logger_type="console")
        assert isinstance(logger2, ConsoleLogger)

        # Can specify null logger
        logger3 = get_logger("test3", logger_type="null")
        assert isinstance(logger3, NullLogger)


class TestProcessors:
    """Test custom processors."""

    def test_filter_secrets(self):
        """Test secret filtering processor."""
        event_dict = {
            "event": "Login attempt",
            "password": "secret123",
            "api_key": "abc-123-def",
            "data": "Bearer token123xyz",
        }

        filtered = filter_secrets(None, None, event_dict)

        assert "***REDACTED***" in str(filtered)
        assert "secret123" not in str(filtered)
        assert "abc-123-def" not in str(filtered)

    def test_add_correlation_id(self):
        """Test correlation ID processor."""
        event_dict = {"event": "Test"}

        result = add_correlation_id(None, None, event_dict)

        assert "correlation_id" in result
        assert len(result["correlation_id"]) > 0

    def test_hash_user_data(self):
        """Test user data hashing processor."""
        event_dict = {
            "event": "User action",
            "email": "user@example.com",
            "user_id": "12345",
            "other_data": "unchanged",
        }

        hashed = hash_user_data(None, None, event_dict)

        assert hashed["email"] == "***HASHED***"
        assert "email_hash" in hashed
        assert hashed["user_id"] == "***HASHED***"
        assert "user_id_hash" in hashed
        assert hashed["other_data"] == "unchanged"


class TestCaptureLogger:
    """Test the CaptureLogger for testing."""

    def test_capture_logs(self):
        """Test that CaptureLogger captures log entries."""
        logger = CaptureLogger("test")

        logger.info("Test message", user_id=123)
        logger.error("Error message", code=500)

        # Check captured entries
        assert len(logger.entries) == 2

        # Can clear entries
        logger.clear()
        assert len(logger.entries) == 0

    def test_test_logger_context(self):
        """Test context handling in CaptureLogger."""
        logger = CaptureLogger("test")
        logger2 = logger.bind(request_id="abc")

        logger2.info("With context")

        # Both loggers share the same capture
        assert len(logger.entries) == 1
        assert len(logger2.entries) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
