"""
Transaction context manager for ff-storage.

Provides a Pythonic async context manager for database transactions
with automatic commit/rollback, isolation level control, and savepoint support.

Usage:
    # Basic transaction
    async with Transaction(db_pool) as txn:
        await repo.create(model, connection=txn.connection)
        # Auto-commit on success, auto-rollback on exception

    # With isolation level
    async with Transaction(db_pool, isolation=IsolationLevel.SERIALIZABLE) as txn:
        # High-consistency operations
        ...

    # With savepoints
    async with Transaction(db_pool) as txn:
        await repo.create(author, connection=txn.connection)

        try:
            async with txn.savepoint() as sp:
                await repo.create(risky_post, connection=sp.connection)
        except IntegrityError:
            pass  # Only savepoint rolled back

        # Author still committed
"""

from typing import TYPE_CHECKING, Any, Optional

from .exceptions import TransactionAlreadyStarted, TransactionClosed, TransactionNotStarted
from .isolation import IsolationLevel
from .savepoint import Savepoint

if TYPE_CHECKING:
    from ..db.connections.postgres import PostgresPool


class Transaction:
    """
    Async context manager for database transactions.

    Provides automatic transaction management with:
    - Auto-commit on successful exit
    - Auto-rollback on exception
    - Configurable isolation levels
    - Read-only transaction support
    - Nested transaction detection (auto-converts to savepoint)
    - Savepoint support for partial rollback

    Attributes:
        connection: The database connection for passing to repository methods
        isolation: The transaction isolation level
        readonly: Whether the transaction is read-only
    """

    def __init__(
        self,
        db_pool: "PostgresPool",
        isolation: Optional[IsolationLevel] = None,
        readonly: bool = False,
    ):
        """
        Initialize a transaction.

        Args:
            db_pool: PostgresPool instance to acquire connection from
            isolation: Transaction isolation level (defaults to READ COMMITTED)
            readonly: If True, the transaction only allows read operations
        """
        self.db_pool = db_pool
        self.isolation = isolation or IsolationLevel.default()
        self.readonly = readonly

        # Internal state
        self._connection: Optional[Any] = None
        self._transaction: Optional[Any] = None
        self._started = False
        self._closed = False

        # Nested transaction support
        self._is_savepoint = False
        self._savepoint: Optional[Savepoint] = None

    @property
    def connection(self) -> Any:
        """
        Get the database connection for use in repository methods.

        Returns:
            The asyncpg connection object

        Raises:
            TransactionNotStarted: If accessed before entering context
            TransactionClosed: If accessed after transaction is closed
        """
        if not self._started:
            raise TransactionNotStarted(
                "Transaction must be used as a context manager: "
                "async with Transaction(db_pool) as txn:"
            )
        if self._closed:
            raise TransactionClosed("Transaction has been committed or rolled back")
        return self._connection

    @property
    def is_active(self) -> bool:
        """Check if the transaction is currently active."""
        return self._started and not self._closed

    async def __aenter__(self) -> "Transaction":
        """
        Enter the transaction context.

        Acquires a connection from the pool, starts a transaction,
        and optionally sets isolation level and read-only mode.

        If the connection already has an active transaction (nested case),
        automatically creates a savepoint instead.

        Returns:
            Self for use in the context manager

        Raises:
            TransactionAlreadyStarted: If the transaction was already started
        """
        if self._started:
            raise TransactionAlreadyStarted()

        # Acquire connection from pool
        self._connection = await self.db_pool.pool.acquire()

        try:
            # Check if this is a nested transaction
            # asyncpg connections have is_in_transaction() method
            if (
                hasattr(self._connection, "is_in_transaction")
                and self._connection.is_in_transaction()
            ):
                # Nested transaction - use savepoint
                self._is_savepoint = True
                self._savepoint = Savepoint(self._connection)
                await self._savepoint.__aenter__()
            else:
                # Normal transaction
                self._is_savepoint = False
                self._transaction = self._connection.transaction()
                await self._transaction.start()

                # Set isolation level if not default
                if self.isolation != IsolationLevel.READ_COMMITTED:
                    await self._connection.execute(
                        f"SET TRANSACTION ISOLATION LEVEL {self.isolation.value}"
                    )

                # Set read-only mode if requested
                if self.readonly:
                    await self._connection.execute("SET TRANSACTION READ ONLY")

            self._started = True
            return self

        except Exception:
            # Release connection on error
            await self.db_pool.pool.release(self._connection)
            raise

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> bool:
        """
        Exit the transaction context.

        On success (no exception): Commits the transaction
        On exception: Rolls back the transaction

        Always releases the connection back to the pool.

        Args:
            exc_type: Exception type if an exception was raised
            exc_val: Exception value if an exception was raised
            exc_tb: Exception traceback if an exception was raised

        Returns:
            False to propagate exceptions (never suppresses)
        """
        try:
            if self._is_savepoint and self._savepoint:
                # Delegate to savepoint
                await self._savepoint.__aexit__(exc_type, exc_val, exc_tb)
            elif self._transaction:
                if exc_type is None:
                    # Success - commit
                    await self._transaction.commit()
                else:
                    # Error - rollback
                    await self._transaction.rollback()
        finally:
            self._closed = True
            # Release connection back to pool
            if self._connection:
                await self.db_pool.pool.release(self._connection)

        return False  # Don't suppress exceptions

    async def commit(self) -> None:
        """
        Commit the transaction explicitly.

        Typically not needed when using the context manager, as commit
        happens automatically on successful exit. Useful for long-running
        transactions that need intermediate commits.

        After commit, a new transaction is automatically started on
        the same connection, allowing continued use.

        Raises:
            TransactionNotStarted: If transaction hasn't been started
            TransactionClosed: If transaction is already closed
        """
        if not self._started:
            raise TransactionNotStarted()
        if self._closed:
            raise TransactionClosed()

        if self._is_savepoint and self._savepoint:
            await self._savepoint.release()
            # Start a new savepoint for continued use
            self._savepoint = Savepoint(self._connection)
            await self._savepoint.__aenter__()
        elif self._transaction:
            await self._transaction.commit()
            # Start a new transaction for continued use
            self._transaction = self._connection.transaction()
            await self._transaction.start()

    async def rollback(self) -> None:
        """
        Rollback the transaction explicitly.

        Undoes all changes made within the transaction.
        After rollback, a new transaction is automatically started
        on the same connection, allowing continued use.

        Raises:
            TransactionNotStarted: If transaction hasn't been started
            TransactionClosed: If transaction is already closed
        """
        if not self._started:
            raise TransactionNotStarted()
        if self._closed:
            raise TransactionClosed()

        if self._is_savepoint and self._savepoint:
            await self._savepoint.rollback()
            # Start a new savepoint for continued use
            self._savepoint = Savepoint(self._connection)
            await self._savepoint.__aenter__()
        elif self._transaction:
            await self._transaction.rollback()
            # Start a new transaction for continued use
            self._transaction = self._connection.transaction()
            await self._transaction.start()

    def savepoint(self, name: Optional[str] = None) -> Savepoint:
        """
        Create a savepoint for partial rollback capability.

        Savepoints allow rolling back part of a transaction without
        affecting earlier operations.

        Args:
            name: Optional savepoint name (auto-generated if not provided)

        Returns:
            Savepoint context manager

        Raises:
            TransactionNotStarted: If transaction hasn't been started
            TransactionClosed: If transaction is already closed

        Example:
            async with Transaction(db_pool) as txn:
                await repo.create(author, connection=txn.connection)

                try:
                    async with txn.savepoint() as sp:
                        await repo.create(risky_post, connection=sp.connection)
                except IntegrityError:
                    pass  # Only savepoint rolled back

                # Author still committed
        """
        if not self._started:
            raise TransactionNotStarted()
        if self._closed:
            raise TransactionClosed()

        return Savepoint(self._connection, name)
