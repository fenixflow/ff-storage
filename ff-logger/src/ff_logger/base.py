"""
Base scoped logger implementation using structlog.
"""

from typing import Any

import structlog
from structlog.stdlib import BoundLogger
from structlog.types import Processor


class ScopedLogger:
    """
    Base class for scoped loggers using structlog.

    Each instance has its own context and processor chain.
    Can be easily extended or overridden by importing different implementations.
    """

    def __init__(
        self,
        name: str,
        processors: list[Processor] | None = None,
        context: dict[str, Any] | None = None,
        wrapper_class: type | None = None,
        cache_logger_on_first_use: bool = True,
    ):
        """
        Initialize a scoped logger.

        Args:
            name: Logger name/scope identifier
            processors: List of structlog processors
            context: Initial context dictionary
            wrapper_class: Logger wrapper class (default: BoundLogger)
            cache_logger_on_first_use: Whether to cache the logger
        """
        self.name = name
        self._context = context or {}
        self._context["logger"] = name

        # Set up processors if not provided
        if processors is None:
            processors = self._get_default_processors()

        # Configure structlog for this logger instance
        self._logger = structlog.get_logger(
            name,
            wrapper_class=wrapper_class or BoundLogger,
            processors=processors,
            cache_logger_on_first_use=cache_logger_on_first_use,
        ).bind(**self._context)

    def _get_default_processors(self) -> list[Processor]:
        """
        Get default processor chain.
        Can be overridden in subclasses.
        """
        return [
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(),
        ]

    def bind(self, **kwargs: Any) -> "ScopedLogger":
        """
        Bind additional context to the logger.
        Returns a new logger instance with the bound context.

        Args:
            **kwargs: Key-value pairs to bind to the logger context

        Returns:
            New ScopedLogger instance with bound context
        """
        new_logger = self.__class__(
            name=self.name,
            processors=None,  # Will use same processors
            context={**self._context, **kwargs},
        )
        new_logger._logger = self._logger.bind(**kwargs)
        return new_logger

    def unbind(self, *keys: str) -> "ScopedLogger":
        """
        Remove keys from the logger context.
        Returns a new logger instance without the specified keys.

        Args:
            *keys: Keys to remove from context

        Returns:
            New ScopedLogger instance with keys removed
        """
        new_context = {k: v for k, v in self._context.items() if k not in keys}
        new_logger = self.__class__(
            name=self.name,
            processors=None,
            context=new_context,
        )
        new_logger._logger = self._logger.unbind(*keys)
        return new_logger

    def debug(self, event: str, **kwargs: Any) -> None:
        """Log a debug message."""
        self._logger.debug(event, **kwargs)

    def info(self, event: str, **kwargs: Any) -> None:
        """Log an info message."""
        self._logger.info(event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        """Log a warning message."""
        self._logger.warning(event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        """Log an error message."""
        self._logger.error(event, **kwargs)

    def critical(self, event: str, **kwargs: Any) -> None:
        """Log a critical message."""
        self._logger.critical(event, **kwargs)

    def exception(self, event: str, **kwargs: Any) -> None:
        """Log an exception with traceback."""
        self._logger.exception(event, **kwargs)

    def log(self, level: str, event: str, **kwargs: Any) -> None:
        """
        Log at a specific level.

        Args:
            level: Log level (debug, info, warning, error, critical)
            event: Event/message to log
            **kwargs: Additional context
        """
        getattr(self._logger, level.lower())(event, **kwargs)

    @property
    def context(self) -> dict[str, Any]:
        """Get the current logger context."""
        return self._context.copy()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, context={self._context!r})"
