"""
Temporal repository base class.

Strategy-agnostic repository that delegates to temporal strategies.
"""

import logging
from typing import Any, Dict, Generic, List, Optional, TypeVar
from uuid import UUID

from .strategies.base import TemporalStrategy

T = TypeVar("T")


class TemporalRepository(Generic[T]):
    """
    Strategy-agnostic temporal repository.

    Delegates all CRUD operations to the configured temporal strategy.
    Manages tenant and user context.

    Usage:
        strategy = get_strategy(TemporalStrategyType.COPY_ON_CHANGE, Product)
        repo = TemporalRepository(Product, db_pool, strategy, tenant_id=org_id)

        product = await repo.create(Product(...), user_id=user_id)
        updated = await repo.update(product.id, Product(...), user_id=user_id)
    """

    def __init__(
        self,
        model_class: type[T],
        db_pool,
        strategy: TemporalStrategy[T],
        tenant_id: Optional[UUID] = None,
        logger=None,
    ):
        """
        Initialize repository.

        Args:
            model_class: Model class (Pydantic, dataclass, etc.)
            db_pool: Database connection pool
            strategy: Temporal strategy instance
            tenant_id: Tenant context (for multi-tenant models)
            logger: Optional logger instance
        """
        self.model_class = model_class
        self.db_pool = db_pool
        self.strategy = strategy
        self.tenant_id = tenant_id
        self.logger = logger or logging.getLogger(__name__)

        # Validation
        if strategy.multi_tenant and not tenant_id:
            raise ValueError(
                f"Model {model_class.__name__} is multi-tenant but no tenant_id provided to repository"
            )

    # ==================== CRUD Operations ====================

    async def create(
        self,
        model: T,
        user_id: Optional[UUID] = None,
    ) -> T:
        """
        Create new record.

        Args:
            model: Model instance with data
            user_id: User performing the action (for audit trail)

        Returns:
            Created model instance
        """
        data = self._model_to_dict(model)

        try:
            return await self.strategy.create(
                data=data,
                db_pool=self.db_pool,
                tenant_id=self.tenant_id,
                user_id=user_id,
            )
        except Exception as e:
            self.logger.error(
                f"Failed to create {self.model_class.__name__}",
                extra={"error": str(e), "tenant_id": self.tenant_id},
                exc_info=True,
            )
            raise

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
            return await self.strategy.update(
                id=id,
                data=data,
                db_pool=self.db_pool,
                tenant_id=self.tenant_id,
                user_id=user_id,
            )
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
            return await self.strategy.delete(
                id=id,
                db_pool=self.db_pool,
                tenant_id=self.tenant_id,
                user_id=user_id,
            )
        except Exception as e:
            self.logger.error(
                f"Failed to delete {self.model_class.__name__}",
                extra={"id": str(id), "error": str(e), "tenant_id": self.tenant_id},
                exc_info=True,
            )
            raise

    async def get(
        self,
        id: UUID,
        **kwargs,
    ) -> Optional[T]:
        """
        Get record by ID.

        Kwargs (strategy-dependent):
        - as_of: datetime - Time travel (scd2 only)
        - include_deleted: bool - Include soft-deleted records

        Args:
            id: Record ID

        Returns:
            Model instance or None if not found
        """
        try:
            return await self.strategy.get(
                id=id,
                db_pool=self.db_pool,
                tenant_id=self.tenant_id,
                **kwargs,
            )
        except Exception as e:
            self.logger.error(
                f"Failed to get {self.model_class.__name__}",
                extra={"id": str(id), "error": str(e), "tenant_id": self.tenant_id},
                exc_info=True,
            )
            raise

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

        # Multi-tenant filter
        if self.strategy.multi_tenant:
            where_parts.append(f"{self.strategy.tenant_field} = ${len(where_values) + 1}")
            where_values.append(self.tenant_id)

        # Soft delete filter (if not include_deleted)
        include_deleted = kwargs.get("include_deleted", False)
        if self.strategy.soft_delete and not include_deleted:
            where_parts.append("deleted_at IS NULL")

        # SCD2: current version only
        if hasattr(self.strategy, "get_temporal_fields"):
            temporal_fields = self.strategy.get_temporal_fields()
            if "valid_to" in temporal_fields:
                where_parts.append("valid_to IS NULL")

        # User filters
        if filters:
            for key, value in filters.items():
                where_parts.append(f"{key} = ${len(where_values) + 1}")
                where_values.append(value)

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
            return await self.strategy.restore(
                id=id,
                db_pool=self.db_pool,
                tenant_id=self.tenant_id,
            )
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

    # ==================== Helper Methods ====================

    def _get_table_name(self) -> str:
        """Get table name from model class."""
        if hasattr(self.model_class, "table_name"):
            return self.model_class.table_name()
        elif hasattr(self.model_class, "__table_name__"):
            return self.model_class.__table_name__
        else:
            return self.model_class.__name__.lower() + "s"

    def _model_to_dict(self, model: T) -> Dict[str, Any]:
        """Convert model instance to dict."""
        if hasattr(model, "model_dump"):
            # Pydantic v2
            return model.model_dump()
        elif hasattr(model, "dict"):
            # Pydantic v1
            return model.dict()
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
