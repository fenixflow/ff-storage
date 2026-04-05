"""
Database connection and operation modules.

Sync Connections (for scripts, simple apps):
    - Postgres, MySQL, SQLServer

Async Pools (for FastAPI, production apps):
    - PostgresPool, MySQLPool, SQLServerPool

Schema Management:
    - SchemaManager (Terraform-like schema synchronization - sync)
    - AsyncSchemaManager (NEW in v4.8 - async, works with PostgresPool)
"""

from .connections import (
    MySQL,
    MySQLBase,
    MySQLPool,
    Postgres,
    PostgresBase,
    PostgresPool,
    SQLServer,
    SQLServerBase,
    SQLServerPool,
)
from .schema_sync import AsyncSchemaManager, SchemaManager
from .sql import SQL

__all__ = [
    "SQL",
    # PostgreSQL - sync and async
    "Postgres",  # Sync direct connection
    "PostgresPool",  # Async connection pool
    "PostgresBase",
    # MySQL - sync and async
    "MySQL",  # Sync direct connection
    "MySQLPool",  # Async connection pool
    "MySQLBase",
    # SQL Server - sync and async
    "SQLServer",  # Sync direct connection
    "SQLServerPool",  # Async connection pool
    "SQLServerBase",
    # Schema Sync (replaces MigrationManager in v2.0.0)
    "SchemaManager",  # Sync (uses Postgres connection)
    "AsyncSchemaManager",  # Async (uses PostgresPool)
]
