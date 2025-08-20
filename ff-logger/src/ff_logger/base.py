"""
Base ScopedLogger class for ff-logger.
"""

import logging
from typing import Any


class ScopedLogger:
    """
    Base class for creating a scoped logger with a handler.
    Ensures that each instance has its own independent logger.
    Supports context binding and arbitrary kwargs in log methods.
    """

    def __init__(
        self, name: str, level: int = logging.DEBUG, context: dict[str, Any] | None = None
    ):
        """
        Initialize the scoped logger.

        Args:
            name: A unique name for the logger (e.g., the scope of the logger)
            level: The logging level (default: DEBUG)
            context: Permanent context fields to include in every log message
        """
        self.name = name
        self.level = level
        self.context = context or {}

        # Create a unique logger instance
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        # Clear any pre-existing handlers for this logger to avoid duplicates
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        # Disable propagation to avoid duplicate messages from parent loggers
        self.logger.propagate = False

    def get_logger(self) -> logging.Logger:
        """
        Returns the underlying logger instance.

        Returns:
            The logging.Logger instance
        """
        return self.logger

    def bind(self, **kwargs) -> "ScopedLogger":
        """
        Create a new logger instance with additional context.

        Args:
            **kwargs: Additional context fields to bind

        Returns:
            A new ScopedLogger instance with merged context
        """
        new_context = {**self.context, **kwargs}

        # Create a new instance of the same class
        new_logger = self.__class__(
            name=f"{self.name}.bound", level=self.level, context=new_context
        )

        # Copy handlers from the current logger
        for handler in self.logger.handlers:
            new_logger.logger.addHandler(handler)

        return new_logger

    def _log_with_context(self, level: int, message: str, exc_info: bool = False, **kwargs):
        """
        Internal method to log with context.

        Args:
            level: Logging level
            message: Log message
            exc_info: Whether to include exception information
            **kwargs: Additional context fields for this log entry
        """
        from .utils import RESERVED_FIELDS

        # Merge permanent context with runtime kwargs
        extra = {**self.context, **kwargs}

        # Remove exc_info from extra if present (it's a special parameter)
        extra.pop("exc_info", None)

        # Prefix any reserved fields to avoid conflicts with LogRecord
        safe_extra = {}
        for key, value in extra.items():
            if key in RESERVED_FIELDS:
                safe_extra[f"x_{key}"] = value
            else:
                safe_extra[key] = value

        # Use stacklevel=3 to get the correct line number from calling code
        # Stack: calling_code -> logger.info() -> _log_with_context() -> logger.log()
        self.logger.log(level, message, extra=safe_extra, exc_info=exc_info, stacklevel=3)

    def debug(self, message: str, **kwargs):
        """
        Log a debug message.

        Args:
            message: The log message
            **kwargs: Additional context fields
        """
        self._log_with_context(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """
        Log an info message.

        Args:
            message: The log message
            **kwargs: Additional context fields
        """
        self._log_with_context(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """
        Log a warning message.

        Args:
            message: The log message
            **kwargs: Additional context fields
        """
        self._log_with_context(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        """
        Log an error message.

        Args:
            message: The log message
            **kwargs: Additional context fields
        """
        self._log_with_context(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        """
        Log a critical message.

        Args:
            message: The log message
            **kwargs: Additional context fields
        """
        self._log_with_context(logging.CRITICAL, message, **kwargs)

    def exception(self, message: str, **kwargs):
        """
        Log an exception with traceback.

        Args:
            message: The log message
            **kwargs: Additional context fields
        """
        self._log_with_context(logging.ERROR, message, exc_info=True, **kwargs)
