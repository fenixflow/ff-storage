"""
Enhanced temporal repository with caching and monitoring.

Strategy-agnostic repository that delegates to temporal strategies
with production-ready features like caching, metrics, and error handling.
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Dict, Generic, List, Optional, Tuple, TypeVar
from uuid import UUID

from ..db.adapters import DatabaseAdapter, detect_adapter
from ..exceptions import (
    TemporalStrategyError,
    TenantIsolationError,
    TenantNotConfigured,
)
from ..utils.metrics import async_timer, get_global_collector
from ..utils.retry import exponential_backoff, retry_async
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

    Usage:
        strategy = get_strategy(TemporalStrategyType.COPY_ON_CHANGE, Product)
        repo = TemporalRepository(
            Product, db_pool, strategy,
            tenant_id=org_id,
            cache_ttl=300  # 5 minute cache
        )

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
            tenant_id: Tenant context (for multi-tenant models)
            logger: Optional logger instance
            cache_enabled: Enable query result caching
            cache_ttl: Cache time-to-live in seconds
            collect_metrics: Enable metrics collection
            max_retries: Maximum retry attempts for transient failures
        """
        self.model_class = model_class
        self.db_pool = db_pool
        # Adapter is optional; auto-detect based on pool when not provided
        self.adapter = adapter or detect_adapter(db_pool)
        self.strategy = strategy
        self.logger = logger or logging.getLogger(__name__)

        # Validate tenant_id for multi-tenant models
        if strategy.multi_tenant:
            if tenant_id is None:
                raise TenantNotConfigured(model_class.__name__)
            # Normalize to UUID if provided as string
            self._tenant_id = UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
        else:
            self._tenant_id = None

        # Caching configuration
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Tuple[Any, float]] = {}  # key -> (value, expiry_time)
        self._cache_lock = asyncio.Lock()

        # Metrics configuration
        self.collect_metrics = collect_metrics
        self._metrics = get_global_collector() if collect_metrics else None

        # Retry configuration
        self.max_retries = max_retries

    @property
    def tenant_id(self) -> Optional[UUID]:
        """
        Tenant ID for write operations.

        Returns single tenant UUID for multi-tenant models, None for single-tenant.
        """
        return self._tenant_id

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
        # Build structured key parts
        parts = [
            self.model_class.__name__,
            str(self.tenant_id) if self.tenant_id else "global",
            operation,  # Keep operation visible for pattern matching
        ]

        # Add parameters (sorted for consistency)
        if kwargs:
            sorted_params = sorted(kwargs.items())
            param_str = ":".join(f"{k}={v}" for k, v in sorted_params)
            parts.append(param_str)

        key = ":".join(parts)

        # Limit key size by hashing params if too long
        if len(key) > 500:
            base_parts = parts[:3]  # model, tenant, operation
            param_data = {k: v for k, v in kwargs.items()}
            param_hash = hashlib.sha256(
                json.dumps(param_data, default=str, sort_keys=True).encode()
            ).hexdigest()[:16]

            # Keep ID visible for pattern matching
            id_val = kwargs.get("id")
            if id_val:
                key = f"{':'.join(base_parts)}:h{param_hash}:id={id_val}"
            else:
                key = f"{':'.join(base_parts)}:h{param_hash}"

        return key

    async def _get_cached(self, cache_key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if not self.cache_enabled:
            return None

        async with self._cache_lock:
            if cache_key in self._cache:
                value, expiry = self._cache[cache_key]
                if time.time() < expiry:
                    if self._metrics:
                        self._metrics.increment("cache.hits")
                    # Return a deep copy to prevent mutation
                    import copy

                    return copy.deepcopy(value)
                else:
                    # Expired, remove from cache
                    del self._cache[cache_key]

        if self._metrics:
            self._metrics.increment("cache.misses")
        return None

    async def _set_cached(self, cache_key: str, value: Any):
        """Set value in cache with TTL."""
        if not self.cache_enabled:
            return

        # Store a deep copy to prevent mutation
        import copy

        cached_value = copy.deepcopy(value)

        expiry = time.time() + self.cache_ttl
        async with self._cache_lock:
            self._cache[cache_key] = (cached_value, expiry)

            # Limit cache size (simple LRU by removing oldest entries)
            if len(self._cache) > 1000:
                # Remove expired entries first
                now = time.time()
                expired_keys = [k for k, (_, exp) in self._cache.items() if exp < now]
                for k in expired_keys:
                    del self._cache[k]

                # If still too large, remove oldest 20%
                if len(self._cache) > 1000:
                    sorted_items = sorted(self._cache.items(), key=lambda x: x[1][1])
                    for k, _ in sorted_items[:200]:
                        del self._cache[k]

    async def invalidate_cache(self, pattern: Optional[str] = None):
        """
        Invalidate cache entries.

        Args:
            pattern: Optional pattern to match keys (None = clear all)
        """
        async with self._cache_lock:
            if pattern is None:
                self._cache.clear()
            else:
                keys_to_remove = [k for k in self._cache if pattern in k]
                for k in keys_to_remove:
                    del self._cache[k]

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
    ) -> T:
        """
        Create new record with retry logic and monitoring.

        Args:
            model: Model instance with data
            user_id: User performing the action (for audit trail)

        Returns:
            Created model instance

        Raises:
            TemporalStrategyError: If creation fails after retries
        """
        data = self._model_to_dict(model)

        try:
            async with async_timer(f"repo.{self.model_class.__name__}.create"):
                result = await self.strategy.create(
                    data=data,
                    db_pool=self.db_pool,
                    adapter=self.adapter,
                    tenant_id=self.tenant_id,
                    user_id=user_id,
                )

                # Invalidate list cache since new record added
                await self.invalidate_cache("list")

                if self._metrics:
                    self._metrics.increment(f"repo.{self.model_class.__name__}.created")

                return result

        except Exception as e:
            self.logger.error(
                f"Failed to create {self.model_class.__name__}",
                extra={"error": str(e), "tenant_id": self.tenant_id},
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

        Returns:
            Updated model instance
        """
        data = self._model_to_dict(model)

        try:
            result = await self.strategy.update(
                id=id,
                data=data,
                db_pool=self.db_pool,
                adapter=self.adapter,
                tenant_id=self.tenant_id,
                user_id=user_id,
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
    ) -> bool:
        """
        Delete record.

        Behavior depends on strategy:
        - soft_delete enabled: Sets deleted_at
        - soft_delete disabled: Hard DELETE

        Args:
            id: Record ID
            user_id: User performing the action

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
                result = await self.strategy.get(
                    id=id,
                    db_pool=self.db_pool,
                    tenant_id=self.tenant_id,
                    **kwargs,
                )

                # Validate tenant isolation if result found
                if result and self.strategy.multi_tenant:
                    result_tenant = getattr(result, self.strategy.tenant_field, None)
                    if result_tenant and result_tenant != self.tenant_id:
                        raise TenantIsolationError(
                            requested_tenant=str(self.tenant_id),
                            actual_tenant=str(result_tenant),
                            operation="get",
                        )

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
                extra={"id": str(id), "error": str(e), "tenant_id": self.tenant_id},
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
            return await self.strategy.list(
                filters=filters,
                db_pool=self.db_pool,
                tenant_id=self.tenant_id,
                limit=limit,
                offset=offset,
                **kwargs,
            )
        except Exception as e:
            self.logger.error(
                f"Failed to list {self.model_class.__name__}",
                extra={"filters": filters, "error": str(e), "tenant_id": self.tenant_id},
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

        # Multi-tenant filter (with proper identifier quoting)
        if self.strategy.multi_tenant:
            quoted_tenant_field = self.strategy.query_builder.quote_identifier(
                self.strategy.tenant_field
            )
            where_parts.append(f"{quoted_tenant_field} = ${len(where_values) + 1}")
            where_values.append(self.tenant_id)

        # Current version filters (soft delete, SCD2, etc.)
        include_deleted = kwargs.get("include_deleted", False)
        if not include_deleted:
            current_filters = self.strategy.get_current_version_filters()
            where_parts.extend(current_filters)

        # User filters (with validation to prevent SQL injection)
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
    ) -> List[T]:
        """
        Create multiple records efficiently in batches.

        Args:
            models: List of model instances
            user_id: User performing the action
            batch_size: Number of records per batch

        Returns:
            List of created model instances
        """
        if not models:
            return []

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
        # Try to use full_table_name() method if available (includes schema)
        if hasattr(self.model_class, "full_table_name"):
            return self.model_class.full_table_name()

        # Fallback: construct schema-qualified name manually
        schema = getattr(self.model_class, "__schema__", "public")

        if hasattr(self.model_class, "table_name"):
            table = self.model_class.table_name()
        elif hasattr(self.model_class, "__table_name__"):
            table = self.model_class.__table_name__
        else:
            table = self.model_class.__name__.lower() + "s"

        return f"{schema}.{table}"

    def _model_to_dict(self, model: T) -> Dict[str, Any]:
        """
        Convert model instance to dict.

        For updates, only includes fields that were explicitly set by the user.
        This prevents accidentally overwriting managed fields (id, tenant_id,
        created_at, etc.) with None values.
        """
        if hasattr(model, "model_dump"):
            # Pydantic v2: Only include explicitly set fields for partial updates
            return model.model_dump(exclude_unset=True)
        elif hasattr(model, "dict"):
            # Pydantic v1: Only include explicitly set fields
            return model.dict(exclude_unset=True)
        elif hasattr(model, "__dataclass_fields__"):
            # Dataclass
            from dataclasses import asdict

            return asdict(model)
        else:
            # Fallback: dict of non-private attributes
            return {
                k: getattr(model, k)
                for k in dir(model)
                if not k.startswith("_") and not callable(getattr(model, k))
            }

    def _dict_to_model(self, data: Dict[str, Any]) -> T:
        """Convert dict to model instance."""
        if hasattr(self.model_class, "model_validate"):
            # Pydantic v2
            return self.model_class.model_validate(data)
        elif hasattr(self.model_class, "parse_obj"):
            # Pydantic v1
            return self.model_class.parse_obj(data)
        elif hasattr(self.model_class, "__dataclass_fields__"):
            # Dataclass
            return self.model_class(**data)
        else:
            # Fallback: direct instantiation
            return self.model_class(**data)
