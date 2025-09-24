"""
Console logger with colored output for ff-logger.
"""

import logging
import socket
import sys
from logging import Formatter
from typing import Any

from .base import ScopedLogger
from .utils import extract_extra_fields


class ColoredFormatter(Formatter):
    """
    Colored formatter for console output.
    Adds colors to log levels and formats extra fields nicely.
    """

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[94m",  # Blue
        "INFO": "\033[92m",  # Green
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "CRITICAL": "\033[91m\033[1m",  # Bold Red
        "RESET": "\033[0m",  # Reset
    }

    def __init__(self, colors: bool = True, show_hostname: bool = False):
        """
        Initialize the colored formatter.

        Args:
            colors: Whether to use colors (default: True)
            show_hostname: Whether to include hostname (default: False)
        """
        self.colors = colors
        self.hostname = socket.gethostname() if show_hostname else None

        # Build format string
        fmt_parts = ["[%(asctime)s]"]
        if self.hostname:
            fmt_parts.append(f"{self.hostname}")
        fmt_parts.append("%(levelname)s")
        fmt_parts.append("[%(name)s]")
        fmt_parts.append("%(message)s")

        super().__init__(fmt=" ".join(fmt_parts), datefmt="%Y-%m-%d %H:%M:%S")

    def format(self, record):
        """
        Format the log record with colors and extra fields.

        Args:
            record: The LogRecord to format

        Returns:
            Formatted log string
        """
        # Apply colors to level name if enabled
        if self.colors and record.levelname in self.COLORS:
            original_levelname = record.levelname
            record.levelname = (
                f"{self.COLORS[record.levelname]}{record.levelname}{self.COLORS['RESET']}"
            )
            result = super().format(record)
            record.levelname = original_levelname  # Restore original
        else:
            result = super().format(record)

        # Extract and format extra fields
        extra_data = extract_extra_fields(record)

        # Add file:line information
        if hasattr(record, "filename") and hasattr(record, "lineno"):
            extra_data["line"] = f"{record.filename}:{record.lineno}"

        # Format extra fields if present
        if extra_data:
            # Format as key=value pairs on the same line
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

                if self.colors:
                    # Color the key in cyan
                    extra_parts.append(f"\033[36m{key}\033[0m={formatted_value}")
                else:
                    extra_parts.append(f"{key}={formatted_value}")

            if extra_parts:
                result = f"{result} | {' '.join(extra_parts)}"

        return result


class ConsoleLogger(ScopedLogger):
    """
    A scoped logger that outputs to console with optional colored formatting.
    Supports context binding and arbitrary kwargs.
    """

    def __init__(
        self,
        name: str,
        level: int | str = "DEBUG",
        context: dict[str, Any] | None = None,
        colors: bool = True,
        stream=None,
        show_hostname: bool = False,
    ):
        """
        Initialize the console logger.

        Args:
            name: Logger name
            level: Logging level as int or string (default: "DEBUG")
            context: Permanent context fields
            colors: Whether to use colored output (default: True)
            stream: Output stream (default: sys.stdout)
            show_hostname: Whether to include hostname in logs (default: False)
        """
        super().__init__(name, level, context)

        # Set up the stream handler
        stream = stream or sys.stdout
        handler = logging.StreamHandler(stream)
        # No need to set handler level - inherits from logger

        # Set up the colored formatter
        formatter = ColoredFormatter(colors=colors, show_hostname=show_hostname)
        handler.setFormatter(formatter)

        # Add handler to logger
        self.logger.addHandler(handler)

        # Store configuration for local use
        self.colors = colors
        self.stream = stream
        self.show_hostname = show_hostname

    # bind() method inherited from ScopedLogger base class
