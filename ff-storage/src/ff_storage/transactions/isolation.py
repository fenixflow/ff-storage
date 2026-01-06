"""
Isolation level definitions for database transactions.

PostgreSQL supports four isolation levels:
- READ UNCOMMITTED: Treated as READ COMMITTED in PostgreSQL
- READ COMMITTED: Default level, sees only committed data
- REPEATABLE READ: Sees snapshot from start of transaction
- SERIALIZABLE: Strictest level, full serializability
"""

from enum import Enum


class IsolationLevel(Enum):
    """
    PostgreSQL transaction isolation levels.

    Usage:
        async with Transaction(db_pool, isolation=IsolationLevel.SERIALIZABLE) as txn:
            # High-consistency operation
            ...
    """

    READ_UNCOMMITTED = "READ UNCOMMITTED"
    READ_COMMITTED = "READ COMMITTED"
    REPEATABLE_READ = "REPEATABLE READ"
    SERIALIZABLE = "SERIALIZABLE"

    @classmethod
    def default(cls) -> "IsolationLevel":
        """Return the default isolation level (READ COMMITTED)."""
        return cls.READ_COMMITTED
