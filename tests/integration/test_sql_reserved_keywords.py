"""
Integration test for SQL reserved keywords as column names.

This test ensures that fields named with SQL reserved keywords (limit, order, user, etc.)
work correctly in all CRUD operations across all temporal strategies.

This reproduces the bug: syntax error at or near "limit"
"""

from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from ff_storage import Field, PydanticModel, PydanticRepository
from ff_storage.db import Postgres, PostgresPool


class ProductWithReservedKeywords(PydanticModel):
    """Test model with SQL reserved keywords as field names."""

    __table_name__ = "test_reserved_keywords"
    __schema__ = "public"
    __temporal_strategy__ = "scd2"
    __multi_tenant__ = True
    __soft_delete__ = True

    # SQL reserved keywords as field names (this should work!)
    limit: int = Field(description="Maximum quantity allowed")
    order: str = Field(max_length=50, description="Order code")
    user: str = Field(max_length=100, description="User identifier")
    select: bool = Field(description="Selection flag")

    # Normal fields
    name: str = Field(max_length=255)
    price: Decimal = Field(json_schema_extra={"decimal_precision": (10, 2)})


class SimpleProduct(PydanticModel):
    """Test model with 'none' temporal strategy."""

    __table_name__ = "test_reserved_simple"
    __schema__ = "public"
    __temporal_strategy__ = "none"

    limit: int
    order: str = Field(max_length=50)
    user: str = Field(max_length=100)


class AuditedProduct(PydanticModel):
    """Test model with 'copy_on_change' temporal strategy."""

    __table_name__ = "test_reserved_audited"
    __schema__ = "public"
    __temporal_strategy__ = "copy_on_change"

    limit: int
    order: str = Field(max_length=50)
    select: bool


@pytest.fixture
def db(ensure_test_database):
    """Create synchronous database connection."""
    connection = Postgres(
        dbname="test_temporal", user="postgres", password="postgres", host="localhost", port=5436
    )
    connection.connect()
    yield connection
    connection.close_connection()


@pytest_asyncio.fixture
async def db_pool(ensure_test_database):
    """Create async database pool."""
    pool = PostgresPool(
        dbname="test_temporal", user="postgres", password="postgres", host="localhost", port=5436
    )
    await pool.connect()
    yield pool
    await pool.disconnect()


@pytest.mark.asyncio
async def test_create_with_reserved_keywords_scd2(setup_integration_schema, db_pool):
    """
    Test CREATE operation with SQL reserved keywords as column names.

    Verifies that QueryBuilder properly quotes reserved keywords in INSERT queries:
        INSERT INTO "public"."test_reserved_keywords" ("limit", "order", "user", ...)
    """
    tenant_id = uuid4()
    user_id = uuid4()

    repo = PydanticRepository(ProductWithReservedKeywords, db_pool, tenant_id=tenant_id)

    # This will fail with SQL syntax error
    product = await repo.create(
        ProductWithReservedKeywords(
            limit=100,
            order="ORD-12345",
            user="john@example.com",
            select=True,
            name="Test Product",
            price=Decimal("99.99"),
        ),
        user_id=user_id,
    )

    # Assertions
    assert product.id is not None
    assert product.limit == 100
    assert product.order == "ORD-12345"
    assert product.user == "john@example.com"
    assert product.select is True
    assert product.name == "Test Product"
    assert product.price == Decimal("99.99")


@pytest.mark.asyncio
async def test_update_with_reserved_keywords_scd2(setup_integration_schema, db_pool):
    """
    Test UPDATE operation with SQL reserved keywords.

    Verifies that QueryBuilder properly quotes reserved keywords in UPDATE queries:
        UPDATE table SET "limit" = $1, "order" = $2 WHERE ...
    """
    tenant_id = uuid4()
    user_id = uuid4()

    repo = PydanticRepository(ProductWithReservedKeywords, db_pool, tenant_id=tenant_id)

    # Create
    product = await repo.create(
        ProductWithReservedKeywords(
            limit=100,
            order="ORD-001",
            user="user1@test.com",
            select=False,
            name="Original",
            price=Decimal("50.00"),
        ),
        user_id=user_id,
    )

    # Update - will fail with SQL syntax error
    updated = await repo.update(
        product.id,
        ProductWithReservedKeywords(
            limit=200,  # Changed
            order="ORD-002",  # Changed
            user="user2@test.com",  # Changed
            select=True,  # Changed
            name="Updated",
            price=Decimal("75.00"),
        ),
        user_id=user_id,
    )

    assert updated.limit == 200
    assert updated.order == "ORD-002"
    assert updated.version == 2  # SCD2 creates new version


@pytest.mark.asyncio
async def test_list_with_reserved_keywords_filters(setup_integration_schema, db_pool):
    """
    Test LIST operation with filters on reserved keyword columns.

    Verifies that QueryBuilder properly quotes reserved keywords in WHERE clauses:
        WHERE "limit" = $1 AND "order" = $2
    """
    tenant_id = uuid4()
    user_id = uuid4()

    repo = PydanticRepository(ProductWithReservedKeywords, db_pool, tenant_id=tenant_id)

    # Create test data
    await repo.create(
        ProductWithReservedKeywords(
            limit=100, order="A", user="user1", select=True, name="Product A", price=Decimal("10")
        ),
        user_id=user_id,
    )
    await repo.create(
        ProductWithReservedKeywords(
            limit=200,
            order="B",
            user="user2",
            select=False,
            name="Product B",
            price=Decimal("20"),
        ),
        user_id=user_id,
    )

    # Filter by reserved keyword columns - will fail
    results = await repo.list(filters={"limit": 100, "select": True})

    assert len(results) == 1
    assert results[0].limit == 100
    assert results[0].order == "A"


@pytest.mark.asyncio
async def test_reserved_keywords_with_none_strategy(setup_integration_schema, db_pool):
    """Test reserved keywords work with 'none' temporal strategy."""
    tenant_id = uuid4()
    repo = PydanticRepository(SimpleProduct, db_pool, tenant_id=tenant_id)

    # Will fail with same SQL syntax error
    product = await repo.create(
        SimpleProduct(limit=50, order="TEST", user="test_user"), user_id=uuid4()
    )

    assert product.limit == 50


@pytest.mark.asyncio
async def test_reserved_keywords_with_copy_on_change_strategy(setup_integration_schema, db_pool):
    """Test reserved keywords work with 'copy_on_change' temporal strategy."""
    tenant_id = uuid4()
    user_id = uuid4()
    repo = PydanticRepository(AuditedProduct, db_pool, tenant_id=tenant_id)

    # Will fail in INSERT
    product = await repo.create(
        AuditedProduct(limit=75, order="AUDIT-001", select=True), user_id=user_id
    )

    # Will also fail in UPDATE
    updated = await repo.update(
        product.id, AuditedProduct(limit=100, order="AUDIT-002", select=False), user_id=user_id
    )

    assert updated.limit == 100
