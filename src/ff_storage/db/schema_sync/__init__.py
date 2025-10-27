"""
Schema synchronization system for ff-storage.

Provides Terraform-like schema management with automatic detection
of schema changes and safe migration generation.

Usage:
    from ff_storage.db import Postgres, SchemaManager

    db = Postgres(...)
    db.connect()

    manager = SchemaManager(db, logger=logger)
    changes = manager.sync_schema(
        models=get_all_models(),
        allow_destructive=False,
        dry_run=False
    )
"""

from .manager import SchemaManager
from .models import (
    ChangeType,
    ColumnDefinition,
    ColumnType,
    IndexDefinition,
    SchemaChange,
    TableDefinition,
)

__all__ = [
    # Main orchestrator
    "SchemaManager",
    # Data models
    "ColumnDefinition",
    "IndexDefinition",
    "TableDefinition",
    "SchemaChange",
    # Enums
    "ColumnType",
    "ChangeType",
]
