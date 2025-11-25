"""
Strategy registry and factory for temporal patterns.
"""

from typing import TYPE_CHECKING, Dict, Type

from .enums import TemporalStrategyType

if TYPE_CHECKING:
    from .strategies.base import TemporalStrategy


# Global strategy registry
STRATEGY_REGISTRY: Dict[TemporalStrategyType, Type["TemporalStrategy"]] = {}


def register_strategy(strategy_type: TemporalStrategyType):
    """
    Decorator to register a temporal strategy implementation.

    Usage:
        @register_strategy(TemporalStrategyType.COPY_ON_CHANGE)
        class CopyOnChangeStrategy(TemporalStrategy):
            pass
    """

    def decorator(cls: Type["TemporalStrategy"]) -> Type["TemporalStrategy"]:
        STRATEGY_REGISTRY[strategy_type] = cls
        return cls

    return decorator


def get_strategy(
    strategy_type: TemporalStrategyType,
    model_class,
    query_builder,
    soft_delete: bool = True,
    multi_tenant: bool = True,
    tenant_field: str = "tenant_id",
) -> "TemporalStrategy":
    """
    Factory to create strategy instance for a model.

    Args:
        strategy_type: Type of temporal strategy
        model_class: Model class (Pydantic, dataclass, etc.)
        query_builder: QueryBuilder instance for database-specific SQL generation
        soft_delete: Enable soft delete (deleted_at, deleted_by fields)
        multi_tenant: Enable multi-tenancy (tenant_id field)
        tenant_field: Name of tenant field (default: "tenant_id")

    Returns:
        Strategy instance configured for the model

    Raises:
        ValueError: If strategy type is not registered
    """
    strategy_cls = STRATEGY_REGISTRY.get(strategy_type)
    if not strategy_cls:
        raise ValueError(
            f"Unknown temporal strategy: {strategy_type}. "
            f"Available: {list(STRATEGY_REGISTRY.keys())}"
        )

    return strategy_cls(
        model_class=model_class,
        query_builder=query_builder,
        soft_delete=soft_delete,
        multi_tenant=multi_tenant,
        tenant_field=tenant_field,
    )
