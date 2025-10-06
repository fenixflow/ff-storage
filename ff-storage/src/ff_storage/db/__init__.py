"""
Database connection and operation modules.

Sync Connections (for scripts, simple apps):
    - Postgres, MySQL, SQLServer

Async Pools (for FastAPI, production apps):
    - PostgresPool, MySQLPool, SQLServerPool
"""

from .migrations import MigrationManager
from .mysql import MySQL, MySQLBase, MySQLPool
from .postgres import Postgres, PostgresBase, PostgresPool
from .sql import SQL
from .sqlserver import SQLServer, SQLServerBase, SQLServerPool

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
    # Migrations
    "MigrationManager",
]
