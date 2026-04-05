"""
Pydantic repository - type-safe CRUD with temporal management.

Thin wrapper around TemporalRepository that automatically configures
the strategy based on Pydantic model settings.
"""

import logging
from typing import List, Optional, TypeVar
from uuid import UUID

from ..db.adapters import detect_adapter
from ..temporal.registry import get_strategy
from ..temporal.repository_base import TemporalRepository

T = TypeVar("T")


class PydanticRepository(TemporalRepository[T]):
    """
    Pydantic-specific repository with automatic strategy detection.

    Features:
    - Auto-detects temporal strategy from model
    - Type-safe: returns Pydantic model instances
    - Manages tenant context (single or multi-tenant)
    - Delegates to strategy-specific operations

    Tenant Scoping:
        - tenant_id (single UUID): Strict tenant scope for writes.
          Reads filter to this tenant. Writes FORCE this tenant_id on the model.
          Use for broker/underwriter operations.

        - tenant_ids (list of UUIDs): Permissive multi-tenant scope.
          Reads filter to IN (tenant_ids). Writes VALIDATE model.tenant_id is in list.
          Use for admin cross-tenant operations and B2B read access.

        - Neither: No tenant filtering (admin-only, use with caution).

    Usage:
        ```python
        from ff_storage import PydanticModel, PydanticRepository

        class Product(PydanticModel):
            __temporal_strategy__ = "copy_on_change"
            __soft_delete__ = True
            __multi_tenant__ = True

            name: str
            price: Decimal

        # Single tenant (broker/underwriter writes) - strict scope
        repo = PydanticRepository(
            Product,
            db_pool,
            tenant_id=current_org.id,  # Single UUID
            logger=logger
        )
        # create() forces model.tenant_id = current_org.id

        # Multi-tenant (admin/B2B reads) - permissive scope
        repo_admin = PydanticRepository(
            Product,
            db_pool,
            tenant_ids=[tenant1_id, tenant2_id],  # List of UUIDs
            logger=logger
        )
        # list() filters: WHERE tenant_id IN (tenant1_id, tenant2_id)
        # create() validates: model.tenant_id must be in list

        # CRUD operations
        product = await repo.create(Product(name="Widget", price=99.99), user_id=user.id)
        updated = await repo.update(product.id, product, user_id=user.id)
        found = await repo.get(product.id)
        products = await repo.list(filters={"status": "active"})

        # Temporal operations (if strategy supports)
        history = await repo.get_audit_history(product.id)
        versions = await repo.get_version_history(product.id)
        ```
    """

    def __init__(
        self,
        model_class: type[T],
        db_pool,
        tenant_id: Optional[UUID] = None,
        tenant_ids: Optional[List[UUID]] = None,
        logger=None,
        **kwargs,
    ):
        """
        Initialize Pydantic repository.

        Args:
            model_class: Pydantic model class (must inherit from PydanticModel)
            db_pool: Database connection pool (asyncpg, aiomysql, etc.)
            tenant_id: Single tenant context for strict scope (broker/UW writes).
                      Reads filter to this tenant. Writes force this tenant_id.
            tenant_ids: Multi-tenant context for permissive scope (admin/B2B).
                       Reads filter to IN clause. Writes validate model.tenant_id in list.
            logger: Optional logger instance
            **kwargs: Additional arguments for TemporalRepository
                     (cache_enabled, cache_ttl, collect_metrics, max_retries, etc.)

        Raises:
            ValueError: If model requires tenant context but none provided
            ValueError: If both tenant_id AND tenant_ids are specified
            ValueError: If tenant_ids is empty list
            TypeError: If tenant_id is passed a list (use tenant_ids instead)
        """
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

        # Normalize tenant_ids to remove duplicates
        if tenant_ids is not None:
            tenant_ids = list(set(tenant_ids))

        # Validate model is PydanticModel
        if not hasattr(model_class, "get_temporal_strategy"):
            raise ValueError(f"{model_class.__name__} must inherit from PydanticModel")

        # Auto-detect database adapter from pool
        adapter = detect_adapter(db_pool)

        # Auto-detect strategy from model
        strategy_type = model_class.get_temporal_strategy()
        soft_delete = getattr(model_class, "__soft_delete__", True)
        multi_tenant = getattr(model_class, "__multi_tenant__", True)
        tenant_field = getattr(model_class, "__tenant_field__", "tenant_id")

        # Get QueryBuilder from adapter for database-specific SQL generation
        query_builder = adapter.get_query_builder()

        # Create strategy instance
        strategy = get_strategy(
            strategy_type=strategy_type,
            model_class=model_class,
            query_builder=query_builder,
            soft_delete=soft_delete,
            multi_tenant=multi_tenant,
            tenant_field=tenant_field,
        )

        # Initialize base repository
        super().__init__(
            model_class=model_class,
            db_pool=db_pool,
            adapter=adapter,
            strategy=strategy,
            tenant_id=tenant_id,
            tenant_ids=tenant_ids,
            logger=logger or logging.getLogger(__name__),
            **kwargs,  # Forward cache_enabled, cache_ttl, collect_metrics, etc.
        )

    # All CRUD methods inherited from TemporalRepository
    # Temporal methods inherited from TemporalRepository
    # Type hints ensure return types are T (Pydantic model)
