"""
Database connection implementations.

Provides connection classes for PostgreSQL, MySQL, SQL Server,
and MongoDB with both synchronous and async pool support.
"""

from .mysql import MySQL, MySQLBase, MySQLPool
from .postgres import Postgres, PostgresBase, PostgresPool
from .sqlserver import SQLServer, SQLServerBase, SQLServerPool

# MongoDB is an optional dependency
try:
    from .mongo import MongoPool
except ImportError:
    MongoPool = None  # type: ignore[assignment,misc]

__all__ = [
    # PostgreSQL
    "Postgres",
    "PostgresBase",
    "PostgresPool",
    # MySQL
    "MySQL",
    "MySQLBase",
    "MySQLPool",
    # SQL Server
    "SQLServer",
    "SQLServerBase",
    "SQLServerPool",
    # MongoDB
    "MongoPool",
]
