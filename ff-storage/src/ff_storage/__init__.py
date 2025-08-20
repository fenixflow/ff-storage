"""
ff-storage: Database and file storage operations for Fenixflow applications.
"""

__version__ = "0.1.0"

# Database exports
from .db.postgres import Postgres, PostgresPool
from .db.mysql import MySQL, MySQLPool
from .db.migrations import MigrationManager

__all__ = [
    # PostgreSQL
    "Postgres",
    "PostgresPool",
    # MySQL
    "MySQL",
    "MySQLPool",
    # Migrations
    "MigrationManager",
]