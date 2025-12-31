"""
Unit tests for temporal helpers module.

Tests cover:
- CacheManager: TTL-based caching with invalidation
- TenantScope: Tenant isolation mode detection and validation
- ModelConverter: Model/dict conversion with Pydantic v2 support
"""

import asyncio
from dataclasses import dataclass as py_dataclass
from typing import Optional
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, computed_field

from ff_storage.exceptions import TenantIsolationError
from ff_storage.temporal.helpers import CacheManager, ModelConverter, TenantScope


# ============================================================================
# CacheManager Tests
# ============================================================================


class TestCacheManagerBasics:
    """Tests for CacheManager basic operations."""

    @pytest.fixture
    def cache(self) -> CacheManager:
        """Create a fresh CacheManager for each test."""
        return CacheManager(enabled=True, ttl_seconds=60, max_size=100)

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache: CacheManager):
        """Should store and retrieve values."""
        await cache.set("key1", {"data": "value1"})
        result = await cache.get("key1")
        assert result == {"data": "value1"}

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, cache: CacheManager):
        """Should return None for missing keys."""
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_disabled_cache_returns_none(self):
        """Disabled cache should always return None."""
        cache = CacheManager(enabled=False)
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_disabled_cache_set_is_noop(self):
        """Disabled cache should not store values."""
        cache = CacheManager(enabled=False)
        await cache.set("key1", "value1")
        # Enable cache and verify nothing was stored
        cache.enabled = True
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_deep_copy_on_get(self, cache: CacheManager):
        """Get should return deep copies to prevent mutation."""
        original = {"nested": {"value": 1}}
        await cache.set("key", original)

        result = await cache.get("key")
        result["nested"]["value"] = 999

        # Original cached value should be unchanged
        second_result = await cache.get("key")
        assert second_result["nested"]["value"] == 1

    @pytest.mark.asyncio
    async def test_deep_copy_on_set(self, cache: CacheManager):
        """Set should store deep copies to prevent mutation."""
        original = {"nested": {"value": 1}}
        await cache.set("key", original)

        # Mutate original after caching
        original["nested"]["value"] = 999

        # Cached value should be unchanged
        result = await cache.get("key")
        assert result["nested"]["value"] == 1


class TestCacheManagerTTL:
    """Tests for CacheManager TTL (time-to-live) behavior."""

    @pytest.mark.asyncio
    async def test_ttl_expiration(self):
        """Expired entries should return None."""
        cache = CacheManager(enabled=True, ttl_seconds=1)
        await cache.set("key", "value")

        # Should exist immediately
        assert await cache.get("key") == "value"

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should be expired
        result = await cache.get("key")
        assert result is None

    @pytest.mark.asyncio
    async def test_ttl_cleanup_on_get(self):
        """Expired entries should be removed on access."""
        cache = CacheManager(enabled=True, ttl_seconds=1)
        await cache.set("key", "value")

        await asyncio.sleep(1.1)

        # Access should clean up
        await cache.get("key")

        # Verify entry was removed
        assert "key" not in cache._cache


class TestCacheManagerKeyGeneration:
    """Tests for CacheManager key generation."""

    def test_generate_key_basic(self):
        """Should generate structured key."""
        cache = CacheManager()
        tenant_id = UUID("12345678-1234-5678-1234-567812345678")
        key = cache.generate_key("Product", tenant_id, "list")
        assert key == "Product:12345678-1234-5678-1234-567812345678:list"

    def test_generate_key_with_params(self):
        """Should include sorted params in key."""
        cache = CacheManager()
        tenant_id = UUID("12345678-1234-5678-1234-567812345678")
        key = cache.generate_key("Product", tenant_id, "list", status="active", page=1)
        assert key == "Product:12345678-1234-5678-1234-567812345678:list:page=1:status=active"

    def test_generate_key_global_tenant(self):
        """Should use 'global' for None tenant_id."""
        cache = CacheManager()
        key = cache.generate_key("Product", None, "list")
        assert key == "Product:global:list"

    def test_generate_key_long_params_hashed(self):
        """Long keys should be hashed for stability."""
        cache = CacheManager()
        tenant_id = UUID("12345678-1234-5678-1234-567812345678")

        # Create params that would exceed 500 chars
        long_value = "x" * 500
        key = cache.generate_key("Product", tenant_id, "list", long_param=long_value)

        # Should be shortened with hash
        assert len(key) < 500
        assert ":h" in key  # Hash prefix indicator

    def test_generate_key_long_params_with_id(self):
        """Long keys with id should preserve id in key."""
        cache = CacheManager()
        tenant_id = UUID("12345678-1234-5678-1234-567812345678")

        long_value = "x" * 500
        record_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        key = cache.generate_key("Product", tenant_id, "get", id=record_id, extra=long_value)

        assert f"id={record_id}" in key


class TestCacheManagerInvalidation:
    """Tests for CacheManager invalidation."""

    @pytest.fixture
    def cache(self) -> CacheManager:
        return CacheManager(enabled=True, ttl_seconds=300)

    @pytest.mark.asyncio
    async def test_invalidate_all(self, cache: CacheManager):
        """Invalidate with None should clear all entries."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        await cache.invalidate(None)

        assert await cache.get("key1") is None
        assert await cache.get("key2") is None
        assert await cache.get("key3") is None

    @pytest.mark.asyncio
    async def test_invalidate_pattern(self, cache: CacheManager):
        """Invalidate with pattern should clear matching entries."""
        await cache.set("Product:tenant1:list", "value1")
        await cache.set("Product:tenant1:get", "value2")
        await cache.set("Order:tenant1:list", "value3")

        await cache.invalidate("Product")

        assert await cache.get("Product:tenant1:list") is None
        assert await cache.get("Product:tenant1:get") is None
        # Non-matching should remain
        assert await cache.get("Order:tenant1:list") == "value3"

    @pytest.mark.asyncio
    async def test_clear_alias(self, cache: CacheManager):
        """Clear should be an alias for invalidate(None)."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        await cache.clear()

        assert await cache.get("key1") is None
        assert await cache.get("key2") is None


class TestCacheManagerEviction:
    """Tests for CacheManager LRU eviction."""

    @pytest.mark.asyncio
    async def test_eviction_when_over_max_size(self):
        """Should evict oldest entries when exceeding max_size."""
        cache = CacheManager(enabled=True, ttl_seconds=300, max_size=5)

        # Add 6 entries (exceeds max of 5)
        for i in range(6):
            await cache.set(f"key{i}", f"value{i}")
            await asyncio.sleep(0.01)  # Ensure different timestamps

        # Should have evicted at least 1 entry (20% = 1 of 6)
        assert len(cache._cache) <= 5

    @pytest.mark.asyncio
    async def test_eviction_removes_oldest(self):
        """Eviction should remove oldest entries first."""
        cache = CacheManager(enabled=True, ttl_seconds=300, max_size=3)

        await cache.set("oldest", "value0")
        await asyncio.sleep(0.05)
        await cache.set("middle", "value1")
        await asyncio.sleep(0.05)
        await cache.set("newest", "value2")
        await asyncio.sleep(0.05)

        # Add one more to trigger eviction
        await cache.set("extra", "value3")

        # Newest entries should still exist
        assert await cache.get("newest") is not None
        assert await cache.get("extra") is not None


class TestCacheManagerMetrics:
    """Tests for CacheManager metrics collection."""

    @pytest.mark.asyncio
    async def test_metrics_hit(self):
        """Should increment cache.hits on hit."""

        class MockMetrics:
            def __init__(self):
                self.calls = []

            def increment(self, metric: str):
                self.calls.append(metric)

        cache = CacheManager(enabled=True, ttl_seconds=300)
        metrics = MockMetrics()
        cache.set_metrics_collector(metrics)

        await cache.set("key", "value")
        await cache.get("key")

        assert "cache.hits" in metrics.calls

    @pytest.mark.asyncio
    async def test_metrics_miss(self):
        """Should increment cache.misses on miss."""

        class MockMetrics:
            def __init__(self):
                self.calls = []

            def increment(self, metric: str):
                self.calls.append(metric)

        cache = CacheManager(enabled=True, ttl_seconds=300)
        metrics = MockMetrics()
        cache.set_metrics_collector(metrics)

        await cache.get("nonexistent")

        assert "cache.misses" in metrics.calls


# ============================================================================
# TenantScope Tests
# ============================================================================


class TestTenantScopeMode:
    """Tests for TenantScope mode detection."""

    def test_strict_mode(self):
        """Single tenant_id should be strict mode."""
        scope = TenantScope(tenant_id=uuid4())
        assert scope.mode == "strict"

    def test_permissive_mode(self):
        """List of tenant_ids should be permissive mode."""
        scope = TenantScope(tenant_ids=[uuid4(), uuid4()])
        assert scope.mode == "permissive"

    def test_admin_mode(self):
        """Neither tenant_id nor tenant_ids should be admin mode."""
        scope = TenantScope()
        assert scope.mode == "admin"

    def test_strict_takes_precedence(self):
        """tenant_id should take precedence over tenant_ids."""
        tid = uuid4()
        scope = TenantScope(tenant_id=tid, tenant_ids=[uuid4()])
        assert scope.mode == "strict"


class TestTenantScopeFilterValue:
    """Tests for TenantScope filter_value property."""

    def test_strict_filter_value(self):
        """Strict mode should return single tenant_id."""
        tid = uuid4()
        scope = TenantScope(tenant_id=tid)
        assert scope.filter_value == tid

    def test_permissive_filter_value(self):
        """Permissive mode should return list of tenant_ids."""
        tids = [uuid4(), uuid4()]
        scope = TenantScope(tenant_ids=tids)
        assert scope.filter_value == tids

    def test_admin_filter_value(self):
        """Admin mode should return None."""
        scope = TenantScope()
        assert scope.filter_value is None


class TestTenantScopeValidateForWrite:
    """Tests for TenantScope.validate_for_write."""

    def test_strict_forces_tenant_id(self):
        """Strict mode should force tenant_id on data."""
        tid = uuid4()
        scope = TenantScope(tenant_id=tid)
        data = {"name": "Test"}

        scope.validate_for_write(data)

        assert data["tenant_id"] == tid

    def test_strict_overwrites_existing_tenant_id(self):
        """Strict mode should overwrite existing tenant_id."""
        tid = uuid4()
        other_tid = uuid4()
        scope = TenantScope(tenant_id=tid)
        data = {"name": "Test", "tenant_id": other_tid}

        scope.validate_for_write(data)

        assert data["tenant_id"] == tid

    def test_permissive_allows_valid_tenant(self):
        """Permissive mode should allow valid tenant_id."""
        tids = [uuid4(), uuid4()]
        scope = TenantScope(tenant_ids=tids)
        data = {"name": "Test", "tenant_id": tids[0]}

        # Should not raise
        scope.validate_for_write(data)

    def test_permissive_rejects_invalid_tenant(self):
        """Permissive mode should reject tenant_id not in list."""
        tids = [uuid4(), uuid4()]
        invalid_tid = uuid4()
        scope = TenantScope(tenant_ids=tids)
        data = {"name": "Test", "tenant_id": invalid_tid}

        with pytest.raises(TenantIsolationError):
            scope.validate_for_write(data)

    def test_permissive_rejects_missing_tenant(self):
        """Permissive mode should reject missing tenant_id."""
        tids = [uuid4(), uuid4()]
        scope = TenantScope(tenant_ids=tids)
        data = {"name": "Test"}

        with pytest.raises(TenantIsolationError):
            scope.validate_for_write(data)

    def test_permissive_accepts_string_uuid(self):
        """Permissive mode should accept string UUID tenant_id."""
        tid = uuid4()
        scope = TenantScope(tenant_ids=[tid])
        data = {"name": "Test", "tenant_id": str(tid)}

        # Should not raise
        scope.validate_for_write(data)

    def test_admin_allows_any_tenant(self):
        """Admin mode should allow any tenant_id."""
        scope = TenantScope()
        data = {"name": "Test", "tenant_id": uuid4()}

        # Should not raise
        scope.validate_for_write(data)

    def test_admin_allows_missing_tenant(self):
        """Admin mode should allow missing tenant_id."""
        scope = TenantScope()
        data = {"name": "Test"}

        # Should not raise
        scope.validate_for_write(data)

    def test_custom_tenant_field(self):
        """Should use custom tenant field name."""
        tid = uuid4()
        scope = TenantScope(tenant_id=tid, tenant_field="org_id")
        data = {"name": "Test"}

        scope.validate_for_write(data)

        assert data["org_id"] == tid
        assert "tenant_id" not in data


class TestTenantScopeValidateForRead:
    """Tests for TenantScope.validate_for_read."""

    def test_strict_allows_matching_tenant(self):
        """Strict mode should allow matching tenant."""
        tid = uuid4()
        scope = TenantScope(tenant_id=tid)

        class Result:
            tenant_id = tid

        # Should not raise
        scope.validate_for_read(Result())

    def test_strict_rejects_mismatched_tenant(self):
        """Strict mode should reject mismatched tenant."""
        tid = uuid4()
        other_tid = uuid4()
        scope = TenantScope(tenant_id=tid)

        class Result:
            tenant_id = other_tid

        with pytest.raises(TenantIsolationError):
            scope.validate_for_read(Result())

    def test_permissive_allows_listed_tenant(self):
        """Permissive mode should allow tenant in list."""
        tids = [uuid4(), uuid4()]
        scope = TenantScope(tenant_ids=tids)

        class Result:
            tenant_id = tids[1]

        # Should not raise
        scope.validate_for_read(Result())

    def test_permissive_rejects_unlisted_tenant(self):
        """Permissive mode should reject tenant not in list."""
        tids = [uuid4(), uuid4()]
        other_tid = uuid4()
        scope = TenantScope(tenant_ids=tids)

        class Result:
            tenant_id = other_tid

        with pytest.raises(TenantIsolationError):
            scope.validate_for_read(Result())

    def test_admin_allows_any_tenant(self):
        """Admin mode should allow any tenant."""
        scope = TenantScope()

        class Result:
            tenant_id = uuid4()

        # Should not raise
        scope.validate_for_read(Result())

    def test_none_result_is_allowed(self):
        """None result should be allowed."""
        tid = uuid4()
        scope = TenantScope(tenant_id=tid)

        # Should not raise
        scope.validate_for_read(None)

    def test_result_without_tenant_field(self):
        """Result without tenant field should be allowed."""
        tid = uuid4()
        scope = TenantScope(tenant_id=tid)

        class Result:
            name = "test"

        # Should not raise
        scope.validate_for_read(Result())

    def test_custom_tenant_field_for_read(self):
        """Should use custom tenant field name for reads."""
        tid = uuid4()
        other_tid = uuid4()
        scope = TenantScope(tenant_id=tid, tenant_field="org_id")

        class Result:
            org_id = other_tid
            tenant_id = tid  # Wrong field should be ignored

        with pytest.raises(TenantIsolationError):
            scope.validate_for_read(Result())


# ============================================================================
# ModelConverter Tests
# ============================================================================


class PydanticV2Model(BaseModel):
    """Test model using Pydantic v2."""

    id: UUID
    name: str
    value: Optional[int] = None

    @computed_field
    @property
    def computed_prop(self) -> str:
        return f"computed_{self.name}"


@py_dataclass
class DataclassModel:
    """Test model using Python dataclass."""

    id: UUID
    name: str
    value: Optional[int] = None


class PlainClass:
    """Test model using plain Python class."""

    def __init__(self, id: UUID, name: str, value: Optional[int] = None):
        self.id = id
        self.name = name
        self.value = value


class TestModelConverterToDict:
    """Tests for ModelConverter.to_dict."""

    def test_pydantic_v2_to_dict(self):
        """Should convert Pydantic v2 model to dict."""
        model_id = uuid4()
        model = PydanticV2Model(id=model_id, name="test", value=42)

        result = ModelConverter.to_dict(model)

        assert result["id"] == model_id
        assert result["name"] == "test"
        assert result["value"] == 42

    def test_pydantic_v2_excludes_computed_by_default(self):
        """Should exclude computed fields by default."""
        model = PydanticV2Model(id=uuid4(), name="test")

        result = ModelConverter.to_dict(model)

        assert "computed_prop" not in result

    def test_pydantic_v2_includes_computed_when_requested(self):
        """Should include computed fields when exclude_computed=False."""
        model = PydanticV2Model(id=uuid4(), name="test")

        result = ModelConverter.to_dict(model, exclude_computed=False)

        assert "computed_prop" in result
        assert result["computed_prop"] == "computed_test"

    def test_pydantic_v2_exclude_unset(self):
        """Should exclude unset fields when exclude_unset=True."""
        model = PydanticV2Model(id=uuid4(), name="test")

        result = ModelConverter.to_dict(model, exclude_unset=True)

        assert "id" in result
        assert "name" in result
        assert "value" not in result  # Not explicitly set

    def test_dataclass_to_dict(self):
        """Should convert dataclass to dict."""
        model_id = uuid4()
        model = DataclassModel(id=model_id, name="test", value=42)

        result = ModelConverter.to_dict(model)

        assert result["id"] == model_id
        assert result["name"] == "test"
        assert result["value"] == 42

    def test_plain_class_to_dict(self):
        """Should convert plain class to dict."""
        model_id = uuid4()
        model = PlainClass(id=model_id, name="test", value=42)

        result = ModelConverter.to_dict(model)

        assert result["id"] == model_id
        assert result["name"] == "test"
        assert result["value"] == 42


class TestModelConverterFromDict:
    """Tests for ModelConverter.from_dict."""

    def test_pydantic_v2_from_dict(self):
        """Should convert dict to Pydantic v2 model."""
        model_id = uuid4()
        data = {"id": model_id, "name": "test", "value": 42}

        result = ModelConverter.from_dict(PydanticV2Model, data)

        assert isinstance(result, PydanticV2Model)
        assert result.id == model_id
        assert result.name == "test"
        assert result.value == 42

    def test_dataclass_from_dict(self):
        """Should convert dict to dataclass."""
        model_id = uuid4()
        data = {"id": model_id, "name": "test", "value": 42}

        result = ModelConverter.from_dict(DataclassModel, data)

        assert isinstance(result, DataclassModel)
        assert result.id == model_id
        assert result.name == "test"
        assert result.value == 42

    def test_plain_class_from_dict(self):
        """Should convert dict to plain class."""
        model_id = uuid4()
        data = {"id": model_id, "name": "test", "value": 42}

        result = ModelConverter.from_dict(PlainClass, data)

        assert isinstance(result, PlainClass)
        assert result.id == model_id
        assert result.name == "test"
        assert result.value == 42


class TestModelConverterGetTableName:
    """Tests for ModelConverter.get_table_name."""

    def test_full_table_name_method(self):
        """Should use full_table_name() if available."""

        class ModelWithFullTableName:
            @staticmethod
            def full_table_name() -> str:
                return "custom_schema.custom_table"

        result = ModelConverter.get_table_name(ModelWithFullTableName)
        assert result == "custom_schema.custom_table"

    def test_table_name_method(self):
        """Should use table_name() method if available."""

        class ModelWithTableNameMethod:
            __schema__ = "myschema"

            @staticmethod
            def table_name() -> str:
                return "my_table"

        result = ModelConverter.get_table_name(ModelWithTableNameMethod)
        assert result == "myschema.my_table"

    def test_table_name_attribute(self):
        """Should use __table_name__ attribute if available."""

        class ModelWithTableNameAttr:
            __schema__ = "myschema"
            __table_name__ = "my_table"

        result = ModelConverter.get_table_name(ModelWithTableNameAttr)
        assert result == "myschema.my_table"

    def test_default_table_name(self):
        """Should derive table name from class name if not specified."""

        class Product:
            pass

        result = ModelConverter.get_table_name(Product)
        assert result == "public.products"

    def test_default_schema(self):
        """Should use 'public' as default schema."""

        class Order:
            __table_name__ = "orders"

        result = ModelConverter.get_table_name(Order)
        assert result == "public.orders"
