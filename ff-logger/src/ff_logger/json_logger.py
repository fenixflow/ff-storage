"""
JSON logger implementation for structured logging.
"""

import json
import logging
import socket
import sys
from datetime import datetime, timezone
from typing import Any

from .base import ScopedLogger
from .utils import extract_extra_fields


class JSONFormatter(logging.Formatter):
    """
    JSON formatter that outputs log records as JSON lines.
    Each log entry is a single line of JSON for easy parsing.
    """

    def __init__(self, show_hostname: bool = False, include_timestamp: bool = True):
        """
        Initialize the JSON formatter.

        Args:
            show_hostname: Whether to include hostname in output
            include_timestamp: Whether to include timestamp
        """
        super().__init__()
        self.show_hostname = show_hostname
        self.include_timestamp = include_timestamp
        self.hostname = socket.gethostname() if show_hostname else None

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record as JSON.

        Args:
            record: The LogRecord to format

        Returns:
            JSON string (single line)
        """
        # Build the base log entry
        log_entry = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add timestamp if requested
        if self.include_timestamp:
            # Use ISO format with timezone
            dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
            log_entry["timestamp"] = dt.isoformat()

        # Add hostname if requested
        if self.hostname:
            log_entry["hostname"] = self.hostname

        # Add source location
        log_entry["source"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add process and thread info
        log_entry["process"] = {
            "pid": record.process,
            "name": record.processName,
        }
        log_entry["thread"] = {
            "id": record.thread,
            "name": record.threadName,
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Extract and add all extra fields (context + kwargs)
        extra_fields = extract_extra_fields(record)
        if extra_fields:
            # Add extra fields directly to the log entry at the top level
            # This makes them easier to query in log aggregation systems
            for key, value in extra_fields.items():
                # Avoid overwriting standard fields
                if key not in log_entry:
                    log_entry[key] = value

        # Return as compact JSON (no extra whitespace)
        return json.dumps(log_entry, ensure_ascii=False, separators=(",", ":"))


class JSONLogger(ScopedLogger):
    """
    A scoped logger that outputs structured JSON lines.
    Perfect for log aggregation systems like ELK, Datadog, etc.
    """

    def __init__(
        self,
        name: str,
        level: int = logging.DEBUG,
        context: dict[str, Any] | None = None,
        stream=None,
        show_hostname: bool = False,
        include_timestamp: bool = True,
    ):
        """
        Initialize the JSON logger.

        Args:
            name: Logger name
            level: Logging level
            context: Permanent context fields
            stream: Output stream (default: sys.stdout)
            show_hostname: Whether to include hostname
            include_timestamp: Whether to include timestamp
        """
        super().__init__(name, level, context)

        # Set up the stream handler
        stream = stream or sys.stdout
        handler = logging.StreamHandler(stream)
        handler.setLevel(level)

        # Set up the JSON formatter
        formatter = JSONFormatter(show_hostname=show_hostname, include_timestamp=include_timestamp)
        handler.setFormatter(formatter)

        # Add handler to logger
        self.logger.addHandler(handler)

        # Store configuration for bind()
        self.stream = stream
        self.show_hostname = show_hostname
        self.include_timestamp = include_timestamp

    def bind(self, **kwargs) -> "JSONLogger":
        """
        Create a new logger instance with additional context.

        Args:
            **kwargs: Additional context fields to bind

        Returns:
            A new JSONLogger instance with merged context
        """
        new_context = {**self.context, **kwargs}

        # Create new instance with same configuration
        new_logger = JSONLogger(
            name=f"{self.name}.bound",
            level=self.level,
            context=new_context,
            stream=self.stream,
            show_hostname=self.show_hostname,
            include_timestamp=self.include_timestamp,
        )

        return new_logger
