"""
Transaction management for ff-storage.

This module provides Pythonic async context managers for database
transactions with automatic commit/rollback, isolation level control,
and savepoint support.

Usage:
    from ff_storage.transactions import Transaction, IsolationLevel

    # Basic transaction
    async with Transaction(db_pool) as txn:
        await repo.create(model, connection=txn.connection)

    # Via pool convenience method
    async with db_pool.transaction() as txn:
        await repo.create(model, connection=txn.connection)

    # With isolation level
    async with Transaction(db_pool, isolation=IsolationLevel.SERIALIZABLE) as txn:
        # High-consistency operations
        ...

    # With savepoints for partial rollback
    async with Transaction(db_pool) as txn:
        await repo.create(author, connection=txn.connection)

        try:
            async with txn.savepoint():
                await repo.create(risky_post, connection=txn.connection)
        except IntegrityError:
            pass  # Only savepoint rolled back, author preserved
"""

from .context import Transaction
from .exceptions import (
    SavepointAlreadyReleased,
    SavepointError,
    SavepointNotFound,
    TransactionAlreadyStarted,
    TransactionClosed,
    TransactionError,
    TransactionNotStarted,
)
from .isolation import IsolationLevel
from .savepoint import Savepoint
from .unit_of_work import TransactionBoundRepository, UnitOfWork

__all__ = [
    # Main classes
    "Transaction",
    "Savepoint",
    "IsolationLevel",
    "UnitOfWork",
    "TransactionBoundRepository",
    # Exceptions
    "TransactionError",
    "TransactionNotStarted",
    "TransactionAlreadyStarted",
    "TransactionClosed",
    "SavepointError",
    "SavepointNotFound",
    "SavepointAlreadyReleased",
]
