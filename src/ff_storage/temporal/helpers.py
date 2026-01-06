"""
Internal helpers for TemporalRepository (not public API).

These helper classes extract focused concerns from the TemporalRepository:
- CacheManager: TTL-based caching with invalidation patterns
- TenantScope: Tenant isolation mode detection and validation
- ModelConverter: Model/dict conversion with Pydantic v1/v2 support
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Generic, List, Optional, Tuple, TypeVar
from uuid import UUID

from ..exceptions import TenantIsolationError

T = TypeVar("T")


@dataclass
class CacheManager(Generic[T]):
    """
    TTL-based cache for repository results.

    Features:
    - Async-safe with lock
    - Pattern-based invalidation
    - Automatic size limiting (LRU eviction)
    - Deep copy to prevent mutation
    """

    enabled: bool = True
    ttl_seconds: int = 300
    max_size: int = 1000

    # Internal state
    _cache: Dict[str, Tuple[T, float]] = field(default_factory=dict, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _metrics_collector: Any = field(default=None, repr=False)

    def set_metrics_collector(self, collector: Any) -> None:
        """Set the metrics collector for cache hit/miss tracking."""
        self._metrics_collector = collector

    def generate_key(
        self,
        model_name: str,
        tenant_id: Optional[UUID],
        operation: str,
        **kwargs,
    ) -> str:
        """
        Generate cache key from operation and parameters.

        Returns a structured key supporting pattern matching:
        Format: {model}:{tenant}:{operation}[:{params}]

        Examples:
        - "Product:org123:list:status=active:page=1"
        - "Product:org123:get:id=abc-123:include_deleted=True"
        """
        parts = [
            model_name,
            str(tenant_id) if tenant_id else "global",
            operation,
        ]

        if kwargs:
            sorted_params = sorted(kwargs.items())
            param_str = ":".join(f"{k}={v}" for k, v in sorted_params)
            parts.append(param_str)

        key = ":".join(parts)

        # Limit key size by hashing params if too long
        if len(key) > 500:
            base_parts = parts[:3]
            param_data = dict(kwargs)
            param_hash = hashlib.sha256(
                json.dumps(param_data, default=str, sort_keys=True).encode()
            ).hexdigest()[:16]

            id_val = kwargs.get("id")
            if id_val:
                key = f"{':'.join(base_parts)}:h{param_hash}:id={id_val}"
            else:
                key = f"{':'.join(base_parts)}:h{param_hash}"

        return key

    async def get(self, cache_key: str) -> Optional[T]:
        """Get value from cache if not expired."""
        if not self.enabled:
            return None

        async with self._lock:
            if cache_key in self._cache:
                value, expiry = self._cache[cache_key]
                if time.time() < expiry:
                    if self._metrics_collector:
                        self._metrics_collector.increment("cache.hits")
                    return copy.deepcopy(value)
                else:
                    del self._cache[cache_key]

        if self._metrics_collector:
            self._metrics_collector.increment("cache.misses")
        return None

    async def set(self, cache_key: str, value: T) -> None:
        """Set value in cache with TTL."""
        if not self.enabled:
            return

        cached_value = copy.deepcopy(value)
        expiry = time.time() + self.ttl_seconds

        async with self._lock:
            self._cache[cache_key] = (cached_value, expiry)

            if len(self._cache) > self.max_size:
                self._evict_expired_and_oldest()

    def _evict_expired_and_oldest(self) -> None:
        """Remove expired entries, then oldest 20% if still too large."""
        now = time.time()
        expired_keys = [k for k, (_, exp) in self._cache.items() if exp < now]
        for k in expired_keys:
            del self._cache[k]

        if len(self._cache) > self.max_size:
            sorted_items = sorted(self._cache.items(), key=lambda x: x[1][1])
            evict_count = len(self._cache) // 5  # 20%
            for k, _ in sorted_items[:evict_count]:
                del self._cache[k]

    async def invalidate(self, pattern: Optional[str] = None) -> None:
        """
        Invalidate cache entries.

        Args:
            pattern: Optional pattern to match keys (None = clear all)
        """
        async with self._lock:
            if pattern is None:
                self._cache.clear()
            else:
                keys_to_remove = [k for k in self._cache if pattern in k]
                for k in keys_to_remove:
                    del self._cache[k]

    async def clear(self) -> None:
        """Clear entire cache."""
        await self.invalidate(None)


@dataclass
class TenantScope:
    """
    Manages tenant isolation modes and validation.

    Modes:
    - strict: Single tenant_id, forces tenant on writes
    - permissive: List of tenant_ids, validates writes are in list
    - admin: No tenant filtering (dangerous, use with caution)
    """

    tenant_id: Optional[UUID] = None
    tenant_ids: Optional[List[UUID]] = None
    tenant_field: str = "tenant_id"

    @property
    def mode(self) -> str:
        """Return current tenant mode: 'strict', 'permissive', or 'admin'."""
        if self.tenant_id is not None:
            return "strict"
        elif self.tenant_ids is not None:
            return "permissive"
        return "admin"

    @property
    def filter_value(self) -> Optional[UUID | List[UUID]]:
        """Return value for tenant filtering in queries."""
        if self.tenant_id is not None:
            return self.tenant_id
        elif self.tenant_ids is not None:
            return self.tenant_ids
        return None

    def validate_for_write(self, data: Dict[str, Any]) -> None:
        """
        Validate and/or set tenant_id for write operations.

        Behavior:
        - strict (single tenant_id): FORCE data[tenant_field] = self.tenant_id
        - permissive (tenant_ids list): VALIDATE data[tenant_field] is in list
        - admin (neither): Allow any tenant_id

        Args:
            data: Model data dict (modified in place for strict mode)

        Raises:
            TenantIsolationError: If permissive validation fails
        """
        if self.tenant_id is not None:
            # STRICT SCOPE: Force tenant_id on the model
            data[self.tenant_field] = self.tenant_id

        elif self.tenant_ids is not None:
            # PERMISSIVE SCOPE: Validate model.tenant_id is in allowed list
            model_tenant = data.get(self.tenant_field)
            if model_tenant is None:
                raise TenantIsolationError(
                    requested_tenant="None",
                    actual_tenant=str(self.tenant_ids),
                    operation="create/update",
                )

            model_tenant_uuid = (
                UUID(model_tenant) if isinstance(model_tenant, str) else model_tenant
            )
            if model_tenant_uuid not in self.tenant_ids:
                raise TenantIsolationError(
                    requested_tenant=str(model_tenant_uuid),
                    actual_tenant=str(self.tenant_ids),
                    operation="create/update",
                )

    def validate_for_read(self, result: Any) -> None:
        """
        Validate tenant isolation for read operations.

        Args:
            result: The fetched model instance

        Raises:
            TenantIsolationError: If result is outside tenant scope
        """
        if result is None:
            return

        result_tenant = getattr(result, self.tenant_field, None)
        if result_tenant is None:
            return

        result_tenant_uuid = (
            UUID(result_tenant) if isinstance(result_tenant, str) else result_tenant
        )

        if self.tenant_id is not None:
            if result_tenant_uuid != self.tenant_id:
                raise TenantIsolationError(
                    requested_tenant=str(self.tenant_id),
                    actual_tenant=str(result_tenant_uuid),
                    operation="get",
                )

        elif self.tenant_ids is not None:
            if result_tenant_uuid not in self.tenant_ids:
                raise TenantIsolationError(
                    requested_tenant=str(self.tenant_ids),
                    actual_tenant=str(result_tenant_uuid),
                    operation="get",
                )


class ModelConverter:
    """
    Converts between model instances and database rows.

    Supports:
    - Pydantic v2 (model_validate, model_dump)
    - Pydantic v1 (parse_obj, dict)
    - Dataclasses (asdict)
    - Plain classes (attribute introspection)
    """

    @staticmethod
    def to_dict(
        model: Any,
        exclude_unset: bool = False,
        exclude_computed: bool = True,
    ) -> Dict[str, Any]:
        """
        Convert model to dictionary for database operations.

        Args:
            model: The model instance to convert
            exclude_unset: If True, only includes fields explicitly set.
                          Use True for UPDATE operations.
            exclude_computed: If True, excludes computed fields (Pydantic v2).

        Returns:
            Dictionary representation of the model
        """
        if hasattr(model, "model_dump"):
            # Pydantic v2
            exclude = set()
            if exclude_computed:
                exclude = set(getattr(model.__class__, "model_computed_fields", {}).keys())
            return model.model_dump(exclude_unset=exclude_unset, exclude=exclude or None)

        elif hasattr(model, "dict"):
            # Pydantic v1
            return model.dict(exclude_unset=exclude_unset)

        elif hasattr(model, "__dataclass_fields__"):
            # Dataclass
            from dataclasses import asdict

            return asdict(model)

        else:
            # Plain class - introspect attributes
            return {
                k: getattr(model, k)
                for k in dir(model)
                if not k.startswith("_") and not callable(getattr(model, k))
            }

    @staticmethod
    def from_dict(model_class: type, data: Dict[str, Any]) -> Any:
        """
        Convert database row to model instance.

        Args:
            model_class: The target model class
            data: Dictionary of field values

        Returns:
            Model instance
        """
        if hasattr(model_class, "model_validate"):
            # Pydantic v2
            return model_class.model_validate(data)

        elif hasattr(model_class, "parse_obj"):
            # Pydantic v1
            return model_class.parse_obj(data)

        elif hasattr(model_class, "__dataclass_fields__"):
            # Dataclass
            return model_class(**data)

        else:
            # Plain class
            return model_class(**data)

    @staticmethod
    def get_table_name(model_class: type) -> str:
        """
        Get fully-qualified table name with schema.

        Returns schema-qualified name (e.g., "public.products").
        """
        if hasattr(model_class, "full_table_name"):
            return model_class.full_table_name()

        schema = getattr(model_class, "__schema__", "public")

        if hasattr(model_class, "table_name"):
            table = model_class.table_name()
        elif hasattr(model_class, "__table_name__"):
            table = model_class.__table_name__
        else:
            table = model_class.__name__.lower() + "s"

        return f"{schema}.{table}"
