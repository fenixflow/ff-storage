"""
Savepoint context manager for nested transactions.

Savepoints allow partial rollback within a transaction, enabling
error recovery without losing all transaction progress.

Usage:
    async with Transaction(db_pool) as txn:
        await repo.create(author, connection=txn.connection)

        try:
            async with txn.savepoint() as sp:
                await repo.create(risky_post, connection=sp.connection)
        except IntegrityError:
            # Only savepoint rolled back, author still in transaction
            pass

        # Author will be committed when transaction exits
"""

from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from .exceptions import SavepointAlreadyReleased

if TYPE_CHECKING:
    pass


class Savepoint:
    """
    Async context manager for database savepoints.

    A savepoint is a named point within a transaction that allows
    partial rollback. If an error occurs within the savepoint,
    only the work after the savepoint is rolled back.

    Attributes:
        connection: The database connection (same as parent transaction)
        name: The savepoint name (auto-generated if not provided)
    """

    def __init__(self, connection: Any, name: Optional[str] = None):
        """
        Initialize a savepoint.

        Args:
            connection: The asyncpg connection from the parent transaction
            name: Optional savepoint name (auto-generated if not provided)
        """
        self._connection = connection
        self._name = name or f"sp_{uuid4().hex[:8]}"
        self._released = False
        self._rolled_back = False

    @property
    def connection(self) -> Any:
        """
        Get the database connection.

        Returns the same connection as the parent transaction,
        allowing operations to participate in the transaction.
        """
        return self._connection

    @property
    def name(self) -> str:
        """Get the savepoint name."""
        return self._name

    @property
    def is_active(self) -> bool:
        """Check if the savepoint is still active (not released or rolled back)."""
        return not self._released and not self._rolled_back

    async def __aenter__(self) -> "Savepoint":
        """
        Enter the savepoint context and create the savepoint.

        Returns:
            Self for use in the context manager
        """
        await self._connection.execute(f"SAVEPOINT {self._name}")
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> bool:
        """
        Exit the savepoint context.

        On success (no exception): Release the savepoint
        On exception: Rollback to the savepoint

        Args:
            exc_type: Exception type if an exception was raised
            exc_val: Exception value if an exception was raised
            exc_tb: Exception traceback if an exception was raised

        Returns:
            False to propagate exceptions (never suppresses)
        """
        if self._released or self._rolled_back:
            return False

        if exc_type is None:
            # Success - release the savepoint
            await self.release()
        else:
            # Error - rollback to savepoint
            await self.rollback()

        return False  # Don't suppress exceptions

    async def release(self) -> None:
        """
        Release the savepoint explicitly.

        After release, the savepoint's changes become part of
        the parent transaction and cannot be rolled back separately.

        Raises:
            SavepointAlreadyReleased: If the savepoint was already released
        """
        if self._released:
            raise SavepointAlreadyReleased(self._name)

        if not self._rolled_back:
            await self._connection.execute(f"RELEASE SAVEPOINT {self._name}")
            self._released = True

    async def rollback(self) -> None:
        """
        Rollback to this savepoint.

        Undoes all changes made after the savepoint was created,
        but preserves changes made before the savepoint.

        Note: After rollback, the savepoint is still usable for
        subsequent operations until the parent transaction ends.
        """
        if not self._released and not self._rolled_back:
            await self._connection.execute(f"ROLLBACK TO SAVEPOINT {self._name}")
            self._rolled_back = True
