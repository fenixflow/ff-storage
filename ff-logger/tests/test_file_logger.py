"""
Tests for FileLogger implementation.
"""

import logging
import os
import tempfile

from ff_logger import FileLogger


def test_file_logger_creates_file():
    """Test that FileLogger creates a log file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = os.path.join(tmpdir, "test.log")

        logger = FileLogger(
            name="test.file", filename=log_file, level=logging.INFO, rotation_type="none"
        )

        logger.info("Test message")

        # File should exist
        assert os.path.exists(log_file)

        # Read and verify content
        with open(log_file) as f:
            content = f.read()

        assert "Test message" in content
        assert "INFO" in content
        assert "test.file" in content


def test_file_logger_with_context():
    """Test FileLogger with permanent context fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = os.path.join(tmpdir, "test_context.log")

        logger = FileLogger(
            name="test.context",
            filename=log_file,
            level=logging.INFO,
            context={"service": "api", "environment": "test"},
            rotation_type="none",
        )

        logger.info("Processing request")

        with open(log_file) as f:
            content = f.read()

        assert "Processing request" in content
        assert 'service="api"' in content
        assert 'environment="test"' in content


def test_file_logger_creates_directory():
    """Test that FileLogger creates directory if it doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = os.path.join(tmpdir, "logs", "app")
        log_file = os.path.join(log_dir, "test.log")

        logger = FileLogger(
            name="test.dir",
            filename=log_file,
            level=logging.INFO,
            ensure_dir=True,
            rotation_type="none",
        )

        logger.info("Test message")

        assert os.path.exists(log_dir)
        assert os.path.exists(log_file)


def test_file_logger_size_rotation():
    """Test FileLogger with size-based rotation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = os.path.join(tmpdir, "test_rotate.log")

        # Small max size to trigger rotation
        logger = FileLogger(
            name="test.rotate",
            filename=log_file,
            level=logging.INFO,
            rotation_type="size",
            max_bytes=100,  # Very small for testing
            backup_count=3,
        )

        # Write enough messages to trigger rotation
        for i in range(20):
            logger.info(f"Message {i} with some extra content to fill space")

        # Should have created backup files
        assert os.path.exists(log_file)
        # At least one backup should exist
        assert os.path.exists(f"{log_file}.1")


def test_file_logger_no_extra_fields():
    """Test FileLogger without extra fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = os.path.join(tmpdir, "test_no_extra.log")

        logger = FileLogger(
            name="test.no_extra",
            filename=log_file,
            level=logging.INFO,
            include_extra=False,
            rotation_type="none",
        )

        logger.info("Simple message", extra_field="should_not_appear")

        with open(log_file) as f:
            content = f.read()

        assert "Simple message" in content
        assert "extra_field" not in content


def test_file_logger_multiple_levels():
    """Test FileLogger with different log levels."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = os.path.join(tmpdir, "test_levels.log")

        logger = FileLogger(
            name="test.levels", filename=log_file, level=logging.DEBUG, rotation_type="none"
        )

        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")

        with open(log_file) as f:
            content = f.read()

        assert "DEBUG" in content and "Debug message" in content
        assert "INFO" in content and "Info message" in content
        assert "WARNING" in content and "Warning message" in content
        assert "ERROR" in content and "Error message" in content
        assert "CRITICAL" in content and "Critical message" in content


def test_file_logger_get_current_log_file():
    """Test get_current_log_file() method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = os.path.join(tmpdir, "test.log")

        logger = FileLogger(
            name="test.current", filename=log_file, level=logging.INFO, rotation_type="none"
        )

        assert logger.get_current_log_file() == log_file


def test_file_logger_bind():
    """Test bind() updates context in place."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = os.path.join(tmpdir, "test_bind.log")

        logger = FileLogger(
            name="test.bind",
            filename=log_file,
            level=logging.INFO,
            context={"service": "api"},
            rotation_type="none",
        )

        # Bind updates context in place
        result = logger.bind(request_id="abc123")

        # Should return self
        assert result is logger
        # Context should be updated
        assert logger.context == {"service": "api", "request_id": "abc123"}
        # Filename should remain the same
        assert logger.get_current_log_file() == log_file
