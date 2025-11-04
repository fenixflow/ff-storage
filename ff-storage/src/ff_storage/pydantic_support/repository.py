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
    - Manages tenant context
    - Delegates to strategy-specific operations

    Usage:
        ```python
        from ff_storage import PydanticModel, PydanticRepository

        class Product(PydanticModel):
            __temporal_strategy__ = "copy_on_change"
            __soft_delete__ = True
            __multi_tenant__ = True

            name: str
            price: Decimal

        # Create repository with single tenant
        repo = PydanticRepository(
            Product,
            db_pool,
            tenant_id=current_org.id,
            logger=logger
        )

        # Or with multiple tenants for cross-tenant access
        repo_admin = PydanticRepository(
            Product,
            db_pool,
            tenant_id=[tenant1_id, tenant2_id],
            logger=logger
        )

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
        tenant_id: Optional[UUID | List[UUID]] = None,
        logger=None,
        **kwargs,
    ):
        """
        Initialize Pydantic repository.

        Args:
            model_class: Pydantic model class (must inherit from PydanticModel)
            db_pool: Database connection pool (asyncpg, aiomysql, etc.)
            tenant_id: Tenant context (required if model is multi-tenant).
                      Can be single UUID or list of UUIDs for cross-tenant access.
            logger: Optional logger instance
            **kwargs: Additional arguments for TemporalRepository
                     (cache_enabled, cache_ttl, collect_metrics, max_retries, etc.)

        Raises:
            ValueError: If model requires tenant_id but none provided
        """
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
            logger=logger or logging.getLogger(__name__),
            **kwargs,  # Forward cache_enabled, cache_ttl, collect_metrics, etc.
        )

    # All CRUD methods inherited from TemporalRepository
    # Temporal methods inherited from TemporalRepository
    # Type hints ensure return types are T (Pydantic model)
