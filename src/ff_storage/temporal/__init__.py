"""
Temporal data management module for ff-storage.

Provides standalone temporal patterns that work with any model system:
- none: Standard CRUD with basic timestamps
- copy_on_change: Field-level audit trail
- scd2: Slowly Changing Dimension Type 2 (immutable versions)

Cross-cutting features:
- soft_delete: Recoverable deletes
- multi_tenant: Data isolation by tenant
"""

from .enums import TemporalStrategyType
from .registry import get_strategy, register_strategy
from .repository_base import TemporalRepository

__all__ = [
    "TemporalStrategyType",
    "get_strategy",
    "register_strategy",
    "TemporalRepository",
]
