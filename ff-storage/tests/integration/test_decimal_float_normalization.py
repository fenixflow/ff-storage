"""
Regression tests for Decimal→Float conversion in temporal strategies.

Tests that Decimal values passed to DOUBLE PRECISION columns are properly
converted to float before being sent to asyncpg, preventing type errors.

Issue: SCD2 (and other strategies) insert Decimal into DOUBLE PRECISION columns,
causing: "invalid input for query argument $N: Decimal(...) (expected str, got Decimal)"
"""

from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from ff_storage import Field, PydanticModel, PydanticRepository


class ProductWithFloatSCD2(PydanticModel):
    """Product model with float field using SCD2 strategy."""

    __table_name__ = "products_float_scd2"
    __temporal_strategy__ = "scd2"
    __soft_delete__ = True
    __multi_tenant__ = True

    name: str = Field(max_length=255)
    # Float field maps to DOUBLE PRECISION in PostgreSQL
    score: float
    status: str = Field(default="active")


class ProductWithFloatCopyOnChange(PydanticModel):
    """Product model with float field using copy_on_change strategy."""

    __table_name__ = "products_float_coc"
    __temporal_strategy__ = "copy_on_change"
    __soft_delete__ = True
    __multi_tenant__ = True

    name: str = Field(max_length=255)
    score: float
    status: str = Field(default="active")


class ProductWithFloatNone(PydanticModel):
    """Product model with float field using none strategy."""

    __table_name__ = "products_float_none"
    __temporal_strategy__ = "none"
    __soft_delete__ = True
    __multi_tenant__ = True

    name: str = Field(max_length=255)
    score: float
    status: str = Field(default="active")


@pytest_asyncio.fixture
async def db_pool(ensure_test_database):
    """Database pool for testing."""
    import asyncpg

    pool = await asyncpg.create_pool(
        host="localhost",
        port=5436,
        database="test_temporal",
        user="postgres",
        password="postgres",
        min_size=2,
        max_size=10,
    )
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def setup_tables(db_pool):
    """Create test tables with float columns."""
    async with db_pool.acquire() as conn:
        # Drop existing tables
        await conn.execute("DROP TABLE IF EXISTS products_float_scd2 CASCADE")
        await conn.execute("DROP TABLE IF EXISTS products_float_coc CASCADE")
        await conn.execute("DROP TABLE IF EXISTS products_float_coc_audit CASCADE")
        await conn.execute("DROP TABLE IF EXISTS products_float_none CASCADE")

        # Create tables
        await conn.execute(ProductWithFloatSCD2.get_create_table_sql())
        await conn.execute(ProductWithFloatCopyOnChange.get_create_table_sql())
        for sql in ProductWithFloatCopyOnChange.get_auxiliary_tables_sql():
            await conn.execute(sql)
        await conn.execute(ProductWithFloatNone.get_create_table_sql())

    yield


@pytest.mark.asyncio
async def test_scd2_decimal_to_float_conversion(db_pool, setup_tables):
    """
    Regression test: Decimal values should be converted to float for DOUBLE PRECISION columns.

    Bug: When passing Decimal to a float field (DOUBLE PRECISION), asyncpg throws:
         "invalid input for query argument $N: Decimal(...) (expected str, got Decimal)"

    This test verifies that Decimal values are normalized to float before INSERT.
    """
    tenant_id = uuid4()
    user_id = uuid4()

    # Create repository
    repo = PydanticRepository(
        ProductWithFloatSCD2,
        db_pool=db_pool,
        tenant_id=tenant_id,
    )

    # Create product with Decimal value for float field
    # This simulates user passing Decimal (common from calculations, JSON parsing, etc.)
    product = ProductWithFloatSCD2(
        name="Test Product",
        score=Decimal("99.5"),  # Decimal passed to float field
        status="active",
    )

    # EXPECTED: This should NOT raise an asyncpg type error
    # ACTUAL (before fix): Raises "invalid input for query argument $N: Decimal(...)"
    created = await repo.create(product, user_id=user_id)

    # Verify the value was stored correctly
    assert created.name == "Test Product"
    # Value should be float after round-trip
    assert isinstance(created.score, float)
    assert created.score == 99.5


@pytest.mark.asyncio
async def test_scd2_update_with_decimal_to_float(db_pool, setup_tables):
    """
    Test that Decimal→Float conversion works in UPDATE operations (SCD2 new version).
    """
    tenant_id = uuid4()
    user_id = uuid4()

    repo = PydanticRepository(
        ProductWithFloatSCD2,
        db_pool=db_pool,
        tenant_id=tenant_id,
    )

    # Create initial version
    product = ProductWithFloatSCD2(
        name="Test Product",
        score=50.0,
        status="active",
    )
    created = await repo.create(product, user_id=user_id)

    # Update with Decimal value
    updated_product = ProductWithFloatSCD2(
        name="Updated Product",
        score=Decimal("75.8"),  # Decimal passed to float field
        status="active",
    )

    # EXPECTED: Should NOT raise asyncpg type error
    updated = await repo.update(created.id, updated_product, user_id=user_id)

    assert updated.name == "Updated Product"
    assert isinstance(updated.score, float)
    assert updated.score == 75.8
    # Verify it created a new version
    assert updated.version == 2


@pytest.mark.asyncio
async def test_copy_on_change_decimal_to_float(db_pool, setup_tables):
    """
    Test that Decimal→Float conversion works for copy_on_change strategy.
    """
    tenant_id = uuid4()
    user_id = uuid4()

    repo = PydanticRepository(
        ProductWithFloatCopyOnChange,
        db_pool=db_pool,
        tenant_id=tenant_id,
    )

    # Create with Decimal
    product = ProductWithFloatCopyOnChange(
        name="Test Product",
        score=Decimal("88.9"),
        status="active",
    )

    created = await repo.create(product, user_id=user_id)

    assert created.name == "Test Product"
    assert isinstance(created.score, float)
    assert created.score == 88.9


@pytest.mark.asyncio
async def test_none_strategy_decimal_to_float(db_pool, setup_tables):
    """
    Test that Decimal→Float conversion works for none strategy.
    """
    tenant_id = uuid4()
    user_id = uuid4()

    repo = PydanticRepository(
        ProductWithFloatNone,
        db_pool=db_pool,
        tenant_id=tenant_id,
    )

    # Create with Decimal
    product = ProductWithFloatNone(
        name="Test Product",
        score=Decimal("66.7"),
        status="active",
    )

    created = await repo.create(product, user_id=user_id)

    assert created.name == "Test Product"
    assert isinstance(created.score, float)
    assert created.score == 66.7
