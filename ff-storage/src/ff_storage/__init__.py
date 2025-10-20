"""
ff-storage: Database and file storage operations for Fenixflow applications.

v3.0.0: Now with Pydantic ORM and temporal data management!
"""

# Version is read from package metadata (pyproject.toml is the single source of truth)
try:
    from importlib.metadata import version

    __version__ = version("ff-storage")
except Exception:
    __version__ = "3.0.0"

# Pydantic ORM (NEW in v3.0)
from .pydantic_support.base import PydanticModel
from .pydantic_support.repository import PydanticRepository

# Temporal strategies (NEW in v3.0)
from .temporal.enums import TemporalStrategyType
from .temporal.repository_base import TemporalRepository

# Database exports
from .db import MySQL, MySQLPool, Postgres, PostgresPool, SchemaManager

# Object storage exports
from .object import AzureBlobObjectStorage, LocalObjectStorage, ObjectStorage, S3ObjectStorage

__all__ = [
    # Pydantic ORM
    "PydanticModel",
    "PydanticRepository",
    # Temporal
    "TemporalStrategyType",
    "TemporalRepository",
    # PostgreSQL
    "Postgres",
    "PostgresPool",
    # MySQL
    "MySQL",
    "MySQLPool",
    # Schema Management
    "SchemaManager",
    # Object Storage
    "ObjectStorage",
    "LocalObjectStorage",
    "S3ObjectStorage",
    "AzureBlobObjectStorage",
]
