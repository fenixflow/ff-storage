"""
JSON logger implementation for structured logging.
"""

import socket
import sys
from typing import Any

import structlog
from structlog.types import Processor

from .base import ScopedLogger


class JSONLogger(ScopedLogger):
    """
    A logger that outputs structured JSON lines.
    Perfect for production environments and log aggregation systems.
    """

    def __init__(
        self,
        name: str,
        context: dict[str, Any] | None = None,
        add_hostname: bool = True,
        add_process_info: bool = False,
        stream=None,
    ):
        """
        Initialize a JSON logger.

        Args:
            name: Logger name/scope
            context: Initial context dictionary
            add_hostname: Whether to include hostname
            add_process_info: Whether to include process/thread info
            stream: Output stream (default: sys.stdout)
        """
        self.stream = stream or sys.stdout
        self.add_hostname = add_hostname
        self.add_process_info = add_process_info

        # Build initial context
        if context is None:
            context = {}

        if add_hostname:
            context["hostname"] = socket.gethostname()

        if add_process_info:
            import os
            import threading

            context["pid"] = os.getpid()
            context["thread"] = threading.current_thread().name

        super().__init__(name=name, context=context)

    def _get_default_processors(self) -> list[Processor]:
        """Get JSON-specific processors."""
        processors = [
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                ]
            ),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

        return processors
