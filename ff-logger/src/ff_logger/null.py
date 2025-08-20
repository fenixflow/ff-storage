"""
Null logger implementation for zero-cost disabled logging.
"""

from typing import Any

import structlog
from structlog.testing import LogCapture


class NullLogger:
    """
    A zero-cost null logger that discards all log messages.

    When using this logger, expensive operations in log arguments
    are never evaluated, providing true zero-cost logging when disabled.

    Example:
        logger = NullLogger("disabled")
        logger.debug("msg", data=expensive_function())  # expensive_function() NOT called!
    """

    def __init__(self, name: str, context: dict[str, Any] | None = None):
        """
        Initialize a null logger.

        Args:
            name: Logger name (for compatibility)
            context: Initial context (ignored but accepted for compatibility)
        """
        self.name = name
        self._context = context or {}
        self._context["logger"] = name

        # Use structlog's PrintLogger with file=None for zero-cost logging
        # This is the most efficient way - no string formatting, no I/O
        self._logger = structlog.PrintLogger(file=None)

    def bind(self, **kwargs: Any) -> "NullLogger":
        """
        Bind context (no-op, returns self for chaining).

        Args:
            **kwargs: Context to bind (ignored)

        Returns:
            Self for method chaining
        """
        return self

    def unbind(self, *keys: str) -> "NullLogger":
        """
        Unbind context (no-op, returns self for chaining).

        Args:
            *keys: Keys to unbind (ignored)

        Returns:
            Self for method chaining
        """
        return self

    def debug(self, event: str, **kwargs: Any) -> None:
        """Debug log (no-op)."""
        pass

    def info(self, event: str, **kwargs: Any) -> None:
        """Info log (no-op)."""
        pass

    def warning(self, event: str, **kwargs: Any) -> None:
        """Warning log (no-op)."""
        pass

    def error(self, event: str, **kwargs: Any) -> None:
        """Error log (no-op)."""
        pass

    def critical(self, event: str, **kwargs: Any) -> None:
        """Critical log (no-op)."""
        pass

    def exception(self, event: str, **kwargs: Any) -> None:
        """Exception log (no-op)."""
        pass

    def log(self, level: str, event: str, **kwargs: Any) -> None:
        """Log at any level (no-op)."""
        pass

    @property
    def context(self) -> dict[str, Any]:
        """Get context (returns empty dict for compatibility)."""
        return {}

    def __repr__(self) -> str:
        return f"NullLogger(name={self.name!r})"


class CaptureLogger:
    """
    A logger that captures log messages for testing.
    Useful for verifying that your code logs the right things.
    """

    def __init__(self, name: str, context: dict[str, Any] | None = None):
        """
        Initialize a test logger.

        Args:
            name: Logger name
            context: Initial context
        """
        self.name = name
        self._context = context or {}
        self._context["logger"] = name
        self._capture = LogCapture()

        # Create a logger that captures to our LogCapture
        self._logger = structlog.get_logger(name).bind(**self._context)
        structlog.configure(processors=[self._capture])

    @property
    def entries(self) -> list:
        """Get captured log entries."""
        return self._capture.entries

    def clear(self) -> None:
        """Clear captured entries."""
        self._capture.entries.clear()

    def bind(self, **kwargs: Any) -> "CaptureLogger":
        """Bind additional context."""
        new_logger = CaptureLogger(self.name, {**self._context, **kwargs})
        new_logger._capture = self._capture  # Share the same capture
        return new_logger

    def unbind(self, *keys: str) -> "CaptureLogger":
        """Remove keys from context."""
        new_context = {k: v for k, v in self._context.items() if k not in keys}
        new_logger = CaptureLogger(self.name, new_context)
        new_logger._capture = self._capture  # Share the same capture
        return new_logger

    def debug(self, event: str, **kwargs: Any) -> None:
        """Log debug message."""
        self._logger.debug(event, **kwargs)

    def info(self, event: str, **kwargs: Any) -> None:
        """Log info message."""
        self._logger.info(event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        """Log warning message."""
        self._logger.warning(event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        """Log error message."""
        self._logger.error(event, **kwargs)

    def critical(self, event: str, **kwargs: Any) -> None:
        """Log critical message."""
        self._logger.critical(event, **kwargs)

    def exception(self, event: str, **kwargs: Any) -> None:
        """Log exception with traceback."""
        self._logger.exception(event, **kwargs)

    def log(self, level: str, event: str, **kwargs: Any) -> None:
        """Log at specific level."""
        getattr(self._logger, level.lower())(event, **kwargs)

    @property
    def context(self) -> dict[str, Any]:
        """Get current context."""
        return self._context.copy()
