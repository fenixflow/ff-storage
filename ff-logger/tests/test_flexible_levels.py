"""
Tests for flexible log level input (int and string).
"""

import io
import logging

from ff_logger import ConsoleLogger, FileLogger, JSONLogger, NullLogger
from ff_logger.utils import normalize_level


class TestLevelNormalization:
    """Test the normalize_level utility function."""

    def test_normalize_int_levels(self):
        """Test that integer levels pass through unchanged."""
        assert normalize_level(logging.DEBUG) == logging.DEBUG
        assert normalize_level(logging.INFO) == logging.INFO
        assert normalize_level(logging.WARNING) == logging.WARNING
        assert normalize_level(logging.ERROR) == logging.ERROR
        assert normalize_level(logging.CRITICAL) == logging.CRITICAL
        assert normalize_level(10) == 10
        assert normalize_level(20) == 20
        assert normalize_level(30) == 30

    def test_normalize_string_levels(self):
        """Test that string levels are converted to integers."""
        assert normalize_level("DEBUG") == logging.DEBUG
        assert normalize_level("INFO") == logging.INFO
        assert normalize_level("WARNING") == logging.WARNING
        assert normalize_level("WARN") == logging.WARNING  # Common alias
        assert normalize_level("ERROR") == logging.ERROR
        assert normalize_level("CRITICAL") == logging.CRITICAL

    def test_normalize_case_insensitive(self):
        """Test that string levels are case-insensitive."""
        assert normalize_level("debug") == logging.DEBUG
        assert normalize_level("Info") == logging.INFO
        assert normalize_level("warning") == logging.WARNING
        assert normalize_level("ErRoR") == logging.ERROR
        assert normalize_level("CRITICAL") == logging.CRITICAL

    def test_normalize_invalid_string(self):
        """Test that invalid strings default to INFO."""
        assert normalize_level("INVALID") == logging.INFO
        assert normalize_level("notlevel") == logging.INFO
        assert normalize_level("") == logging.INFO


class TestConsoleLoggerFlexibleLevels:
    """Test ConsoleLogger with flexible level input."""

    def test_console_logger_int_level(self):
        """Test ConsoleLogger with integer level (backward compatibility)."""
        stream = io.StringIO()
        logger = ConsoleLogger(name="test.int", level=logging.WARNING, stream=stream, colors=False)

        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")

        output = stream.getvalue()
        assert "Debug message" not in output  # Below WARNING level
        assert "Info message" not in output  # Below WARNING level
        assert "Warning message" in output

    def test_console_logger_string_level(self):
        """Test ConsoleLogger with string level."""
        stream = io.StringIO()
        logger = ConsoleLogger(name="test.string", level="WARNING", stream=stream, colors=False)

        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")

        output = stream.getvalue()
        assert "Debug message" not in output  # Below WARNING level
        assert "Info message" not in output  # Below WARNING level
        assert "Warning message" in output

    def test_console_logger_case_insensitive(self):
        """Test ConsoleLogger with case-insensitive string level."""
        stream = io.StringIO()
        logger = ConsoleLogger(name="test.case", level="info", stream=stream, colors=False)

        logger.debug("Debug message")
        logger.info("Info message")

        output = stream.getvalue()
        assert "Debug message" not in output  # Below INFO level
        assert "Info message" in output

    def test_console_logger_default_level(self):
        """Test ConsoleLogger with default level."""
        stream = io.StringIO()
        logger = ConsoleLogger(name="test.default", stream=stream, colors=False)

        logger.debug("Debug message")
        output = stream.getvalue()
        assert "Debug message" in output  # Default is DEBUG


class TestJSONLoggerFlexibleLevels:
    """Test JSONLogger with flexible level input."""

    def test_json_logger_int_level(self):
        """Test JSONLogger with integer level."""
        stream = io.StringIO()
        logger = JSONLogger(
            name="test.json.int",
            level=20,
            stream=stream,
            include_timestamp=False,  # INFO
        )

        logger.debug("Debug message")
        logger.info("Info message")

        output = stream.getvalue()
        assert "Debug message" not in output
        assert "Info message" in output

    def test_json_logger_string_level(self):
        """Test JSONLogger with string level."""
        stream = io.StringIO()
        logger = JSONLogger(
            name="test.json.string", level="ERROR", stream=stream, include_timestamp=False
        )

        logger.warning("Warning message")
        logger.error("Error message")

        output = stream.getvalue()
        assert "Warning message" not in output
        assert "Error message" in output


class TestFileLoggerFlexibleLevels:
    """Test FileLogger with flexible level input."""

    def test_file_logger_string_level(self, tmp_path):
        """Test FileLogger with string level."""
        log_file = tmp_path / "test.log"
        logger = FileLogger(
            name="test.file", filename=str(log_file), level="WARNING", rotation_type="none"
        )

        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")

        content = log_file.read_text()
        assert "Debug message" not in content
        assert "Info message" not in content
        assert "Warning message" in content


class TestNullLoggerFlexibleLevels:
    """Test NullLogger with flexible level input."""

    def test_null_logger_accepts_any_level(self):
        """Test that NullLogger accepts any level type without error."""
        # Should not raise any errors
        logger1 = NullLogger(level=logging.DEBUG)
        logger2 = NullLogger(level="INFO")
        logger3 = NullLogger(level="warning")
        logger4 = NullLogger(level=None)
        logger5 = NullLogger()

        # All should work without error (they're no-ops)
        logger1.info("test")
        logger2.info("test")
        logger3.info("test")
        logger4.info("test")
        logger5.info("test")


class TestBackwardCompatibility:
    """Ensure complete backward compatibility with existing code."""

    def test_all_loggers_accept_int_levels(self):
        """Test that all loggers still accept integer levels."""
        stream = io.StringIO()

        # These should all work exactly as before
        console = ConsoleLogger("test", level=logging.INFO, stream=stream)
        json_logger = JSONLogger("test", level=logging.WARNING, stream=stream)
        NullLogger(level=logging.ERROR)  # Still accepts it

        # Verify they're using the correct levels
        assert console.level == logging.INFO
        assert json_logger.level == logging.WARNING
        # NullLogger doesn't store level but should accept it

    def test_bind_preserves_level(self):
        """Test that bind() preserves the normalized level."""
        stream = io.StringIO()
        logger = ConsoleLogger(name="test", level="INFO", stream=stream, colors=False)

        logger.bind(request_id="123")
        assert logger.level == logging.INFO

        # Test that logger respects the level with bound context
        logger.debug("Debug message")
        logger.info("Info message")

        output = stream.getvalue()
        assert "Debug message" not in output
        assert "Info message" in output
        assert 'request_id="123"' in output
