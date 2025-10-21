"""
Integration tests for temporal strategies with real database operations.

Tests the complete flow of temporal operations including:
- All three temporal strategies (none, copy_on_change, scd2)
- Multi-tenant isolation
- Soft delete operations
- Audit history
- Time travel queries
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import AsyncMock

import pytest
from ff_storage.exceptions import TemporalStrategyError, TenantIsolationError
from ff_storage.pydantic_support.base import PydanticModel
from ff_storage.temporal.enums import TemporalStrategyType
from ff_storage.temporal.registry import get_strategy
from ff_storage.temporal.repository_base import TemporalRepository


def create_async_pool_mock(mock_conn=None, side_effect=None):
    """
    Helper to create a properly mocked async pool with context manager support.

    Args:
        mock_conn: Optional mock connection to return from __aenter__
        side_effect: Optional exception to raise when entering context

    Returns:
        AsyncMock configured as async context manager
    """
    from unittest.mock import Mock

    mock_pool = AsyncMock()

    # Always set up async context manager protocol
    mock_acquire = AsyncMock()

    if side_effect:
        # For exceptions, raise them when entering the context manager
        mock_acquire.__aenter__ = AsyncMock(side_effect=side_effect)
        mock_acquire.__aexit__ = AsyncMock(return_value=None)
    else:
        # Normal case: return connection from __aenter__
        mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn or AsyncMock())
        mock_acquire.__aexit__ = AsyncMock(return_value=None)

    # IMPORTANT: Use Mock (not AsyncMock) for acquire() so it returns the context manager directly
    # without wrapping it in a coroutine
    mock_pool.acquire = Mock(return_value=mock_acquire)

    return mock_pool


# Test models for different strategies
class ProductNone(PydanticModel):
    """Product model with no temporal strategy."""

    __table_name__ = "products_none"
    __temporal_strategy__ = "none"
    __multi_tenant__ = True

    name: str
    price: float
    description: Optional[str] = None


class ProductCopyOnChange(PydanticModel):
    """Product model with copy_on_change temporal strategy."""

    __table_name__ = "products_copy"
    __temporal_strategy__ = "copy_on_change"
    __multi_tenant__ = True

    name: str
    price: float
    description: Optional[str] = None


class ProductSCD2(PydanticModel):
    """Product model with SCD2 temporal strategy."""

    __table_name__ = "products_scd2"
    __temporal_strategy__ = "scd2"
    __multi_tenant__ = True

    name: str
    price: float
    description: Optional[str] = None


@pytest.fixture
async def mock_db_pool():
    """Mock database pool for testing."""
    # Create mock connection with required methods
    conn = AsyncMock()
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    conn.transaction = AsyncMock()

    # Create properly configured pool mock
    pool = create_async_pool_mock(mock_conn=conn)

    # Configure pool-level methods for backward compatibility
    pool.fetch_one = AsyncMock()
    pool.fetch_all = AsyncMock()
    pool.execute = AsyncMock()

    return pool


@pytest.fixture
def tenant_id():
    """Test tenant ID."""
    return uuid.uuid4()


@pytest.fixture
def user_id():
    """Test user ID."""
    return uuid.uuid4()


class TestTemporalStrategies:
    """Test all temporal strategies."""

    @pytest.mark.asyncio
    async def test_none_strategy_crud(self, mock_db_pool, tenant_id, user_id):
        """Test CRUD operations with none strategy."""
        # Setup
        strategy = get_strategy(TemporalStrategyType.NONE, ProductNone)
        repo = TemporalRepository(
            ProductNone,
            mock_db_pool,
            strategy,
            tenant_id=tenant_id,
            cache_enabled=False,  # Disable cache for testing
        )

        # Mock successful create
        created_id = uuid.uuid4()
        mock_db_pool.fetch_one.return_value = {
            "id": created_id,
            "tenant_id": tenant_id,
            "name": "Test Product",
            "price": 99.99,
            "description": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "created_by": user_id,
            "updated_by": user_id,
        }

        # Test create
        product = ProductNone(name="Test Product", price=99.99)
        created = await repo.create(product, user_id=user_id)

        assert created.id == created_id
        assert created.name == "Test Product"
        assert created.price == 99.99

        # Verify query was executed with tenant_id
        mock_db_pool.fetch_one.assert_called_once()
        call_args = mock_db_pool.fetch_one.call_args
        assert tenant_id in call_args[0]  # Check tenant_id is in query args

    @pytest.mark.asyncio
    async def test_copy_on_change_audit_trail(self, mock_db_pool, tenant_id, user_id):
        """Test copy_on_change strategy creates audit trail."""
        # Setup
        strategy = get_strategy(TemporalStrategyType.COPY_ON_CHANGE, ProductCopyOnChange)
        repo = TemporalRepository(
            ProductCopyOnChange, mock_db_pool, strategy, tenant_id=tenant_id, cache_enabled=False
        )

        # Mock update that triggers audit entry
        product_id = uuid.uuid4()
        mock_db_pool.fetch_one.side_effect = [
            # First call: get current record
            {
                "id": product_id,
                "tenant_id": tenant_id,
                "name": "Original Product",
                "price": 50.00,
                "updated_at": datetime.now(timezone.utc) - timedelta(hours=1),
            },
            # Second call: return updated record
            {
                "id": product_id,
                "tenant_id": tenant_id,
                "name": "Updated Product",
                "price": 75.00,
                "updated_at": datetime.now(timezone.utc),
            },
        ]

        # Mock audit table insert
        mock_db_pool.execute.return_value = None

        # Test update
        updated_product = ProductCopyOnChange(id=product_id, name="Updated Product", price=75.00)
        result = await repo.update(product_id, updated_product, user_id=user_id)
        assert result is not None  # Verify update returns a result

        # Verify audit entry was created
        assert mock_db_pool.execute.called
        execute_call = mock_db_pool.execute.call_args[0][0]
        assert "products_copy_audit" in execute_call  # Check audit table is used

    @pytest.mark.asyncio
    async def test_scd2_version_history(self, mock_db_pool, tenant_id, user_id):
        """Test SCD2 strategy creates version history."""
        # Setup
        strategy = get_strategy(TemporalStrategyType.SCD2, ProductSCD2)
        repo = TemporalRepository(
            ProductSCD2, mock_db_pool, strategy, tenant_id=tenant_id, cache_enabled=False
        )

        product_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        # Mock version history
        mock_db_pool.fetch_all.return_value = [
            # Version 1
            {
                "id": product_id,
                "tenant_id": tenant_id,
                "name": "Product V1",
                "price": 10.00,
                "version": 1,
                "valid_from": now - timedelta(days=10),
                "valid_to": now - timedelta(days=5),
            },
            # Version 2
            {
                "id": product_id,
                "tenant_id": tenant_id,
                "name": "Product V2",
                "price": 20.00,
                "version": 2,
                "valid_from": now - timedelta(days=5),
                "valid_to": None,  # Current version
            },
        ]

        # Test get version history
        history = await repo.get_version_history(product_id)

        assert len(history) == 2
        assert history[0].version == 1
        assert history[0].name == "Product V1"
        assert history[1].version == 2
        assert history[1].valid_to is None  # Current version

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, mock_db_pool, user_id):
        """Test tenant isolation is enforced."""
        # Setup
        tenant1 = uuid.uuid4()
        tenant2 = uuid.uuid4()
        product_id = uuid.uuid4()

        strategy = get_strategy(TemporalStrategyType.NONE, ProductNone)
        repo1 = TemporalRepository(
            ProductNone, mock_db_pool, strategy, tenant_id=tenant1, cache_enabled=False
        )

        # Mock get returning wrong tenant
        mock_db_pool.fetch_one.return_value = {
            "id": product_id,
            "tenant_id": tenant2,  # Different tenant!
            "name": "Product",
            "price": 50.00,
        }

        # Should raise TenantIsolationError
        with pytest.raises(TenantIsolationError) as exc_info:
            await repo1.get(product_id)

        assert str(tenant1) in str(exc_info.value)
        assert str(tenant2) in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_soft_delete_and_restore(self, mock_db_pool, tenant_id, user_id):
        """Test soft delete and restore operations."""
        # Setup
        strategy = get_strategy(TemporalStrategyType.NONE, ProductNone)
        repo = TemporalRepository(
            ProductNone, mock_db_pool, strategy, tenant_id=tenant_id, cache_enabled=False
        )

        product_id = uuid.uuid4()

        # Mock soft delete
        mock_db_pool.execute.return_value = "UPDATE 1"

        # Test delete
        result = await repo.delete(product_id, user_id=user_id)
        assert result is True

        # Verify UPDATE with deleted_at was executed
        execute_call = mock_db_pool.execute.call_args[0][0]
        assert "deleted_at" in execute_call
        assert "UPDATE" in execute_call

        # Mock restore
        mock_db_pool.fetch_one.return_value = {
            "id": product_id,
            "tenant_id": tenant_id,
            "name": "Restored Product",
            "price": 50.00,
            "deleted_at": None,
        }

        # Test restore
        restored = await repo.restore(product_id)
        assert restored.deleted_at is None

    @pytest.mark.asyncio
    async def test_caching_behavior(self, mock_db_pool, tenant_id, user_id):
        """Test caching reduces database calls."""
        # Setup with cache enabled
        strategy = get_strategy(TemporalStrategyType.NONE, ProductNone)
        repo = TemporalRepository(
            ProductNone,
            mock_db_pool,
            strategy,
            tenant_id=tenant_id,
            cache_enabled=True,
            cache_ttl=60,  # 1 minute cache
        )

        product_id = uuid.uuid4()
        mock_db_pool.fetch_one.return_value = {
            "id": product_id,
            "tenant_id": tenant_id,
            "name": "Cached Product",
            "price": 30.00,
        }

        # First get - should hit database
        product1 = await repo.get(product_id)
        assert product1.name == "Cached Product"
        assert mock_db_pool.fetch_one.call_count == 1

        # Second get - should use cache
        product2 = await repo.get(product_id)
        assert product2.name == "Cached Product"
        assert mock_db_pool.fetch_one.call_count == 1  # No additional call

        # Invalidate cache
        await repo.invalidate_cache()

        # Third get - should hit database again
        product3 = await repo.get(product_id)
        assert product3.name == "Cached Product"
        assert mock_db_pool.fetch_one.call_count == 2

    @pytest.mark.asyncio
    async def test_batch_operations(self, mock_db_pool, tenant_id, user_id):
        """Test batch create and get operations."""
        # Setup
        strategy = get_strategy(TemporalStrategyType.NONE, ProductNone)
        repo = TemporalRepository(
            ProductNone, mock_db_pool, strategy, tenant_id=tenant_id, cache_enabled=False
        )

        # Mock batch create
        created_ids = [uuid.uuid4() for _ in range(3)]
        mock_db_pool.fetch_one.side_effect = [
            {"id": id, "name": f"Product {i}", "price": i * 10.0, "tenant_id": tenant_id}
            for i, id in enumerate(created_ids)
        ]

        # Test batch create
        products = [ProductNone(name=f"Product {i}", price=i * 10.0) for i in range(3)]
        created = await repo.create_many(products, user_id=user_id)

        assert len(created) == 3
        for i, product in enumerate(created):
            assert product.name == f"Product {i}"
            assert product.price == i * 10.0

        # Reset mock for batch get
        mock_db_pool.fetch_all.return_value = [
            {"id": id, "name": f"Product {i}", "price": i * 10.0, "tenant_id": tenant_id}
            for i, id in enumerate(created_ids)
        ]

        # Test batch get
        result_map = await repo.get_many(created_ids)

        assert len(result_map) == 3
        for id in created_ids:
            assert id in result_map
            assert result_map[id] is not None

    @pytest.mark.asyncio
    async def test_error_handling_with_retry(self, mock_db_pool, tenant_id, user_id):
        """Test error handling and retry logic."""
        # Setup
        strategy = get_strategy(TemporalStrategyType.NONE, ProductNone)
        repo = TemporalRepository(
            ProductNone,
            mock_db_pool,
            strategy,
            tenant_id=tenant_id,
            cache_enabled=False,
            max_retries=3,
        )

        # Mock transient failure then success
        mock_db_pool.fetch_one.side_effect = [
            asyncio.TimeoutError("Connection timeout"),
            asyncio.TimeoutError("Connection timeout"),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "name": "Success after retry",
                "price": 99.99,
            },
        ]

        # Should succeed after retries
        product = ProductNone(name="Test", price=99.99)
        created = await repo.create(product, user_id=user_id)

        assert created.name == "Success after retry"
        assert mock_db_pool.fetch_one.call_count == 3  # 2 failures + 1 success

    @pytest.mark.asyncio
    async def test_concurrent_update_detection(self, mock_db_pool, tenant_id, user_id):
        """Test detection of concurrent updates."""
        # Setup
        strategy = get_strategy(TemporalStrategyType.COPY_ON_CHANGE, ProductCopyOnChange)
        repo = TemporalRepository(
            ProductCopyOnChange, mock_db_pool, strategy, tenant_id=tenant_id, cache_enabled=False
        )

        product_id = uuid.uuid4()
        original_updated = datetime.now(timezone.utc) - timedelta(hours=1)
        new_updated = datetime.now(timezone.utc)

        # Mock concurrent modification
        mock_db_pool.fetch_one.side_effect = [
            # First call: get current record with newer updated_at
            {
                "id": product_id,
                "tenant_id": tenant_id,
                "name": "Concurrently Modified",
                "price": 60.00,
                "updated_at": new_updated,  # Newer than expected!
            }
        ]

        # Update with old version
        product = ProductCopyOnChange(
            id=product_id,
            name="My Update",
            price=70.00,
            updated_at=original_updated,  # Old timestamp
        )

        # Should detect concurrent modification
        with pytest.raises(TemporalStrategyError) as exc_info:
            await repo.update(product_id, product, user_id=user_id)

        # Error message should indicate the issue
        assert "update" in str(exc_info.value).lower()
