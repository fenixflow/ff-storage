"""
Schema synchronization system for ff-storage.

Provides Terraform-like schema management with automatic detection
of schema changes and safe migration generation.

Sync Usage:
    from ff_storage.db import Postgres, SchemaManager

    db = Postgres(...)
    db.connect()

    manager = SchemaManager(db, logger=logger)
    changes = manager.sync_schema(
        models=get_all_models(),
        allow_destructive=False,
        dry_run=False
    )

Async Usage (NEW in v4.8):
    from ff_storage.db.schema_sync import AsyncSchemaManager

    pool = PostgresPool(...)
    await pool.connect()

    manager = AsyncSchemaManager(pool, logger=logger)
    changes = await manager.sync_schema(
        models=get_all_models(),
        allow_destructive=False,
        dry_run=False
    )
"""

from .async_introspector import AsyncPostgresSchemaIntrospector
from .async_manager import AsyncSchemaManager
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
    # Main orchestrators
    "SchemaManager",
    "AsyncSchemaManager",
    # Async introspector
    "AsyncPostgresSchemaIntrospector",
    # Data models
    "ColumnDefinition",
    "IndexDefinition",
    "TableDefinition",
    "SchemaChange",
    # Enums
    "ColumnType",
    "ChangeType",
]
