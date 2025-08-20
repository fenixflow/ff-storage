"""
Console logger implementation with colored output.
"""

import socket
import sys
from typing import Any

import structlog
from structlog.types import Processor

from .base import ScopedLogger


class ConsoleLogger(ScopedLogger):
    """
    A logger that outputs to console with colored, human-readable format.
    Perfect for development and debugging.
    """

    def __init__(
        self,
        name: str,
        context: dict[str, Any] | None = None,
        colors: bool = True,
        add_hostname: bool = False,
        stream=None,
    ):
        """
        Initialize a console logger.

        Args:
            name: Logger name/scope
            context: Initial context dictionary
            colors: Whether to use colored output
            add_hostname: Whether to include hostname in logs
            stream: Output stream (default: sys.stdout)
        """
        self.stream = stream or sys.stdout
        self.colors = colors
        self.add_hostname = add_hostname

        # Add hostname to context if requested
        if add_hostname and context is None:
            context = {}
        if add_hostname:
            context["hostname"] = socket.gethostname()

        super().__init__(name=name, context=context)

    def _get_default_processors(self) -> list[Processor]:
        """Get console-specific processors."""
        processors = [
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
        ]

        # Add appropriate renderer based on colors setting
        if self.colors:
            processors.append(
                structlog.dev.ConsoleRenderer(
                    colors=True,
                    exception_formatter=structlog.dev.rich_traceback,
                )
            )
        else:
            processors.append(structlog.dev.ConsoleRenderer(colors=False))

        return processors
