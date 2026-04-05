"""
Enhanced temporal repository with caching and monitoring.

Strategy-agnostic repository that delegates to temporal strategies
with production-ready features like caching, metrics, and error handling.

Tenant Scoping:
    - tenant_id (single UUID): Strict tenant scope for writes.
      Reads filter to this tenant. Writes FORCE this tenant_id on the model.
      Use for broker/underwriter operations.

    - tenant_ids (list of UUIDs): Permissive multi-tenant scope.
      Reads filter to IN (tenant_ids). Writes VALIDATE model.tenant_id is in list.
      Use for admin cross-tenant operations and B2B read access.

    - Neither: No tenant filtering (admin-only, use with caution).
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, Generic, List, Optional, TypeVar
from uuid import UUID

if TYPE_CHECKING:
    from ..transactions import IsolationLevel, Transaction

from ..db.adapters import DatabaseAdapter, detect_adapter
from ..exceptions import (
    TemporalStrategyError,
    TenantIsolationError,
    TenantNotConfigured,
)
from ..utils.metrics import async_timer, get_global_collector
from ..utils.retry import exponential_backoff, retry_async
from .helpers import CacheManager, ModelConverter, TenantScope
from .strategies.base import TemporalStrategy

T = TypeVar("T")


class TemporalRepository(Generic[T]):
    """
    Enhanced temporal repository with caching and monitoring.

    Features:
    - Query result caching with TTL
    - Automatic retry on transient failures
    - Metrics collection
    - Optimistic locking for concurrent updates
    - Tenant isolation enforcement

    Tenant Scoping:
        - tenant_id (single UUID): Strict tenant scope for writes.
          Reads filter to this tenant. Writes FORCE this tenant_id on the model.
          Use for broker/underwriter operations.

        - tenant_ids (list of UUIDs): Permissive multi-tenant scope.
          Reads filter to IN (tenant_ids). Writes VALIDATE model.tenant_id is in list.
          Use for admin cross-tenant operations and B2B read access.

        - Neither: No tenant filtering (admin-only, use with caution).

    Usage:
        # Single tenant (broker/underwriter writes) - strict scope
        repo = TemporalRepository(
            Product, db_pool, strategy,
            tenant_id=org_id,  # Single UUID
            cache_ttl=300
        )
        # create() forces model.tenant_id = org_id

        # Multi-tenant (admin/B2B reads) - permissive scope
        repo_admin = TemporalRepository(
            Product, db_pool, strategy,
            tenant_ids=[tenant1_id, tenant2_id],  # List of UUIDs
            cache_ttl=300
        )
        # list() filters: WHERE tenant_id IN (tenant1_id, tenant2_id)
        # create() validates: model.tenant_id must be in list

        product = await repo.create(Product(...), user_id=user_id)
        updated = await repo.update(product.id, Product(...), user_id=user_id)
    """

    def __init__(
        self,
        model_class: type[T],
        db_pool,
        strategy: TemporalStrategy[T],
        adapter: Optional[DatabaseAdapter] = None,
        tenant_id: Optional[UUID] = None,
        tenant_ids: Optional[List[UUID]] = None,
        logger=None,
        cache_enabled: bool = True,
        cache_ttl: int = 300,  # 5 minutes default
        collect_metrics: bool = True,
        max_retries: int = 3,
    ):
        """
        Initialize enhanced repository.

        Args:
            model_class: Model class (Pydantic, dataclass, etc.)
            db_pool: Database connection pool
            adapter: Database adapter for executing queries
            strategy: Temporal strategy instance
            tenant_id: Single tenant context for strict scope (broker/UW writes).
                      Reads filter to this tenant. Writes force this tenant_id.
            tenant_ids: Multi-tenant context for permissive scope (admin/B2B).
                       Reads filter to IN clause. Writes validate model.tenant_id in list.
            logger: Optional logger instance
            cache_enabled: Enable query result caching
            cache_ttl: Cache time-to-live in seconds
            collect_metrics: Enable metrics collection
            max_retries: Maximum retry attempts for transient failures

        Raises:
            ValueError: If model requires tenant context but none provided
            ValueError: If both tenant_id AND tenant_ids are specified
            ValueError: If tenant_ids is empty list
            TypeError: If tenant_id is passed a list (use tenant_ids instead)
        """
        self.model_class = model_class
        self.db_pool = db_pool
        # Adapter is optional; auto-detect based on pool when not provided
        self.adapter = adapter or detect_adapter(db_pool)
        self.strategy = strategy
        self.logger = logger or logging.getLogger(__name__)

        # Validate and set tenant scope using TenantScope helper
        normalized_tenant_id: Optional[UUID] = None
        normalized_tenant_ids: Optional[List[UUID]] = None

        if strategy.multi_tenant:
            # Validate mutual exclusion
            if tenant_id is not None and tenant_ids is not None:
                raise ValueError(
                    "Specify tenant_id OR tenant_ids, not both. "
                    "Use tenant_id for single-tenant (strict) scope, "
                    "tenant_ids for multi-tenant (permissive) scope."
                )

            # Validate tenant_id is not a list (catch old usage pattern)
            if tenant_id is not None and isinstance(tenant_id, (list, tuple)):
                raise TypeError(
                    "tenant_id must be a single UUID. "
                    "For multi-tenant access, use the tenant_ids parameter instead."
                )

            # Validate tenant_ids is not empty
            if tenant_ids is not None and len(tenant_ids) == 0:
                raise ValueError("tenant_ids cannot be empty. Provide at least one tenant UUID.")

            # Set tenant scope based on which parameter was provided
            if tenant_id is not None:
                # Normalize to UUID if provided as string
                normalized_tenant_id = UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
            elif tenant_ids is not None:
                # Normalize tenant_ids to remove duplicates and convert strings
                normalized = []
                for tid in tenant_ids:
                    normalized.append(UUID(tid) if isinstance(tid, str) else tid)
                normalized_tenant_ids = list(set(normalized))
            else:
                # Neither tenant_id nor tenant_ids provided for multi-tenant model
                raise TenantNotConfigured(
                    model_class.__name__,
                    message="Multi-tenant models require either tenant_id (single) or tenant_ids (list). "
                    "Use tenant_id for strict scope (broker/UW writes), "
                    "tenant_ids for permissive scope (admin cross-tenant access).",
                )

        # Initialize TenantScope helper
        self._tenant_scope = TenantScope(
            tenant_id=normalized_tenant_id,
            tenant_ids=normalized_tenant_ids,
            tenant_field=strategy.tenant_field if strategy.multi_tenant else "tenant_id",
        )

        # Initialize CacheManager helper
        self._cache_manager = CacheManager(
            enabled=cache_enabled,
            ttl_seconds=cache_ttl,
        )

        # Backward-compatible attributes
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl

        # Metrics configuration
        self.collect_metrics = collect_metrics
        self._metrics = get_global_collector() if collect_metrics else None

        # Connect metrics to cache manager
        if self._metrics:
            self._cache_manager.set_metrics_collector(self._metrics)

        # Retry configuration
        self.max_retries = max_retries

    @property
    def tenant_id(self) -> Optional[UUID]:
        """
        Single tenant ID for strict scope operations.

        Returns single tenant UUID if configured, None otherwise.
        For multi-tenant scope, use tenant_ids property instead.
        """
        return self._tenant_scope.tenant_id

    @property
    def tenant_ids(self) -> Optional[List[UUID]]:
        """
        List of tenant IDs for permissive multi-tenant scope.

        Returns list of allowed tenant UUIDs if configured, None otherwise.
        For strict single-tenant scope, use tenant_id property instead.
        """
        return self._tenant_scope.tenant_ids

    @property
    def tenant_filter_value(self) -> Optional[UUID | List[UUID]]:
        """
        Get the appropriate tenant filter value for queries.

        Returns:
            - Single UUID if tenant_id is set (strict scope)
            - List[UUID] if tenant_ids is set (permissive scope)
            - None if neither is set (admin scope)
        """
        return self._tenant_scope.filter_value

    def _validate_tenant_for_write(self, data: Dict[str, Any]) -> None:
        """
        Validate and/or set tenant_id for write operations.

        Behavior:
        - tenant_id (single): FORCE model.tenant_id = self.tenant_id
        - tenant_ids (list): VALIDATE model.tenant_id is in self.tenant_ids
        - Neither (admin): Allow any tenant_id in data

        Args:
            data: Model data dict (modified in place for single tenant_id)

        Raises:
            TenantIsolationError: If tenant_ids validation fails
        """
        if not self.strategy.multi_tenant:
            return

        # Delegate to TenantScope helper (modifies data in place for strict scope)
        self._tenant_scope.validate_for_write(data)

    def _validate_tenant_for_read(self, result: T) -> None:
        """
        Validate tenant isolation for read operations.

        Args:
            result: The fetched model instance

        Raises:
            TenantIsolationError: If result is outside tenant scope
        """
        if not self.strategy.multi_tenant or result is None:
            return

        # Delegate to TenantScope helper
        self._tenant_scope.validate_for_read(result)

    # ==================== Cache Management ====================

    def _get_cache_key(self, operation: str, **kwargs) -> str:
        """
        Generate cache key from operation and parameters.

        Returns a structured key supporting pattern matching:
        Format: {model}:{tenant}:{operation}[:{params}]

        Examples:
        - "Product:org123:list:status=active:page=1"
        - "Product:org123:get:id=abc-123:include_deleted=True"

        This allows:
        - invalidate_cache("list") to match all list queries
        - invalidate_cache(":id={uuid}") to match all operations for that record
        """
        # Delegate to CacheManager helper
        return self._cache_manager.generate_key(
            model_name=self.model_class.__name__,
            tenant_id=self.tenant_id,
            operation=operation,
            **kwargs,
        )

    async def _get_cached(self, cache_key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        # Delegate to CacheManager helper (handles deep copy internally)
        return await self._cache_manager.get(cache_key)

    async def _set_cached(self, cache_key: str, value: Any):
        """Set value in cache with TTL."""
        # Delegate to CacheManager helper (handles deep copy and eviction)
        await self._cache_manager.set(cache_key, value)

    async def invalidate_cache(self, pattern: Optional[str] = None):
        """
        Invalidate cache entries.

        Args:
            pattern: Optional pattern to match keys (None = clear all)
        """
        # Delegate to CacheManager helper
        await self._cache_manager.invalidate(pattern)

    # ==================== Transaction Support ====================

    def transaction(
        self,
        isolation: "Optional[IsolationLevel]" = None,
        readonly: bool = False,
    ) -> "Transaction":
        """
        Create a transaction context manager for this repository's pool.

        Convenience method that returns a Transaction bound to this
        repository's database pool, allowing atomic operations across
        multiple repository calls.

        Args:
            isolation: Transaction isolation level (defaults to READ COMMITTED)
            readonly: If True, the transaction only allows read operations

        Returns:
            Transaction context manager

        Example:
            async with repo.transaction() as txn:
                author = await author_repo.create(Author(name="John"), connection=txn.connection)
                await post_repo.create(Post(author_id=author.id), connection=txn.connection)
                # Auto-commit on success, auto-rollback on exception
        """
        from ..transactions import IsolationLevel, Transaction

        return Transaction(
            self.db_pool,
            isolation=isolation or IsolationLevel.READ_COMMITTED,
            readonly=readonly,
        )

    # ==================== CRUD Operations ====================

    @retry_async(
        max_attempts=3,
        delay=exponential_backoff(base_delay=0.5),
        exceptions=(asyncio.TimeoutError, ConnectionError),
    )
    async def create(
        self,
        model: T,
        user_id: Optional[UUID] = None,
        connection=None,
    ) -> T:
        """
        Create new record with retry logic and monitoring.

        Tenant Behavior:
        - tenant_id (single): FORCES model.tenant_id = self.tenant_id
        - tenant_ids (list): VALIDATES model.tenant_id is in self.tenant_ids
        - Neither (admin): Allows any tenant_id in model

        Args:
            model: Model instance with data
            user_id: User performing the action (for audit trail)
            connection: Optional database connection for external transaction management.
                       When provided, the operation uses this connection instead of
                       acquiring a new one from the pool.

        Returns:
            Created model instance

        Raises:
            TemporalStrategyError: If creation fails after retries
            TenantIsolationError: If tenant_ids validation fails
        """
        data = self._model_to_dict(model)

        # Validate/force tenant_id based on scope
        self._validate_tenant_for_write(data)

        try:
            async with async_timer(f"repo.{self.model_class.__name__}.create"):
                # For create, always pass single tenant_id (either forced or from model)
                # The validation above ensures the model has the correct tenant_id
                effective_tenant = (
                    data.get(self.strategy.tenant_field) if self.strategy.multi_tenant else None
                )

                result = await self.strategy.create(
                    data=data,
                    db_pool=self.db_pool,
                    adapter=self.adapter,
                    tenant_id=effective_tenant,
                    user_id=user_id,
                    connection=connection,
                )

                # Invalidate list cache since new record added
                await self.invalidate_cache("list")

                if self._metrics:
                    self._metrics.increment(f"repo.{self.model_class.__name__}.created")

                return result

        except TenantIsolationError:
            raise
        except Exception as e:
            self.logger.error(
                f"Failed to create {self.model_class.__name__}",
                extra={"error": str(e), "tenant_id": str(self.tenant_filter_value)},
                exc_info=True,
            )
            if self._metrics:
                self._metrics.increment(f"repo.{self.model_class.__name__}.create_failed")

            raise TemporalStrategyError(
                strategy=type(self.strategy).__name__, operation="create", error=str(e)
            )

    async def update(
        self,
        id: UUID,
        model: T,
        user_id: Optional[UUID] = None,
        connection=None,
    ) -> T:
        """
        Update record.

        Behavior depends on strategy:
        - none/copy_on_change: Direct UPDATE
        - scd2: Creates new version

        Args:
            id: Record ID
            model: Model instance with updated data
            user_id: User performing the action
            connection: Optional database connection for external transaction management.
                       When provided, the operation uses this connection instead of
                       acquiring a new one from the pool.

        Returns:
            Updated model instance
        """
        # Use exclude_unset=True to only update explicitly provided fields
        # This prevents overwriting managed fields (id, tenant_id, created_at)
        data = self._model_to_dict(model, exclude_unset=True)

        try:
            result = await self.strategy.update(
                id=id,
                data=data,
                db_pool=self.db_pool,
                adapter=self.adapter,
                tenant_id=self.tenant_id,
                user_id=user_id,
                connection=connection,
            )

            # Invalidate ALL cached variants for this record ID
            # (e.g., get(id), get(id, include_deleted=True), etc.)
            await self.invalidate_cache(f":id={id}")

            # Also invalidate list cache since the record was modified
            await self.invalidate_cache("list")

            return result
        except Exception as e:
            self.logger.error(
                f"Failed to update {self.model_class.__name__}",
                extra={"id": str(id), "error": str(e), "tenant_id": self.tenant_id},
                exc_info=True,
            )
            raise

    async def delete(
        self,
        id: UUID,
        user_id: Optional[UUID] = None,
        connection=None,
    ) -> bool:
        """
        Delete record.

        Behavior depends on strategy:
        - soft_delete enabled: Sets deleted_at
        - soft_delete disabled: Hard DELETE

        Args:
            id: Record ID
            user_id: User performing the action
            connection: Optional database connection for external transaction management.
                       When provided, the operation uses this connection instead of
                       acquiring a new one from the pool.

        Returns:
            True if deleted, False if not found
        """
        try:
            result = await self.strategy.delete(
                id=id,
                db_pool=self.db_pool,
                adapter=self.adapter,
                tenant_id=self.tenant_id,
                user_id=user_id,
                connection=connection,
            )

            # Invalidate ALL cached variants for this record ID
            # (e.g., get(id), get(id), include_deleted=True), etc.)
            await self.invalidate_cache(f":id={id}")

            # Also invalidate list cache since the record was deleted
            await self.invalidate_cache("list")

            return result
        except Exception as e:
            self.logger.error(
                f"Failed to delete {self.model_class.__name__}",
                extra={"id": str(id), "error": str(e), "tenant_id": self.tenant_id},
                exc_info=True,
            )
            raise

    async def transfer_ownership(
        self,
        id: UUID,
        new_tenant_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> T:
        """
        Transfer record ownership to a different tenant (superadmin only).

        This operation changes the tenant_id of a record, effectively moving it
        between tenants. Should only be called for authorized superadmin operations.

        Args:
            id: Record ID
            new_tenant_id: New tenant to own this record
            user_id: User performing the transfer (for audit trail)

        Returns:
            Updated model instance with new tenant_id

        Raises:
            ValueError: If strategy doesn't support transfer_ownership
            TemporalStrategyError: If transfer fails
        """
        if not hasattr(self.strategy, "transfer_ownership"):
            raise ValueError(
                f"transfer_ownership() not available for strategy {type(self.strategy).__name__}"
            )

        try:
            result = await self.strategy.transfer_ownership(
                id=id,
                new_tenant_id=new_tenant_id,
                db_pool=self.db_pool,
                adapter=self.adapter,
                current_tenant_id=self.tenant_id,
                user_id=user_id,
            )

            # Invalidate ALL cached variants for this record ID
            await self.invalidate_cache(f":id={id}")

            # Also invalidate list cache since tenant changed
            await self.invalidate_cache("list")

            return result
        except Exception as e:
            self.logger.error(
                f"Failed to transfer ownership for {self.model_class.__name__}",
                extra={"id": str(id), "new_tenant_id": str(new_tenant_id), "error": str(e)},
                exc_info=True,
            )
            raise

    async def get(
        self,
        id: UUID,
        **kwargs,
    ) -> Optional[T]:
        """
        Get record by ID with caching.

        Tenant Behavior:
        - tenant_id (single): Validates result.tenant_id == self.tenant_id
        - tenant_ids (list): Validates result.tenant_id IN self.tenant_ids
        - Neither (admin): No validation

        Kwargs (strategy-dependent):
        - as_of: datetime - Time travel (scd2 only)
        - include_deleted: bool - Include soft-deleted records

        Args:
            id: Record ID

        Returns:
            Model instance or None if not found

        Raises:
            TemporalStrategyError: If get operation fails
            TenantIsolationError: If record belongs to different tenant
        """
        # Generate cache key
        cache_key = self._get_cache_key("get", id=str(id), **kwargs)

        # Check cache
        cached_result = await self._get_cached(cache_key)
        if cached_result is not None:
            return cached_result

        try:
            async with async_timer(f"repo.{self.model_class.__name__}.get"):
                # For get(), we don't filter by tenant in the query (strategy does that)
                # Instead, we validate the result after fetching
                result = await self.strategy.get(
                    id=id,
                    db_pool=self.db_pool,
                    tenant_id=self.tenant_id,  # Strategy uses this for filtering if single
                    **kwargs,
                )

                # Validate tenant isolation if result found
                self._validate_tenant_for_read(result)

                # Cache the result
                if result:
                    await self._set_cached(cache_key, result)

                if self._metrics:
                    self._metrics.increment(f"repo.{self.model_class.__name__}.get")

                return result

        except TenantIsolationError:
            raise
        except Exception as e:
            self.logger.error(
                f"Failed to get {self.model_class.__name__}",
                extra={"id": str(id), "error": str(e), "tenant_id": str(self.tenant_filter_value)},
                exc_info=True,
            )
            raise TemporalStrategyError(
                strategy=type(self.strategy).__name__, operation="get", error=str(e)
            )

    async def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        **kwargs,
    ) -> List[T]:
        """
        List records with filters.

        Tenant Behavior:
        - tenant_id (single): Filters WHERE tenant_id = self.tenant_id
        - tenant_ids (list): Filters WHERE tenant_id IN (self.tenant_ids)
        - Neither (admin): No tenant filtering

        Args:
            filters: Field filters (key=value)
            limit: Max records to return
            offset: Pagination offset

        Kwargs (strategy-dependent):
        - as_of: datetime - Time travel (scd2 only)
        - include_deleted: bool - Include soft-deleted records

        Returns:
            List of model instances
        """
        try:
            # Use tenant_filter_value which returns UUID, List[UUID], or None
            return await self.strategy.list(
                filters=filters,
                db_pool=self.db_pool,
                tenant_id=self.tenant_filter_value,  # Passes single UUID, list, or None
                limit=limit,
                offset=offset,
                **kwargs,
            )
        except Exception as e:
            self.logger.error(
                f"Failed to list {self.model_class.__name__}",
                extra={
                    "filters": filters,
                    "error": str(e),
                    "tenant_id": str(self.tenant_filter_value),
                },
                exc_info=True,
            )
            raise

    async def count(
        self,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> int:
        """
        Count records matching filters.

        Tenant Behavior:
        - tenant_id (single): Filters WHERE tenant_id = self.tenant_id
        - tenant_ids (list): Filters WHERE tenant_id IN (self.tenant_ids)
        - Neither (admin): No tenant filtering

        Args:
            filters: Field filters (key=value)

        Kwargs (strategy-dependent):
        - include_deleted: bool - Include soft-deleted records

        Returns:
            Count of matching records
        """
        # Get table name
        table_name = self._get_table_name()

        # Build WHERE clause
        where_parts = []
        where_values = []

        # Multi-tenant filter: Add to filters dict
        # Use tenant_filter_value which handles both single UUID and List[UUID]
        if self.strategy.multi_tenant and self.tenant_filter_value is not None:
            if filters is None:
                filters = {}
            # Only add tenant filter if not already specified
            if self.strategy.tenant_field not in filters:
                filters[self.strategy.tenant_field] = self.tenant_filter_value

        # Current version filters (soft delete, SCD2, etc.)
        include_deleted = kwargs.get("include_deleted", False)
        if not include_deleted:
            current_filters = self.strategy.get_current_version_filters()
            where_parts.extend(current_filters)

        # User filters (with validation to prevent SQL injection)
        # This now includes tenant filtering and properly handles List[UUID]
        if filters:
            filter_clauses, filter_values = self.strategy._validate_and_build_filter_clauses(
                filters, base_param_count=len(where_values)
            )
            where_parts.extend(filter_clauses)
            where_values.extend(filter_values)

        # Build query
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        query = f"SELECT COUNT(*) FROM {table_name} {where_clause}"

        # Execute
        async with self.db_pool.acquire() as conn:
            result = await conn.fetchval(query, *where_values)

        return result

    # ==================== Soft Delete Operations ====================

    async def restore(
        self,
        id: UUID,
    ) -> Optional[T]:
        """
        Restore a soft-deleted record.

        Only available if soft_delete is enabled.

        Args:
            id: Record ID

        Returns:
            Restored model instance or None if not found
        """
        if not self.strategy.soft_delete:
            raise ValueError("restore() only available with soft_delete enabled")

        if not hasattr(self.strategy, "restore"):
            raise ValueError(f"Strategy {type(self.strategy).__name__} does not support restore()")

        try:
            result = await self.strategy.restore(
                id=id,
                db_pool=self.db_pool,
                adapter=self.adapter,
                tenant_id=self.tenant_id,
            )

            # Invalidate ALL cached variants for this record ID
            # (e.g., get(id), get(id, include_deleted=True), etc.)
            await self.invalidate_cache(f":id={id}")

            # Also invalidate list cache since the record was restored
            await self.invalidate_cache("list")

            return result
        except Exception as e:
            self.logger.error(
                f"Failed to restore {self.model_class.__name__}",
                extra={"id": str(id), "error": str(e), "tenant_id": self.tenant_id},
                exc_info=True,
            )
            raise

    # ==================== Strategy-Specific Methods ====================

    async def get_audit_history(
        self,
        record_id: UUID,
    ):
        """
        Get audit history (copy_on_change strategy only).

        Returns:
            List of AuditEntry objects
        """
        if not hasattr(self.strategy, "get_audit_history"):
            raise ValueError(
                f"get_audit_history() not available for strategy {type(self.strategy).__name__}"
            )

        return await self.strategy.get_audit_history(
            record_id=record_id,
            db_pool=self.db_pool,
            tenant_id=self.tenant_id,
        )

    async def get_field_history(
        self,
        record_id: UUID,
        field_name: str,
    ):
        """
        Get field history (copy_on_change strategy only).

        Returns:
            List of AuditEntry objects for specific field
        """
        if not hasattr(self.strategy, "get_field_history"):
            raise ValueError(
                f"get_field_history() not available for strategy {type(self.strategy).__name__}"
            )

        return await self.strategy.get_field_history(
            record_id=record_id,
            field_name=field_name,
            db_pool=self.db_pool,
            tenant_id=self.tenant_id,
        )

    async def get_version_history(
        self,
        id: UUID,
    ) -> List[T]:
        """
        Get version history (scd2 strategy only).

        Returns:
            List of all versions (model instances)
        """
        if not hasattr(self.strategy, "get_version_history"):
            raise ValueError(
                f"get_version_history() not available for strategy {type(self.strategy).__name__}"
            )

        return await self.strategy.get_version_history(
            id=id,
            db_pool=self.db_pool,
            tenant_id=self.tenant_id,
        )

    async def get_version(
        self,
        id: UUID,
        version: int,
    ) -> Optional[T]:
        """
        Get specific version (scd2 strategy only).

        Returns:
            Model instance for that version or None
        """
        if not hasattr(self.strategy, "get_version"):
            raise ValueError(
                f"get_version() not available for strategy {type(self.strategy).__name__}"
            )

        return await self.strategy.get_version(
            id=id,
            version=version,
            db_pool=self.db_pool,
            tenant_id=self.tenant_id,
        )

    async def compare_versions(
        self,
        id: UUID,
        version1: int,
        version2: int,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compare two versions (scd2 strategy only).

        Returns:
            Dict mapping field_name → {old, new, changed}
        """
        if not hasattr(self.strategy, "compare_versions"):
            raise ValueError(
                f"compare_versions() not available for strategy {type(self.strategy).__name__}"
            )

        return await self.strategy.compare_versions(
            id=id,
            version1=version1,
            version2=version2,
            db_pool=self.db_pool,
            tenant_id=self.tenant_id,
        )

    # ==================== Batch Operations ====================

    async def create_many(
        self,
        models: List[T],
        user_id: Optional[UUID] = None,
        batch_size: int = 100,
        atomic: bool = False,
        connection=None,
    ) -> List[T]:
        """
        Create multiple records efficiently in batches.

        Args:
            models: List of model instances
            user_id: User performing the action
            batch_size: Number of records per batch
            atomic: If True, all creates happen in a single transaction.
                   If any create fails, all are rolled back. Default False.
            connection: Optional database connection for external transaction
                       management. When provided, the operation uses this
                       connection instead of acquiring a new one from the pool.

        Returns:
            List of created model instances

        Example:
            # Non-atomic (default) - partial success possible
            results = await repo.create_many(models)

            # Atomic - all-or-nothing
            results = await repo.create_many(models, atomic=True)

            # With external transaction
            async with repo.transaction() as txn:
                results = await repo.create_many(models, connection=txn.connection)
        """
        if not models:
            return []

        if atomic and connection is None:
            # Wrap in a transaction for all-or-nothing semantics
            return await self._create_many_atomic(models, user_id, batch_size)

        return await self._create_many_batched(models, user_id, batch_size, connection)

    async def _create_many_atomic(
        self,
        models: List[T],
        user_id: Optional[UUID] = None,
        batch_size: int = 100,
    ) -> List[T]:
        """
        Create all records atomically within a single transaction.

        If any create fails, all changes are rolled back.
        """
        async with self.transaction() as txn:
            return await self._create_many_batched(
                models, user_id, batch_size, connection=txn.connection
            )

    async def _create_many_batched(
        self,
        models: List[T],
        user_id: Optional[UUID] = None,
        batch_size: int = 100,
        connection=None,
    ) -> List[T]:
        """
        Create records in batches, optionally using an external connection.
        """
        results = []
        total = len(models)

        try:
            for i in range(0, total, batch_size):
                batch = models[i : i + batch_size]
                batch_data = [self._model_to_dict(m) for m in batch]

                # Process batch
                async with async_timer(f"repo.{self.model_class.__name__}.create_batch"):
                    if hasattr(self.strategy, "create_many"):
                        # Strategy supports batch creation
                        batch_results = await self.strategy.create_many(
                            data_list=batch_data,
                            db_pool=self.db_pool,
                            adapter=self.adapter,
                            tenant_id=self.tenant_id,
                            user_id=user_id,
                            connection=connection,
                        )
                    else:
                        # Fall back to individual creates
                        batch_results = []
                        for data in batch_data:
                            result = await self.strategy.create(
                                data=data,
                                db_pool=self.db_pool,
                                adapter=self.adapter,
                                tenant_id=self.tenant_id,
                                user_id=user_id,
                                connection=connection,
                            )
                            batch_results.append(result)

                    results.extend(batch_results)

                self.logger.info(
                    f"Created batch {i // batch_size + 1}/{(total + batch_size - 1) // batch_size} "
                    f"({len(batch_results)} records)"
                )

            # Invalidate cache after batch creation
            await self.invalidate_cache("list")

            if self._metrics:
                self._metrics.increment(
                    f"repo.{self.model_class.__name__}.batch_created", value=len(results)
                )

            return results

        except Exception as e:
            self.logger.error(
                f"Failed to batch create {self.model_class.__name__}",
                extra={"count": total, "error": str(e), "tenant_id": self.tenant_id},
                exc_info=True,
            )
            raise TemporalStrategyError(
                strategy=type(self.strategy).__name__, operation="create_many", error=str(e)
            )

    async def get_many(
        self,
        ids: List[UUID],
        **kwargs,
    ) -> Dict[UUID, Optional[T]]:
        """
        Get multiple records by IDs efficiently.

        Args:
            ids: List of record IDs

        Returns:
            Dict mapping ID to model instance (or None if not found)
        """
        if not ids:
            return {}

        results = {}

        # Check cache for each ID
        uncached_ids = []
        for id in ids:
            cache_key = self._get_cache_key("get", id=str(id), **kwargs)
            cached = await self._get_cached(cache_key)
            if cached is not None:
                # _get_cached already returns a deep copy
                results[id] = cached
            else:
                uncached_ids.append(id)

        # Fetch uncached records
        if uncached_ids:
            try:
                async with async_timer(f"repo.{self.model_class.__name__}.get_many"):
                    # Build IN query
                    placeholders = ", ".join([f"${i + 1}" for i in range(len(uncached_ids))])
                    query = f"""
                        SELECT * FROM {self._get_table_name()}
                        WHERE id IN ({placeholders})
                    """

                    # Add tenant filter (with proper identifier quoting)
                    values = list(uncached_ids)
                    if self.strategy.multi_tenant:
                        quoted_tenant_field = self.strategy.query_builder.quote_identifier(
                            self.strategy.tenant_field
                        )
                        query += f" AND {quoted_tenant_field} = ${len(values) + 1}"
                        values.append(self.tenant_id)

                    # Add current version filters (prevent data leakage)
                    current_filters = self.strategy.get_current_version_filters()
                    if current_filters:
                        query += f" AND {' AND '.join(current_filters)}"

                    # Execute query
                    async with self.db_pool.acquire() as conn:
                        rows = await conn.fetch(query, *values)

                    # Convert rows to models and cache
                    for row in rows:
                        model = self._dict_to_model(dict(row))
                        id = row["id"]
                        results[id] = model

                        # Cache the result
                        cache_key = self._get_cache_key("get", id=str(id), **kwargs)
                        await self._set_cached(cache_key, model)

                    # Add None for missing IDs
                    for id in uncached_ids:
                        if id not in results:
                            results[id] = None

            except Exception as e:
                self.logger.error(
                    f"Failed to batch get {self.model_class.__name__}",
                    extra={"ids": [str(id) for id in ids], "error": str(e)},
                    exc_info=True,
                )
                raise

        return results

    # ==================== Helper Methods ====================

    def _get_table_name(self) -> str:
        """
        Get fully-qualified table name with schema.

        Returns schema-qualified name (e.g., "public.products") to ensure
        queries work correctly regardless of PostgreSQL search_path configuration.
        """
        # Delegate to ModelConverter helper
        return ModelConverter.get_table_name(self.model_class)

    def _model_to_dict(self, model: T, exclude_unset: bool = False) -> Dict[str, Any]:
        """
        Convert model instance to dict, excluding computed fields.

        Computed fields (properties decorated with @computed_field) are
        derived values that should not be stored in the database.

        Args:
            model: The model instance to convert
            exclude_unset: If True, only includes fields explicitly set by the user.
                          Use True for UPDATE operations to avoid overwriting managed
                          fields (id, tenant_id, created_at) with None values.
                          Use False (default) for CREATE operations to include all
                          fields including those with default_factory values.

        Returns:
            Dictionary representation of the model
        """
        # Delegate to ModelConverter helper
        return ModelConverter.to_dict(model, exclude_unset=exclude_unset)

    def _dict_to_model(self, data: Dict[str, Any]) -> T:
        """Convert dict to model instance."""
        # Delegate to ModelConverter helper
        return ModelConverter.from_dict(self.model_class, data)
