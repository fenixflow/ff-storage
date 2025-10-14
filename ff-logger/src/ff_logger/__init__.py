"""
ff-logger: Scoped logging package for Fenixflow applications.

This package provides instance-based loggers that can be passed around as objects,
with support for context binding and multiple output formats.
"""

from .base import ScopedLogger
from .console import ConsoleLogger
from .database import DatabaseHandler, DatabaseLogger
from .file import FileLogger
from .json_logger import JSONLogger
from .null import NullLogger

# Version is read from package metadata (pyproject.toml is the single source of truth)
try:
    from importlib.metadata import version

    __version__ = version("ff-logger")
except Exception:
    __version__ = "0.0.0+unknown"

__all__ = [
    # Base class
    "ScopedLogger",
    # Logger implementations
    "ConsoleLogger",
    "NullLogger",
    "JSONLogger",
    "DatabaseLogger",
    "FileLogger",
    "DatabaseHandler",
]
