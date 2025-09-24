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

    Can be used directly as a class without instantiation:
        NullLogger.info("message")  # Does nothing

    Or as a default parameter:
        def my_func(logger=NullLogger):
            logger.info("message")
    """

    def __init__(
        self,
        name: str = "null",
        level: int | str | None = None,
        context: dict[str, Any] | None = None,
        *args,
        **kwargs,
    ):
        """
        Initialize the null logger. All parameters are optional and ignored.

        This method exists primarily for backward compatibility. The preferred
        usage is to call class methods directly without instantiation.

        Args:
            name: Optional logger name (ignored)
            level: Optional log level (ignored)
            context: Optional context fields (ignored)
            *args, **kwargs: Accept and ignore any other arguments
        """
        pass

    @classmethod
    def get_logger(cls):
        """
        Returns the class itself for compatibility with ScopedLogger interface.

        Returns:
            The NullLogger class
        """
        return cls

    @classmethod
    def bind(cls, **kwargs) -> "NullLogger":
        """
        For compatibility only - returns the NullLogger class itself.

        Since NullLogger doesn't do anything with context, binding is meaningless.

        Args:
            **kwargs: Context fields (accepted but ignored)

        Returns:
            The NullLogger class
        """
        return cls

    @classmethod
    def debug(cls, *args, **kwargs):
        """No-op debug log."""
        pass

    @classmethod
    def info(cls, *args, **kwargs):
        """No-op info log."""
        pass

    @classmethod
    def warning(cls, *args, **kwargs):
        """No-op warning log."""
        pass

    @classmethod
    def error(cls, *args, **kwargs):
        """No-op error log."""
        pass

    @classmethod
    def critical(cls, *args, **kwargs):
        """No-op critical log."""
        pass

    @classmethod
    def exception(cls, *args, **kwargs):
        """No-op exception log."""
        pass

    @classmethod
    def log(cls, *args, **kwargs):
        """No-op generic log."""
        pass

    # Compatibility methods for standard logging interface
    @classmethod
    def isEnabledFor(cls, level):
        """
        Always returns False since logging is disabled.

        Args:
            level: Log level to check

        Returns:
            False
        """
        return False

    @classmethod
    def setLevel(cls, level):
        """No-op setLevel for compatibility."""
        pass

    @classmethod
    def addHandler(cls, handler):
        """No-op addHandler for compatibility."""
        pass

    @classmethod
    def removeHandler(cls, handler):
        """No-op removeHandler for compatibility."""
        pass

    def __repr__(self):
        """String representation of the NullLogger."""
        return "NullLogger()"

    @classmethod
    def __class_repr__(cls):
        """String representation when used as a class."""
        return "NullLogger"
