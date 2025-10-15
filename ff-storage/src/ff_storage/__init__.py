"""
ff-storage: Database and file storage operations for Fenixflow applications.
"""

# Version is read from package metadata (pyproject.toml is the single source of truth)
try:
    from importlib.metadata import version

    __version__ = version("ff-storage")
except Exception:
    __version__ = "0.0.0+unknown"

# Database exports
from .db import MySQL, MySQLPool, Postgres, PostgresPool, SchemaManager

# Object storage exports
from .object import AzureBlobObjectStorage, LocalObjectStorage, ObjectStorage, S3ObjectStorage

__all__ = [
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
