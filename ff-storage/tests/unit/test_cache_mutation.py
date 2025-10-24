"""
Unit tests for cache mutation vulnerability fix.

These tests ensure that cached models cannot be mutated, preventing
silent corruption of the cache.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from ff_storage import Field, PydanticModel
from ff_storage.db.adapters import PostgresAdapter
from ff_storage.temporal.repository_base import TemporalRepository


class TestModel(PydanticModel):
    """Test model for cache mutation tests."""

    __table_name__ = "test_models"
    __temporal_strategy__ = "none"

    name: str
    value: int
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class TestCacheMutation:
    """Test that cached models are protected from mutation."""

    @pytest.mark.asyncio
    async def test_get_returns_copy_not_reference(self):
        """Test that get() returns a copy of the cached model, not the reference."""
        # Setup
        model_id = uuid4()
        original_model = TestModel(
            id=model_id,
            name="Original",
            value=100,
            tags=["tag1", "tag2"],
            metadata={"key": "value"},
        )

        # Mock strategy
        strategy = AsyncMock()
        strategy.get.return_value = original_model
        strategy.multi_tenant = False

        # Create repository with caching enabled
        db_pool = AsyncMock()
        repo = TemporalRepository(
            model_class=TestModel,
            db_pool=db_pool,
            strategy=strategy,
            adapter=PostgresAdapter(),
            cache_enabled=True,
            cache_ttl=300,
        )

        # First call - should cache the result
        result1 = await repo.get(model_id)
        assert result1.name == "Original"
        assert strategy.get.call_count == 1

        # Mutate the returned model
        result1.name = "Modified"
        result1.value = 200
        result1.tags.append("tag3")
        result1.metadata["new_key"] = "new_value"

        # Second call - should return cached value
        result2 = await repo.get(model_id)

        # The cached value should NOT be mutated
        assert result2.name == "Original"  # Not "Modified"
        assert result2.value == 100  # Not 200
        assert "tag3" not in result2.tags
        assert "new_key" not in result2.metadata

        # Strategy should still only be called once (cache hit)
        assert strategy.get.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_stores_deep_copy(self):
        """Test that cache stores a deep copy of the model."""
        model_id = uuid4()
        nested_data = {"level1": {"level2": {"items": ["a", "b", "c"]}}}

        original_model = TestModel(
            id=model_id, name="Test", value=42, tags=["original"], metadata=nested_data
        )

        strategy = AsyncMock()
        strategy.get.return_value = original_model
        strategy.multi_tenant = False

        db_pool = AsyncMock()
        repo = TemporalRepository(
            model_class=TestModel,
            db_pool=db_pool,
            strategy=strategy,
            adapter=PostgresAdapter(),
            cache_enabled=True,
            cache_ttl=300,
        )

        # Get and cache the model
        result1 = await repo.get(model_id)

        # Mutate nested structure
        result1.metadata["level1"]["level2"]["items"].append("d")
        result1.metadata["level1"]["new_field"] = "added"

        # Get from cache
        result2 = await repo.get(model_id)

        # Nested structure should not be mutated
        assert "d" not in result2.metadata["level1"]["level2"]["items"]
        assert "new_field" not in result2.metadata["level1"]
        assert result2.metadata["level1"]["level2"]["items"] == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_cache_mutation_with_list_operations(self):
        """Test cache protection against list mutation operations."""
        model_id = uuid4()
        original_model = TestModel(
            id=model_id, name="Test", value=1, tags=["python", "async", "cache"]
        )

        strategy = AsyncMock()
        strategy.get.return_value = original_model
        strategy.multi_tenant = False

        db_pool = AsyncMock()
        repo = TemporalRepository(
            model_class=TestModel,
            db_pool=db_pool,
            strategy=strategy,
            adapter=PostgresAdapter(),
            cache_enabled=True,
        )

        # Get and cache
        result1 = await repo.get(model_id)

        # Try various list mutations
        result1.tags.extend(["new1", "new2"])
        result1.tags.remove("python")
        result1.tags[0] = "modified"
        result1.tags.sort()
        result1.tags.reverse()

        # Get from cache
        result2 = await repo.get(model_id)

        # Original list should be unchanged
        assert result2.tags == ["python", "async", "cache"]

    @pytest.mark.asyncio
    async def test_cache_mutation_with_dict_operations(self):
        """Test cache protection against dict mutation operations."""
        model_id = uuid4()
        original_model = TestModel(
            id=model_id,
            name="Test",
            value=1,
            metadata={"author": "John", "version": 1, "settings": {"debug": False}},
        )

        strategy = AsyncMock()
        strategy.get.return_value = original_model
        strategy.multi_tenant = False

        db_pool = AsyncMock()
        repo = TemporalRepository(
            model_class=TestModel,
            db_pool=db_pool,
            strategy=strategy,
            adapter=PostgresAdapter(),
            cache_enabled=True,
        )

        # Get and cache
        result1 = await repo.get(model_id)

        # Try various dict mutations
        result1.metadata["author"] = "Jane"
        result1.metadata["new_field"] = "added"
        del result1.metadata["version"]
        result1.metadata["settings"]["debug"] = True
        result1.metadata.update({"bulk": "update"})

        # Get from cache
        result2 = await repo.get(model_id)

        # Original dict should be unchanged
        assert result2.metadata == {"author": "John", "version": 1, "settings": {"debug": False}}

    @pytest.mark.asyncio
    async def test_multiple_cache_hits_return_independent_copies(self):
        """Test that multiple cache hits return independent copies."""
        model_id = uuid4()
        original_model = TestModel(id=model_id, name="Shared", value=42, tags=["tag1"])

        strategy = AsyncMock()
        strategy.get.return_value = original_model
        strategy.multi_tenant = False

        db_pool = AsyncMock()
        repo = TemporalRepository(
            model_class=TestModel,
            db_pool=db_pool,
            strategy=strategy,
            adapter=PostgresAdapter(),
            cache_enabled=True,
        )

        # Get multiple times from cache
        result1 = await repo.get(model_id)
        result2 = await repo.get(model_id)
        result3 = await repo.get(model_id)

        # Each should be independent
        result1.name = "Modified1"
        result2.value = 999
        result3.tags.append("new_tag")

        # Get one more time
        result4 = await repo.get(model_id)

        # Should still have original values
        assert result4.name == "Shared"
        assert result4.value == 42
        assert result4.tags == ["tag1"]

        # All results should be different objects
        assert result1 is not result2
        assert result2 is not result3
        assert result3 is not result4

    @pytest.mark.asyncio
    async def test_cache_invalidation_after_update(self):
        """Test that cache is properly invalidated after update operations."""
        model_id = uuid4()
        original_model = TestModel(id=model_id, name="Original", value=100)

        updated_model = TestModel(id=model_id, name="Updated", value=200)

        strategy = AsyncMock()
        strategy.get.side_effect = [original_model, updated_model]
        strategy.update.return_value = updated_model
        strategy.multi_tenant = False

        db_pool = AsyncMock()
        repo = TemporalRepository(
            model_class=TestModel,
            db_pool=db_pool,
            strategy=strategy,
            adapter=PostgresAdapter(),
            cache_enabled=True,
        )

        # Get and cache original
        result1 = await repo.get(model_id)
        assert result1.name == "Original"
        assert strategy.get.call_count == 1

        # Update should invalidate cache
        await repo.update(model_id, updated_model)

        # Next get should fetch updated version
        result2 = await repo.get(model_id)
        assert result2.name == "Updated"
        assert strategy.get.call_count == 2  # Called again after cache invalidation

    @pytest.mark.asyncio
    async def test_get_many_returns_independent_copies(self):
        """Test that get_many returns independent copies for each model."""
        ids = [uuid4() for _ in range(3)]
        models = [
            TestModel(id=ids[0], name="Model1", value=1, tags=["a"]),
            TestModel(id=ids[1], name="Model2", value=2, tags=["b"]),
            TestModel(id=ids[2], name="Model3", value=3, tags=["c"]),
        ]

        from unittest.mock import MagicMock

        strategy = MagicMock()  # Use regular MagicMock instead of AsyncMock
        strategy.multi_tenant = False
        strategy.get_current_version_filters.return_value = []  # Return empty list for no filters

        db_pool = AsyncMock()
        # Mock conn.fetch() to return rows
        rows = [
            {"id": ids[0], "name": "Model1", "value": 1, "tags": ["a"]},
            {"id": ids[1], "name": "Model2", "value": 2, "tags": ["b"]},
            {"id": ids[2], "name": "Model3", "value": 3, "tags": ["c"]},
        ]
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=rows)

        # Create a proper async context manager mock
        acquire_context = MagicMock()
        acquire_context.__aenter__ = AsyncMock(return_value=conn)
        acquire_context.__aexit__ = AsyncMock(return_value=None)
        # Make acquire() a regular (non-async) method that returns the context manager
        db_pool.acquire = MagicMock(return_value=acquire_context)

        repo = TemporalRepository(
            model_class=TestModel,
            db_pool=db_pool,
            strategy=strategy,
            adapter=PostgresAdapter(),
            cache_enabled=True,
        )

        # Mock _dict_to_model
        with patch.object(repo, "_dict_to_model", side_effect=models):
            # Get many - should cache all
            results1 = await repo.get_many(ids)

            # Mutate returned models
            if ids[0] in results1 and results1[ids[0]]:
                results1[ids[0]].name = "Modified1"
                results1[ids[0]].tags.append("x")

            # Get many again - should return cached copies
            results2 = await repo.get_many(ids)

            # Cached values should not be mutated
            if ids[0] in results2 and results2[ids[0]]:
                assert results2[ids[0]].name == "Model1"  # Not "Modified1"
                assert results2[ids[0]].tags == ["a"]  # Not ["a", "x"]

    @pytest.mark.asyncio
    async def test_cache_disabled_no_protection_needed(self):
        """Test that when cache is disabled, no copy overhead is incurred."""
        model_id = uuid4()
        original_model = TestModel(id=model_id, name="NoCacheTest", value=42)

        strategy = AsyncMock()
        # Return same object twice
        strategy.get.return_value = original_model
        strategy.multi_tenant = False

        db_pool = AsyncMock()
        repo = TemporalRepository(
            model_class=TestModel,
            db_pool=db_pool,
            strategy=strategy,
            adapter=PostgresAdapter(),
            cache_enabled=False,  # Cache disabled
        )

        # Get twice
        result1 = await repo.get(model_id)
        result2 = await repo.get(model_id)

        # With cache disabled, strategy should be called twice
        assert strategy.get.call_count == 2

        # Both should be the same object (no copying when cache disabled)
        assert result1 is original_model
        assert result2 is original_model


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
