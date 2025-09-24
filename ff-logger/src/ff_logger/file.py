"""
File logger with rotation support for ff-logger.
"""

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Any

from .base import ScopedLogger
from .utils import extract_extra_fields


class FileFormatter(logging.Formatter):
    """
    Formatter for file-based logging with structured output.
    """

    def __init__(self, include_extra: bool = True):
        """
        Initialize the file formatter.

        Args:
            include_extra: Whether to include extra fields in output
        """
        self.include_extra = include_extra

        # Use a detailed format for file logs
        super().__init__(
            fmt="[%(asctime)s] %(levelname)-8s [%(name)s] %(filename)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record for file output.

        Args:
            record: The LogRecord to format

        Returns:
            Formatted log string
        """
        # Get the base formatted message
        result = super().format(record)

        # Add extra fields if requested
        if self.include_extra:
            extra_data = extract_extra_fields(record)
            if extra_data:
                # Format extra fields as key=value pairs
                extra_parts = []
                for key, value in extra_data.items():
                    if isinstance(value, str):
                        formatted_value = f'"{value}"'
                    elif isinstance(value, bool):
                        formatted_value = str(value).lower()
                    elif value is None:
                        formatted_value = "null"
                    else:
                        formatted_value = str(value)
                    extra_parts.append(f"{key}={formatted_value}")

                if extra_parts:
                    result = f"{result} | {' '.join(extra_parts)}"

        return result


class FileLogger(ScopedLogger):
    """
    A scoped logger that writes to files with optional rotation.
    Supports size-based and time-based rotation.
    """

    def __init__(
        self,
        name: str,
        filename: str,
        level: int | str = "DEBUG",
        context: dict[str, Any] | None = None,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB default
        backup_count: int = 5,
        rotation_type: str = "size",  # "size", "time", or "none"
        when: str = "midnight",  # For time-based rotation
        interval: int = 1,  # For time-based rotation
        include_extra: bool = True,
        ensure_dir: bool = True,
    ):
        """
        Initialize the file logger.

        Args:
            name: Logger name
            filename: Path to the log file
            level: Logging level as int or string (default: "DEBUG")
            context: Permanent context fields
            max_bytes: Maximum file size before rotation (for size-based)
            backup_count: Number of backup files to keep
            rotation_type: Type of rotation ("size", "time", or "none")
            when: When to rotate for time-based ('midnight', 'W0'-'W6', etc.)
            interval: Interval for time-based rotation
            include_extra: Whether to include extra fields in output
            ensure_dir: Whether to create the directory if it doesn't exist
        """
        super().__init__(name, level, context)

        # Ensure directory exists if requested
        if ensure_dir:
            log_dir = os.path.dirname(filename)
            if log_dir:
                Path(log_dir).mkdir(parents=True, exist_ok=True)

        # Create the appropriate handler based on rotation type
        if rotation_type == "size":
            # Size-based rotation
            handler = logging.handlers.RotatingFileHandler(
                filename=filename, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
            )
        elif rotation_type == "time":
            # Time-based rotation
            handler = logging.handlers.TimedRotatingFileHandler(
                filename=filename,
                when=when,
                interval=interval,
                backupCount=backup_count,
                encoding="utf-8",
            )
        else:
            # No rotation - simple file handler
            handler = logging.FileHandler(filename=filename, encoding="utf-8")

        # No need to set handler level - inherits from logger

        # Set up the formatter
        formatter = FileFormatter(include_extra=include_extra)
        handler.setFormatter(formatter)

        # Add handler to logger
        self.logger.addHandler(handler)

        # Store configuration for local use
        self.filename = filename
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.rotation_type = rotation_type
        self.when = when
        self.interval = interval
        self.include_extra = include_extra
        self.ensure_dir = ensure_dir

    # bind() method inherited from ScopedLogger base class

    def get_current_log_file(self) -> str:
        """
        Get the path to the current log file.

        Returns:
            Path to the current log file
        """
        return self.filename

    def rotate(self) -> None:
        """
        Force a rotation of the log file (if using rotation).
        """
        for handler in self.logger.handlers:
            if isinstance(
                handler,
                logging.handlers.RotatingFileHandler | logging.handlers.TimedRotatingFileHandler,
            ):
                handler.doRollover()
