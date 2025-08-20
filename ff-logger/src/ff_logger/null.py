"""
Null logger implementation for zero-cost disabled logging.

Note: If your code calls logger.info("some %s", arg) (i.e., letting the logger
handle string interpolation), that's minimal overhead. If you do
logger.info(f"some {arg}"), Python will build the string before calling the
logger (meaning you pay the cost of string construction even if the logger
is a no-op). To minimize overhead in production, stick to the logger's
built-in interpolation with %s and pass arguments instead of f-strings.
"""

from typing import Any


class NullLogger:
    """
    A no-op (do nothing) logger that implements the same interface as ScopedLogger
    but does nothing. This provides zero-cost logging when disabled.

    All methods are no-ops and return immediately without any processing.
    """

    def __init__(self, name: str, level: Any = None, context: dict[str, Any] | None = None):
        """
        Initialize the null logger.

        Args:
            name: Logger name (stored but not used)
            level: Log level (accepted but ignored)
            context: Context fields (accepted but ignored)
        """
        self.name = name
        self.level = level
        self.context = context or {}

    def get_logger(self):
        """
        Returns self for compatibility with ScopedLogger interface.

        Returns:
            Self (NullLogger instance)
        """
        return self

    def bind(self, **kwargs) -> "NullLogger":
        """
        Create a new NullLogger with additional context.
        For compatibility only - returns a new NullLogger.

        Args:
            **kwargs: Context fields (accepted but ignored)

        Returns:
            A new NullLogger instance
        """
        new_context = {**self.context, **kwargs}
        return NullLogger(name=f"{self.name}.bound", level=self.level, context=new_context)

    def debug(self, *args, **kwargs):
        """No-op debug log."""
        pass

    def info(self, *args, **kwargs):
        """No-op info log."""
        pass

    def warning(self, *args, **kwargs):
        """No-op warning log."""
        pass

    def error(self, *args, **kwargs):
        """No-op error log."""
        pass

    def critical(self, *args, **kwargs):
        """No-op critical log."""
        pass

    def exception(self, *args, **kwargs):
        """No-op exception log."""
        pass

    def log(self, *args, **kwargs):
        """No-op generic log."""
        pass

    # Compatibility methods for standard logging interface
    def isEnabledFor(self, level):
        """
        Always returns False since logging is disabled.

        Args:
            level: Log level to check

        Returns:
            False
        """
        return False

    def setLevel(self, level):
        """No-op setLevel for compatibility."""
        pass

    def addHandler(self, handler):
        """No-op addHandler for compatibility."""
        pass

    def removeHandler(self, handler):
        """No-op removeHandler for compatibility."""
        pass

    def __repr__(self):
        """String representation of the NullLogger."""
        return f"NullLogger(name={self.name!r})"
