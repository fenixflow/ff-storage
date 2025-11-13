"""
TDD Test for Pydantic Schema Consistency.

This test verifies that when a Pydantic model is used to create a table,
and then the table is introspected, the resulting schema definitions are
identical - meaning NO schema drift is detected.

This is critical for the ff-storage schema synchronization system to work
correctly without generating false positive drift warnings.

Test Strategy:
1. Create Pydantic models with all common field types
2. Use SchemaManager to create tables from models
3. Introspect the created tables
4. Compare desired schema (from Pydantic) vs current schema (from DB)
5. Assert NO differences are detected

Expected Result:
- Zero schema changes should be detected after initial table creation
- All native_type values should match between Pydantic and PostgreSQL
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pytest
from ff_storage.db import Postgres, SchemaManager
from ff_storage.db.schema_sync.normalizer import PostgresNormalizer
from ff_storage.db.schema_sync.postgres import PostgresSchemaIntrospector
from ff_storage.pydantic_support.base import PydanticModel
from ff_storage.pydantic_support.introspector import PydanticSchemaIntrospector
from pydantic import Field

# ==================== Test Models ====================


class AllTypesModel(PydanticModel):
    """
    Test model with all common PostgreSQL types.

    This model exercises every major column type to ensure consistent
    native_type representation between Pydantic schema generation
    and PostgreSQL introspection.
    """

    __table_name__ = "test_all_types"
    __schema__ = "public"
    __temporal_strategy__ = "none"
    __soft_delete__ = False
    __multi_tenant__ = False

    # String types
    name: str = Field(max_length=255)
    description: str  # TEXT type (no max_length)

    # Numeric types
    age: int
    quantity: int = Field(ge=0)  # Non-negative integer
    large_number: int  # BIGINT if annotated, or INTEGER by default

    # Decimal types
    price: Decimal = Field(max_digits=10, decimal_places=2)
    rate: Decimal

    # Boolean type
    is_active: bool
    is_verified: bool = True

    # Timestamp types
    created_timestamp: datetime  # TIMESTAMP WITHOUT TIME ZONE

    # UUID type (already in base PydanticModel as 'id')

    # JSONB types
    metadata: Dict[str, Any]
    tags: Optional[List[str]] = None

    # Optional fields
    notes: Optional[str] = None
    score: Optional[int] = None


class SCD2TemporalModel(PydanticModel):
    """
    Test model with SCD2 temporal strategy.

    This tests that temporal fields (valid_from, valid_to, version)
    are correctly created and introspected without drift.
    """

    __table_name__ = "test_scd2_temporal"
    __schema__ = "public"
    __temporal_strategy__ = "scd2"
    __soft_delete__ = True
    __multi_tenant__ = True

    product_name: str = Field(max_length=200)
    product_code: str = Field(max_length=50)
    unit_price: Decimal = Field(max_digits=10, decimal_places=2)


class MinimalModel(PydanticModel):
    """
    Minimal test model with just basic fields.

    Used for focused testing of core type mapping.
    """

    __table_name__ = "test_minimal"
    __schema__ = "public"
    __temporal_strategy__ = "none"
    __soft_delete__ = False
    __multi_tenant__ = False

    title: str


# ==================== Fixtures ====================


@pytest.fixture(scope="session")
def ensure_test_db():
    """Ensure test_schema_consistency database exists."""
    import psycopg2

    conn = psycopg2.connect(
        dbname="postgres",
        user="postgres",
        password="postgres",
        host="localhost",
        port=5438,
    )
    conn.autocommit = True

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", ("test_schema_consistency",)
            )
            result = cursor.fetchone()

            if not result:
                cursor.execute("CREATE DATABASE test_schema_consistency")
                logging.info("Created test_schema_consistency database")

        yield

    finally:
        conn.close()


@pytest.fixture(scope="function")
def db_connection(ensure_test_db):
    """Provide a fresh database connection for each test."""
    db = Postgres(
        dbname="test_schema_consistency",
        user="postgres",
        password="postgres",
        host="localhost",
        port=5438,
    )

    db.connect()

    yield db

    # Cleanup: drop test tables after each test
    try:
        tables = ["test_all_types", "test_scd2_temporal", "test_minimal"]
        for table in tables:
            db.execute_query(f"DROP TABLE IF EXISTS public.{table} CASCADE")
    except Exception as e:
        logging.warning(f"Cleanup failed: {e}")
    finally:
        db.close_connection()


@pytest.fixture
def logger():
    """Provide a logger for tests."""
    logger = logging.getLogger("test_schema_consistency")
    logger.setLevel(logging.DEBUG)
    return logger


# ==================== Tests ====================


class TestPydanticSchemaConsistency:
    """Test that Pydantic-generated schemas match introspected schemas."""

    def test_minimal_model_no_drift(self, db_connection, logger):
        """
        CRITICAL TEST: Minimal model should have ZERO drift after creation.

        This is the most basic test case. If this fails, the type mapping
        system has a fundamental issue.
        """
        # Arrange: Create schema manager
        manager = SchemaManager(db_connection, logger=logger)

        # Act: Create table from Pydantic model
        changes = manager.sync_schema(
            models=[MinimalModel],
            allow_destructive=False,
            dry_run=False,
        )

        logger.info(f"Initial sync: {changes} changes applied")

        # Act: Sync again - should detect NO changes
        changes_second = manager.sync_schema(
            models=[MinimalModel],
            allow_destructive=False,
            dry_run=True,  # Dry run to see what would change
        )

        # Assert: NO changes should be detected
        assert changes_second == 0, (
            f"Expected 0 changes on second sync, but detected {changes_second} changes. "
            "This indicates schema drift between Pydantic model and introspected database schema."
        )

    def test_all_types_model_no_drift(self, db_connection, logger):
        """
        COMPREHENSIVE TEST: Model with all common types should have ZERO drift.

        This tests every major PostgreSQL type to ensure consistent native_type
        representation across:
        - Pydantic type mapping (str → VARCHAR, int → INTEGER, etc.)
        - PostgreSQL introspection (information_schema.columns)
        - Type normalization (PostgresNormalizer)
        """
        # Arrange
        manager = SchemaManager(db_connection, logger=logger)

        # Act: Create table
        changes = manager.sync_schema(
            models=[AllTypesModel],
            allow_destructive=False,
            dry_run=False,
        )

        logger.info(f"Initial sync for AllTypesModel: {changes} changes")

        # Act: Sync again
        changes_second = manager.sync_schema(
            models=[AllTypesModel],
            allow_destructive=False,
            dry_run=True,
        )

        # Assert: NO drift
        assert changes_second == 0, (
            f"AllTypesModel has {changes_second} schema drift issues. "
            "Check native_type mapping for: VARCHAR, TEXT, INTEGER, BIGINT, "
            "NUMERIC, BOOLEAN, TIMESTAMP WITH TIME ZONE, UUID, JSONB"
        )

    def test_scd2_temporal_model_no_drift(self, db_connection, logger):
        """
        TEMPORAL TEST: SCD2 model with temporal fields should have ZERO drift.

        This tests that automatically injected temporal fields
        (tenant_id, version, valid_from, valid_to, deleted_at, deleted_by)
        are correctly created and introspected.
        """
        # Arrange
        manager = SchemaManager(db_connection, logger=logger)

        # Act: Create table
        changes = manager.sync_schema(
            models=[SCD2TemporalModel],
            allow_destructive=False,
            dry_run=False,
        )

        logger.info(f"Initial sync for SCD2TemporalModel: {changes} changes")

        # Act: Sync again
        changes_second = manager.sync_schema(
            models=[SCD2TemporalModel],
            allow_destructive=False,
            dry_run=True,
        )

        # Assert: NO drift
        assert changes_second == 0, (
            f"SCD2TemporalModel has {changes_second} schema drift issues. "
            "Check temporal field types: tenant_id (UUID), version (INTEGER), "
            "valid_from/valid_to (TIMESTAMP WITH TIME ZONE), "
            "deleted_at (TIMESTAMP WITH TIME ZONE), deleted_by (UUID)"
        )

    def test_native_type_consistency_debug(self, db_connection, logger):
        """
        DEBUG TEST: Capture and compare exact native_type values.

        This test extracts the actual native_type values from both:
        1. Pydantic schema generation (PydanticSchemaIntrospector)
        2. PostgreSQL introspection (PostgresSchemaIntrospector)

        If this test fails, the output will show exactly which types don't match.
        """
        # Arrange: Create table first
        manager = SchemaManager(db_connection, logger=logger)
        manager.sync_schema(
            models=[AllTypesModel],
            allow_destructive=False,
            dry_run=False,
        )

        # Act: Extract schema from Pydantic model
        pydantic_introspector = PydanticSchemaIntrospector()
        desired_table = pydantic_introspector.extract_table_definition(AllTypesModel)

        # Act: Extract schema from PostgreSQL
        postgres_introspector = PostgresSchemaIntrospector(db_connection)
        current_table = postgres_introspector.get_table_schema(
            table_name="test_all_types", schema="public"
        )

        # Act: Normalize both schemas
        normalizer = PostgresNormalizer()

        # Compare each column
        desired_cols = {col.name: col for col in desired_table.columns}
        current_cols = {col.name: col for col in current_table.columns}

        mismatches = []

        for col_name in desired_cols:
            if col_name not in current_cols:
                mismatches.append(f"Column '{col_name}' missing in database")
                continue

            desired_col = desired_cols[col_name]
            current_col = current_cols[col_name]

            # Normalize
            norm_desired = normalizer.normalize_column(desired_col)
            norm_current = normalizer.normalize_column(current_col)

            # Compare native_type specifically
            if norm_desired.native_type != norm_current.native_type:
                mismatches.append(
                    f"Column '{col_name}': "
                    f"Pydantic='{norm_desired.native_type}' != "
                    f"PostgreSQL='{norm_current.native_type}'"
                )

            # Compare column_type enum
            if norm_desired.column_type != norm_current.column_type:
                mismatches.append(
                    f"Column '{col_name}' column_type: "
                    f"Pydantic={norm_desired.column_type} != "
                    f"PostgreSQL={norm_current.column_type}"
                )

            # Compare nullable
            if norm_desired.nullable != norm_current.nullable:
                mismatches.append(
                    f"Column '{col_name}' nullable: "
                    f"Pydantic={norm_desired.nullable} != "
                    f"PostgreSQL={norm_current.nullable}"
                )

            # Compare default
            if norm_desired.default != norm_current.default:
                mismatches.append(
                    f"Column '{col_name}' default: "
                    f"Pydantic='{norm_desired.default}' != "
                    f"PostgreSQL='{norm_current.default}'"
                )

        # Assert: NO mismatches
        if mismatches:
            failure_msg = "Schema consistency check FAILED:\n" + "\n".join(mismatches)
            logger.error(failure_msg)
            pytest.fail(failure_msg)

        logger.info("✅ All columns match perfectly between Pydantic and PostgreSQL!")


class TestIndexConsistency:
    """Test that indexes are consistently created and introspected."""

    def test_index_definitions_no_drift(self, db_connection, logger):
        """
        Test that index definitions don't cause drift warnings.

        This specifically tests the index WHERE clause normalization
        that was causing false positives.
        """
        # Arrange
        manager = SchemaManager(db_connection, logger=logger)

        # Act: Create table with indexes
        manager.sync_schema(
            models=[SCD2TemporalModel],
            allow_destructive=False,
            dry_run=False,
        )

        # Act: Sync again
        changes_second = manager.sync_schema(
            models=[SCD2TemporalModel],
            allow_destructive=False,
            dry_run=True,
        )

        # Assert: NO index drift
        assert changes_second == 0, (
            f"Index definitions have {changes_second} drift issues. "
            "Check WHERE clause normalization."
        )


class TestIndexColumnOrder:
    """Test that index column order is preserved exactly as defined."""

    def test_index_column_order_matches_creation_order(self, db_connection, logger):
        """
        Index columns MUST be returned in the order they were defined in CREATE INDEX.

        PostgreSQL stores this in pg_index.indkey array.
        ORDER BY attnum is WRONG - returns table column order.
        ORDER BY array_position(indkey, attnum) is CORRECT - returns index definition order.

        This is critical because index column order affects query performance.
        Multi-tenant indexes need (tenant_id, created_at) for efficient filtering.
        """
        from ff_storage.db.schema_sync.postgres import PostgresSchemaIntrospector

        # Create table with columns in specific order
        db_connection.execute_query(
            """
            CREATE TABLE IF NOT EXISTS test_idx_order (
                id UUID PRIMARY KEY,
                col_c TEXT,
                col_a TEXT,
                col_b TEXT
            )
        """
        )

        # Create index with DIFFERENT order than table columns
        # Index order: col_b, col_c, col_a (NOT alphabetical, NOT attnum order)
        db_connection.execute_query(
            """
            CREATE INDEX IF NOT EXISTS idx_specific_order
            ON test_idx_order (col_b, col_c, col_a)
        """
        )

        # Verify with pg_get_indexdef (authoritative source)
        result = db_connection.read_query(
            """
            SELECT pg_get_indexdef(i.oid)
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            WHERE t.relname = 'test_idx_order'
              AND i.relname = 'idx_specific_order'
        """,
            as_dict=False,
        )

        indexdef = result[0][0]
        assert "(col_b, col_c, col_a)" in indexdef, (
            f"PostgreSQL stores index as (col_b, col_c, col_a), got: {indexdef}"
        )

        # Introspect the index
        introspector = PostgresSchemaIntrospector(db_connection)
        indexes = introspector.get_indexes("test_idx_order", "public")
        idx = [i for i in indexes if i.name == "idx_specific_order"][0]

        # MUST match CREATE INDEX order, NOT table order, NOT alphabetical
        assert idx.columns == [
            "col_b",
            "col_c",
            "col_a",
        ], (
            f"Introspector must return index definition order (col_b, col_c, col_a), got {idx.columns}"
        )

        # Cleanup
        db_connection.execute_query("DROP TABLE test_idx_order CASCADE")


class TestRealWorldModels:
    """Test schema consistency with real-world complex models from ix-ds."""

    def test_real_world_contingency_sui_no_drift(self, db_connection, logger):
        """
        REAL-WORLD TEST: Complex SUI model from ix-ds should have ZERO drift.

        This model has:
        - SCD2 temporal strategy
        - Soft delete + multi-tenant
        - Complex nested JSONB (list[Pydantic models])
        - Custom serializers/validators
        - list[str] with custom JSON encoding
        - Multiple field types and constraints

        This test catches edge cases that simpler models miss.
        """
        # Import the real-world model
        from fixtures.real_world_models import RealWorldContingencySUI

        # Arrange
        manager = SchemaManager(db_connection, logger=logger)

        # Act: Create table
        changes = manager.sync_schema(
            models=[RealWorldContingencySUI],
            allow_destructive=False,
            dry_run=False,
        )

        logger.info(f"Initial sync for RealWorldContingencySUI: {changes} changes")

        # Act: Sync again
        changes_second = manager.sync_schema(
            models=[RealWorldContingencySUI],
            allow_destructive=False,
            dry_run=True,
        )

        # Assert: NO drift
        assert changes_second == 0, (
            f"RealWorldContingencySUI has {changes_second} schema drift issues. "
            "This real-world model should create a stable schema. Check: "
            "list[str] serialization, nested JSONB models, temporal fields, "
            "Decimal precision, date fields, Optional fields"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
