"""
Integration tests for temporal strategies.

Tests all three temporal strategies (none, copy_on_change, scd2) with:
- CRUD operations
- Soft delete
- Multi-tenant isolation
- Audit trails
- Time travel
"""

import pytest
import asyncio
from datetime import datetime, timezone
from uuid import uuid4
from decimal import Decimal

from ff_storage import PydanticModel, Field, PydanticRepository


# Test models for each strategy


class ProductNone(PydanticModel):
    """Product with no temporal tracking."""

    __table_name__ = "products_none"
    __temporal_strategy__ = "none"
    __soft_delete__ = True
    __multi_tenant__ = True

    name: str = Field(max_length=255)
    price: Decimal = Field(decimal_places=2)
    status: str = Field(default="active")


class ProductCopyOnChange(PydanticModel):
    """Product with field-level audit trail."""

    __table_name__ = "products_coc"
    __temporal_strategy__ = "copy_on_change"
    __soft_delete__ = True
    __multi_tenant__ = True

    name: str = Field(max_length=255)
    price: Decimal = Field(decimal_places=2)
    status: str = Field(default="active")


class ProductSCD2(PydanticModel):
    """Product with immutable versions (SCD2)."""

    __table_name__ = "products_scd2"
    __temporal_strategy__ = "scd2"
    __soft_delete__ = True
    __multi_tenant__ = True

    name: str = Field(max_length=255)
    price: Decimal = Field(decimal_places=2)
    status: str = Field(default="active")


@pytest.fixture
async def db_pool():
    """Mock database pool for testing."""
    import asyncpg

    # Connect to test database
    pool = await asyncpg.create_pool(
        host="localhost",
        port=5432,
        database="test_temporal",
        user="test_user",
        password="test_pass",
        min_size=2,
        max_size=10,
    )
    yield pool
    await pool.close()


@pytest.fixture
async def setup_tables(db_pool):
    """Create test tables."""
    async with db_pool.acquire() as conn:
        # Drop existing tables
        await conn.execute("DROP TABLE IF EXISTS products_none CASCADE")
        await conn.execute("DROP TABLE IF EXISTS products_coc CASCADE")
        await conn.execute("DROP TABLE IF EXISTS products_coc_audit CASCADE")
        await conn.execute("DROP TABLE IF EXISTS products_scd2 CASCADE")

        # Create tables for each strategy
        await conn.execute(ProductNone.get_create_table_sql())
        await conn.execute(ProductCopyOnChange.get_create_table_sql())
        for sql in ProductCopyOnChange.get_auxiliary_tables_sql():
            await conn.execute(sql)
        await conn.execute(ProductSCD2.get_create_table_sql())

    yield

    # Cleanup after tests
    async with db_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS products_none CASCADE")
        await conn.execute("DROP TABLE IF EXISTS products_coc CASCADE")
        await conn.execute("DROP TABLE IF EXISTS products_coc_audit CASCADE")
        await conn.execute("DROP TABLE IF EXISTS products_scd2 CASCADE")


class TestNoneStrategy:
    """Test 'none' temporal strategy."""

    @pytest.mark.asyncio
    async def test_basic_crud(self, db_pool, setup_tables):
        """Test basic CRUD operations with none strategy."""
        tenant_id = uuid4()
        user_id = uuid4()

        repo = PydanticRepository(ProductNone, db_pool, tenant_id=tenant_id)

        # Create
        product = await repo.create(
            ProductNone(name="Widget", price=Decimal("99.99")), user_id=user_id
        )

        assert product.id is not None
        assert product.name == "Widget"
        assert product.price == Decimal("99.99")
        assert product.created_by == user_id

        # Read
        fetched = await repo.get(product.id)
        assert fetched.name == "Widget"

        # Update
        updated = await repo.update(
            product.id,
            ProductNone(name="Super Widget", price=Decimal("149.99")),
            user_id=user_id,
        )
        assert updated.name == "Super Widget"
        assert updated.updated_by == user_id

        # Delete (soft)
        deleted = await repo.delete(product.id, user_id=user_id)
        assert deleted is True

        # Verify soft delete
        not_found = await repo.get(product.id)
        assert not_found is None

        # Get with include_deleted
        deleted_product = await repo.get(product.id, include_deleted=True)
        assert deleted_product is not None
        assert deleted_product.deleted_by == user_id

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, db_pool, setup_tables):
        """Test that tenants cannot see each other's data."""
        tenant1 = uuid4()
        tenant2 = uuid4()
        user_id = uuid4()

        repo1 = PydanticRepository(ProductNone, db_pool, tenant_id=tenant1)
        repo2 = PydanticRepository(ProductNone, db_pool, tenant_id=tenant2)

        # Create product for tenant1
        product1 = await repo1.create(
            ProductNone(name="Tenant1 Product", price=Decimal("50.00")), user_id=user_id
        )

        # Create product for tenant2
        product2 = await repo2.create(
            ProductNone(name="Tenant2 Product", price=Decimal("60.00")), user_id=user_id
        )

        # Tenant1 cannot see tenant2's product
        not_found = await repo1.get(product2.id)
        assert not_found is None

        # Tenant2 cannot see tenant1's product
        not_found = await repo2.get(product1.id)
        assert not_found is None

        # Each can see their own
        found1 = await repo1.get(product1.id)
        assert found1.name == "Tenant1 Product"

        found2 = await repo2.get(product2.id)
        assert found2.name == "Tenant2 Product"

    @pytest.mark.asyncio
    async def test_list_filtering(self, db_pool, setup_tables):
        """Test list operations with filters."""
        tenant_id = uuid4()
        user_id = uuid4()

        repo = PydanticRepository(ProductNone, db_pool, tenant_id=tenant_id)

        # Create multiple products
        products = []
        for i in range(5):
            p = await repo.create(
                ProductNone(
                    name=f"Product {i}",
                    price=Decimal(f"{10 * (i + 1)}.00"),
                    status="active" if i % 2 == 0 else "inactive",
                ),
                user_id=user_id,
            )
            products.append(p)

        # List all
        all_products = await repo.list()
        assert len(all_products) == 5

        # List with filter
        active = await repo.list(filters={"status": "active"})
        assert len(active) == 3

        # List with pagination
        page1 = await repo.list(limit=2, offset=0)
        assert len(page1) == 2

        page2 = await repo.list(limit=2, offset=2)
        assert len(page2) == 2

        # Delete one and verify count
        await repo.delete(products[0].id, user_id=user_id)
        remaining = await repo.list()
        assert len(remaining) == 4


class TestCopyOnChangeStrategy:
    """Test 'copy_on_change' temporal strategy."""

    @pytest.mark.asyncio
    async def test_audit_trail(self, db_pool, setup_tables):
        """Test that changes create audit trail entries."""
        tenant_id = uuid4()
        user_id1 = uuid4()
        user_id2 = uuid4()

        repo = PydanticRepository(ProductCopyOnChange, db_pool, tenant_id=tenant_id)

        # Create product
        product = await repo.create(
            ProductCopyOnChange(name="Original", price=Decimal("100.00")),
            user_id=user_id1,
        )

        # Update name
        await repo.update(
            product.id,
            ProductCopyOnChange(name="Updated", price=Decimal("100.00")),
            user_id=user_id2,
        )

        # Update price
        await repo.update(
            product.id,
            ProductCopyOnChange(name="Updated", price=Decimal("150.00")),
            user_id=user_id2,
        )

        # Get audit history
        history = await repo.get_audit_history(product.id)

        # Should have 2 audit entries (one for each update)
        assert len(history) >= 2

        # Check name change
        name_changes = [h for h in history if h.field_name == "name"]
        assert len(name_changes) == 1
        assert name_changes[0].old_value == "Original"
        assert name_changes[0].new_value == "Updated"
        assert name_changes[0].changed_by == user_id2

        # Check price change
        price_changes = [h for h in history if h.field_name == "price"]
        assert len(price_changes) == 1
        assert Decimal(price_changes[0].old_value) == Decimal("100.00")
        assert Decimal(price_changes[0].new_value) == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_field_history(self, db_pool, setup_tables):
        """Test getting history for a specific field."""
        tenant_id = uuid4()
        user_id = uuid4()

        repo = PydanticRepository(ProductCopyOnChange, db_pool, tenant_id=tenant_id)

        # Create and update product multiple times
        product = await repo.create(
            ProductCopyOnChange(name="v1", price=Decimal("10.00")), user_id=user_id
        )

        await repo.update(
            product.id,
            ProductCopyOnChange(name="v2", price=Decimal("10.00")),
            user_id=user_id,
        )

        await repo.update(
            product.id,
            ProductCopyOnChange(name="v3", price=Decimal("10.00")),
            user_id=user_id,
        )

        # Get field history for 'name'
        name_history = await repo.get_field_history(product.id, "name")

        assert len(name_history) == 2  # Two updates to name
        assert name_history[0].old_value == "v1"
        assert name_history[0].new_value == "v2"
        assert name_history[1].old_value == "v2"
        assert name_history[1].new_value == "v3"

    @pytest.mark.asyncio
    async def test_concurrent_updates_with_locking(self, db_pool, setup_tables):
        """Test that row-level locking prevents race conditions."""
        tenant_id = uuid4()
        user_id = uuid4()

        repo = PydanticRepository(ProductCopyOnChange, db_pool, tenant_id=tenant_id)

        # Create product
        product = await repo.create(
            ProductCopyOnChange(name="Test", price=Decimal("100.00")), user_id=user_id
        )

        # Try concurrent updates
        async def update_price(new_price):
            await repo.update(
                product.id,
                ProductCopyOnChange(name="Test", price=new_price),
                user_id=user_id,
            )

        # Run updates concurrently
        tasks = [
            update_price(Decimal("150.00")),
            update_price(Decimal("200.00")),
            update_price(Decimal("250.00")),
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

        # Check audit trail - should have all updates
        history = await repo.get_audit_history(product.id)
        price_changes = [h for h in history if h.field_name == "price"]

        # All updates should be recorded (no lost updates)
        assert len(price_changes) == 3


class TestSCD2Strategy:
    """Test 'scd2' temporal strategy."""

    @pytest.mark.asyncio
    async def test_versioning(self, db_pool, setup_tables):
        """Test that updates create new versions."""
        tenant_id = uuid4()
        user_id = uuid4()

        repo = PydanticRepository(ProductSCD2, db_pool, tenant_id=tenant_id)

        # Create product (version 1)
        product = await repo.create(
            ProductSCD2(name="Version 1", price=Decimal("100.00")), user_id=user_id
        )

        assert product.version == 1

        # Update (creates version 2)
        updated = await repo.update(
            product.id,
            ProductSCD2(name="Version 2", price=Decimal("150.00")),
            user_id=user_id,
        )

        assert updated.version == 2
        assert updated.name == "Version 2"

        # Update again (creates version 3)
        updated2 = await repo.update(
            product.id,
            ProductSCD2(name="Version 3", price=Decimal("200.00")),
            user_id=user_id,
        )

        assert updated2.version == 3

        # Get current version
        current = await repo.get(product.id)
        assert current.version == 3
        assert current.name == "Version 3"

        # Get version history
        history = await repo.get_version_history(product.id)
        assert len(history) == 3

        # Verify versions
        assert history[0].version == 1
        assert history[0].name == "Version 1"
        assert history[1].version == 2
        assert history[1].name == "Version 2"
        assert history[2].version == 3
        assert history[2].name == "Version 3"

    @pytest.mark.asyncio
    async def test_time_travel(self, db_pool, setup_tables):
        """Test time travel queries."""
        tenant_id = uuid4()
        user_id = uuid4()

        repo = PydanticRepository(ProductSCD2, db_pool, tenant_id=tenant_id)

        # Create product
        product = await repo.create(
            ProductSCD2(name="Initial", price=Decimal("100.00")), user_id=user_id
        )

        # Wait a moment
        await asyncio.sleep(0.1)
        time_after_create = datetime.now(timezone.utc)

        # Update
        await repo.update(
            product.id,
            ProductSCD2(name="Updated", price=Decimal("150.00")),
            user_id=user_id,
        )

        # Wait a moment
        await asyncio.sleep(0.1)
        time_after_update = datetime.now(timezone.utc)

        # Query at different points in time
        at_create = await repo.get(product.id, as_of=time_after_create)
        assert at_create.name == "Initial"
        assert at_create.version == 1

        at_update = await repo.get(product.id, as_of=time_after_update)
        assert at_update.name == "Updated"
        assert at_update.version == 2

    @pytest.mark.asyncio
    async def test_version_comparison(self, db_pool, setup_tables):
        """Test comparing different versions."""
        tenant_id = uuid4()
        user_id = uuid4()

        repo = PydanticRepository(ProductSCD2, db_pool, tenant_id=tenant_id)

        # Create and update
        product = await repo.create(
            ProductSCD2(name="Original", price=Decimal("100.00"), status="draft"),
            user_id=user_id,
        )

        await repo.update(
            product.id,
            ProductSCD2(name="Modified", price=Decimal("150.00"), status="active"),
            user_id=user_id,
        )

        # Compare versions
        diff = await repo.compare_versions(product.id, version1=1, version2=2)

        assert diff["name"]["old"] == "Original"
        assert diff["name"]["new"] == "Modified"
        assert diff["name"]["changed"] is True

        assert Decimal(diff["price"]["old"]) == Decimal("100.00")
        assert Decimal(diff["price"]["new"]) == Decimal("150.00")
        assert diff["price"]["changed"] is True

        assert diff["status"]["old"] == "draft"
        assert diff["status"]["new"] == "active"
        assert diff["status"]["changed"] is True

    @pytest.mark.asyncio
    async def test_immutable_versions(self, db_pool, setup_tables):
        """Test that previous versions remain immutable."""
        tenant_id = uuid4()
        user_id = uuid4()

        repo = PydanticRepository(ProductSCD2, db_pool, tenant_id=tenant_id)

        # Create product
        product = await repo.create(
            ProductSCD2(name="Immutable", price=Decimal("100.00")), user_id=user_id
        )

        # Update multiple times
        for i in range(2, 5):
            await repo.update(
                product.id,
                ProductSCD2(name=f"Version {i}", price=Decimal(f"{i * 50}.00")),
                user_id=user_id,
            )

        # Get specific version
        v1 = await repo.get_version(product.id, version=1)
        assert v1.name == "Immutable"
        assert v1.price == Decimal("100.00")

        v3 = await repo.get_version(product.id, version=3)
        assert v3.name == "Version 3"
        assert v3.price == Decimal("150.00")

        # Verify all versions still exist
        history = await repo.get_version_history(product.id)
        assert len(history) == 4


class TestCrossCuttingFeatures:
    """Test features that apply to all strategies."""

    @pytest.mark.asyncio
    async def test_soft_delete_restore(self, db_pool, setup_tables):
        """Test soft delete and restore across strategies."""
        tenant_id = uuid4()
        user_id = uuid4()

        # Test with each strategy
        for model_class in [ProductNone, ProductCopyOnChange, ProductSCD2]:
            repo = PydanticRepository(model_class, db_pool, tenant_id=tenant_id)

            # Create and delete
            product = await repo.create(
                model_class(name="To Delete", price=Decimal("99.99")), user_id=user_id
            )

            await repo.delete(product.id, user_id=user_id)

            # Verify deleted
            not_found = await repo.get(product.id)
            assert not_found is None

            # Restore
            restored = await repo.restore(product.id)
            assert restored is not None
            assert restored.name == "To Delete"

            # Verify restored
            found = await repo.get(product.id)
            assert found is not None

    @pytest.mark.asyncio
    async def test_batch_operations(self, db_pool, setup_tables):
        """Test batch create and get operations."""
        tenant_id = uuid4()
        user_id = uuid4()

        repo = PydanticRepository(ProductNone, db_pool, tenant_id=tenant_id)

        # Batch create
        products_data = [
            ProductNone(name=f"Batch {i}", price=Decimal(f"{i * 10}.00")) for i in range(1, 11)
        ]

        created = await repo.create_many(products_data, user_id=user_id, batch_size=3)
        assert len(created) == 10

        # Batch get
        ids = [p.id for p in created]
        fetched = await repo.get_many(ids)

        assert len(fetched) == 10
        for id in ids:
            assert id in fetched
            assert fetched[id] is not None

    @pytest.mark.asyncio
    async def test_cache_behavior(self, db_pool, setup_tables):
        """Test repository caching."""
        tenant_id = uuid4()
        user_id = uuid4()

        # Create repo with caching
        repo = PydanticRepository(
            ProductNone, db_pool, tenant_id=tenant_id, cache_enabled=True, cache_ttl=5
        )

        # Create product
        product = await repo.create(
            ProductNone(name="Cached", price=Decimal("100.00")), user_id=user_id
        )

        # First get - cache miss
        result1 = await repo.get(product.id)
        assert result1.name == "Cached"

        # Second get - should be cache hit (no DB call)
        result2 = await repo.get(product.id)
        assert result2.name == "Cached"

        # Update invalidates cache
        await repo.update(
            product.id,
            ProductNone(name="Updated", price=Decimal("150.00")),
            user_id=user_id,
        )

        # Next get should fetch updated value
        result3 = await repo.get(product.id)
        assert result3.name == "Updated"

    @pytest.mark.asyncio
    async def test_count_operations(self, db_pool, setup_tables):
        """Test count operations with filters."""
        tenant_id = uuid4()
        user_id = uuid4()

        repo = PydanticRepository(ProductNone, db_pool, tenant_id=tenant_id)

        # Create products
        for i in range(10):
            await repo.create(
                ProductNone(
                    name=f"Product {i}",
                    price=Decimal(f"{i * 10}.00"),
                    status="active" if i < 5 else "inactive",
                ),
                user_id=user_id,
            )

        # Count all
        total = await repo.count()
        assert total == 10

        # Count with filter
        active_count = await repo.count(filters={"status": "active"})
        assert active_count == 5

        # Delete some and count again
        products = await repo.list(limit=3)
        for p in products:
            await repo.delete(p.id, user_id=user_id)

        remaining = await repo.count()
        assert remaining == 7

        # Count including deleted
        all_count = await repo.count(include_deleted=True)
        assert all_count == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
