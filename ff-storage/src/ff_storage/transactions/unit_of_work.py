"""
Unit of Work pattern for coordinating multiple repository operations.

The Unit of Work pattern provides a higher-level abstraction over transactions,
allowing multiple repositories to participate in a single atomic operation.

Usage:
    async with UnitOfWork(db_pool) as uow:
        author_repo = uow.repository(Author, tenant_id=tenant)
        post_repo = uow.repository(Post, tenant_id=tenant)

        author = await author_repo.create(Author(name="John"))
        await post_repo.create(Post(author_id=author.id, title="Hello"))
        # Auto-commit on exit, auto-rollback on exception
"""

from typing import TYPE_CHECKING, Any, Dict, Generic, List, Optional, Type, TypeVar
from uuid import UUID

from .context import Transaction
from .isolation import IsolationLevel
from .savepoint import Savepoint

if TYPE_CHECKING:
    from ..db.connections.postgres import PostgresPool
    from ..pydantic_support.base import PydanticModel


T = TypeVar("T", bound="PydanticModel")


class UnitOfWork:
    """
    Coordinates multiple repository operations within a single transaction.

    The Unit of Work pattern provides:
    - A single transaction for all repository operations
    - Automatic commit on successful exit
    - Automatic rollback on exception
    - Repository caching (same model+tenant returns same instance)
    - Savepoint support for partial rollback

    All repositories obtained from a UnitOfWork automatically use
    the transaction's connection, ensuring read-your-writes consistency.

    Attributes:
        isolation: The transaction isolation level
        connection: The underlying database connection (after entering context)

    Example:
        async with UnitOfWork(db_pool) as uow:
            # Get repositories bound to this unit of work
            author_repo = uow.repository(Author, tenant_id=tenant)
            post_repo = uow.repository(Post, tenant_id=tenant)

            # All operations use the same transaction
            author = await author_repo.create(Author(name="John"))
            await post_repo.create(Post(author_id=author.id))

            # Savepoints for partial rollback
            try:
                async with uow.savepoint():
                    await post_repo.create(Post(title="risky"))
            except IntegrityError:
                pass  # Only savepoint rolled back
    """

    def __init__(
        self,
        db_pool: "PostgresPool",
        isolation: Optional[IsolationLevel] = None,
    ):
        """
        Initialize a Unit of Work.

        Args:
            db_pool: PostgresPool instance to acquire connection from
            isolation: Transaction isolation level (defaults to READ COMMITTED)
        """
        self.db_pool = db_pool
        self.isolation = isolation or IsolationLevel.READ_COMMITTED

        # Internal state
        self._transaction: Optional[Transaction] = None
        self._repositories: Dict[str, Any] = {}

    @property
    def connection(self) -> Any:
        """
        Get the underlying database connection.

        Returns:
            The asyncpg connection object

        Raises:
            RuntimeError: If accessed outside of context manager
        """
        if self._transaction is None:
            raise RuntimeError(
                "UnitOfWork must be used as a context manager: "
                "async with UnitOfWork(db_pool) as uow:"
            )
        return self._transaction.connection

    @property
    def is_active(self) -> bool:
        """Check if the unit of work is currently active."""
        return self._transaction is not None and self._transaction.is_active

    async def __aenter__(self) -> "UnitOfWork":
        """
        Enter the unit of work context.

        Creates a new transaction for all repository operations.

        Returns:
            Self for use in the context manager
        """
        self._transaction = Transaction(self.db_pool, isolation=self.isolation)
        await self._transaction.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> bool:
        """
        Exit the unit of work context.

        On success: Commits all changes
        On exception: Rolls back all changes

        Args:
            exc_type: Exception type if an exception was raised
            exc_val: Exception value if an exception was raised
            exc_tb: Exception traceback if an exception was raised

        Returns:
            False to propagate exceptions
        """
        if self._transaction:
            result = await self._transaction.__aexit__(exc_type, exc_val, exc_tb)
            self._transaction = None
            self._repositories.clear()
            return result
        return False

    def repository(
        self,
        model_class: Type[T],
        tenant_id: Optional[UUID] = None,
        tenant_ids: Optional[List[UUID]] = None,
    ) -> "TransactionBoundRepository[T]":
        """
        Get a repository bound to this unit of work's transaction.

        Repositories are cached by (model_class, tenant_id) pair.
        Repeated calls with the same arguments return the same instance.

        Args:
            model_class: The PydanticModel class for the repository
            tenant_id: Single tenant ID for strict tenant scope
            tenant_ids: List of tenant IDs for permissive multi-tenant scope

        Returns:
            A TransactionBoundRepository that uses this transaction's connection
        """
        # Create a unique cache key
        tenant_key = str(tenant_id) if tenant_id else str(tenant_ids) if tenant_ids else "none"
        cache_key = f"{model_class.__name__}:{tenant_key}"

        if cache_key not in self._repositories:
            self._repositories[cache_key] = TransactionBoundRepository(
                model_class=model_class,
                db_pool=self.db_pool,
                tenant_id=tenant_id,
                tenant_ids=tenant_ids,
                connection=self.connection,
            )
        return self._repositories[cache_key]

    async def commit(self) -> None:
        """
        Commit all changes explicitly.

        After commit, a new transaction is automatically started,
        allowing continued use of the unit of work.

        Raises:
            RuntimeError: If unit of work is not active
        """
        if self._transaction is None:
            raise RuntimeError("UnitOfWork is not active")
        await self._transaction.commit()

    async def rollback(self) -> None:
        """
        Rollback all changes explicitly.

        After rollback, a new transaction is automatically started,
        allowing continued use of the unit of work.

        Raises:
            RuntimeError: If unit of work is not active
        """
        if self._transaction is None:
            raise RuntimeError("UnitOfWork is not active")
        await self._transaction.rollback()

    def savepoint(self, name: Optional[str] = None) -> Savepoint:
        """
        Create a savepoint for partial rollback capability.

        Savepoints allow rolling back part of the unit of work's
        transaction without affecting earlier operations.

        Args:
            name: Optional savepoint name (auto-generated if not provided)

        Returns:
            Savepoint context manager

        Raises:
            RuntimeError: If unit of work is not active
        """
        if self._transaction is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._transaction.savepoint(name)


class TransactionBoundRepository(Generic[T]):
    """
    Repository wrapper that automatically uses a transaction connection.

    This class wraps a PydanticRepository (via TemporalRepository) and
    ensures all operations use the provided transaction connection,
    enabling read-your-writes consistency within transactions.

    All methods delegate to the underlying repository, passing the
    transaction connection automatically.
    """

    def __init__(
        self,
        model_class: Type[T],
        db_pool: "PostgresPool",
        tenant_id: Optional[UUID],
        tenant_ids: Optional[List[UUID]],
        connection: Any,
    ):
        """
        Initialize a transaction-bound repository.

        Args:
            model_class: The PydanticModel class
            db_pool: Database connection pool
            tenant_id: Single tenant ID for strict scope
            tenant_ids: List of tenant IDs for permissive scope
            connection: The transaction's database connection
        """
        # Import here to avoid circular imports
        from ..pydantic_support.repository import PydanticRepository

        self._inner = PydanticRepository(
            model_class,
            db_pool,
            tenant_id=tenant_id,
            tenant_ids=tenant_ids,
        )
        self._connection = connection

    async def create(
        self,
        model: T,
        user_id: Optional[UUID] = None,
    ) -> T:
        """
        Create a new record using the transaction connection.

        Args:
            model: Model instance with data
            user_id: User performing the action

        Returns:
            Created model instance
        """
        return await self._inner.create(model, user_id=user_id, connection=self._connection)

    async def update(
        self,
        id: UUID,
        model: T,
        user_id: Optional[UUID] = None,
    ) -> T:
        """
        Update a record using the transaction connection.

        Args:
            id: Record ID
            model: Model instance with updated data
            user_id: User performing the action

        Returns:
            Updated model instance
        """
        return await self._inner.update(id, model, user_id=user_id, connection=self._connection)

    async def delete(
        self,
        id: UUID,
        user_id: Optional[UUID] = None,
    ) -> bool:
        """
        Delete a record using the transaction connection.

        Args:
            id: Record ID
            user_id: User performing the action

        Returns:
            True if deleted
        """
        return await self._inner.delete(id, user_id=user_id, connection=self._connection)

    async def get(
        self,
        id: UUID,
        **kwargs,
    ) -> Optional[T]:
        """
        Get a record by ID using the transaction connection.

        Uses the transaction connection to ensure read-your-writes
        consistency within the unit of work.

        Args:
            id: Record ID
            **kwargs: Additional arguments (include_deleted, etc.)

        Returns:
            Model instance or None if not found
        """
        return await self._inner.get(id, connection=self._connection, **kwargs)

    async def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **kwargs,
    ) -> List[T]:
        """
        List records using the transaction connection.

        Uses the transaction connection to ensure read-your-writes
        consistency within the unit of work.

        Args:
            filters: Filter conditions
            order_by: Ordering fields
            limit: Maximum results
            offset: Results to skip
            **kwargs: Additional arguments

        Returns:
            List of model instances
        """
        return await self._inner.list(
            filters=filters,
            order_by=order_by,
            limit=limit,
            offset=offset,
            connection=self._connection,
            **kwargs,
        )

    async def create_many(
        self,
        models: List[T],
        user_id: Optional[UUID] = None,
        batch_size: int = 100,
        atomic: bool = False,
    ) -> List[T]:
        """
        Create multiple records using the transaction connection.

        Note: When using within a UnitOfWork, atomic=True is redundant
        since all operations already share the same transaction.

        Args:
            models: List of model instances
            user_id: User performing the action
            batch_size: Records per batch
            atomic: Ignored within UoW (already atomic)

        Returns:
            List of created model instances
        """
        return await self._inner.create_many(
            models,
            user_id=user_id,
            batch_size=batch_size,
            connection=self._connection,
        )
