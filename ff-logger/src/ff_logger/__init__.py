"""
ff-logger: Structured logging package for Fenixflow applications.

Provides scoped loggers with multiple backends using structlog.
"""

__version__ = "0.1.0"

from .base import ScopedLogger
from .config import configure_logging, get_logger
from .console import ConsoleLogger
from .database import DatabaseLogger
from .json import JSONLogger
from .null import NullLogger

__all__ = [
    "ScopedLogger",
    "ConsoleLogger",
    "JSONLogger",
    "DatabaseLogger",
    "NullLogger",
    "configure_logging",
    "get_logger",
]
