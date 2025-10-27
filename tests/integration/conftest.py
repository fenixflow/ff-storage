"""
Pytest configuration for integration tests.

Provides session-scoped fixtures for database schema setup using SchemaManager.
"""

import logging

import pytest
from ff_storage.db import Postgres, SchemaManager

# Import test models that need schema setup
from test_sql_reserved_keywords import (
    AuditedProduct,
    ProductWithReservedKeywords,
    SimpleProduct,
)


@pytest.fixture(scope="session")
def ensure_test_database():
    """
    Create test_temporal database if it doesn't exist.

    Connects to the default 'postgres' database to check and create
    the test_temporal database. This ensures the database exists before
    any tests attempt to connect to it.

    This fixture runs once per test session.
    """
    import psycopg2

    # Use raw psycopg2 connection with autocommit for CREATE DATABASE
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
            # Check if test_temporal database exists
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", ("test_temporal",))
            result = cursor.fetchone()

            if not result:
                # Create database if it doesn't exist
                cursor.execute("CREATE DATABASE test_temporal")
                logging.info("Created test_temporal database")
            else:
                logging.info("test_temporal database already exists")

        yield

    finally:
        conn.close()


@pytest.fixture(scope="session")
def setup_integration_schema(ensure_test_database):
    """
    Create test database schema before integration tests run.

    This fixture uses SchemaManager to automatically create all tables
    and auxiliary tables (e.g., audit tables) from model definitions.

    Tables created:
    - public.test_reserved_keywords (SCD2 strategy)
    - public.test_reserved_simple (None strategy)
    - public.test_reserved_audited (CopyOnChange strategy)
    - public.test_reserved_audited_audit (auto-created auxiliary table)

    The schema is created once per test session and shared across all tests.

    Note: Uses synchronous Postgres connection since SchemaManager requires sync operations.
    """
    # Create synchronous database connection (SchemaManager requires sync)
    db = Postgres(
        dbname="test_temporal",
        user="postgres",
        password="postgres",
        host="localhost",
        port=5438,
    )

    try:
        db.connect()

        # Create logger for schema operations
        logger = logging.getLogger("test_schema_setup")
        logger.setLevel(logging.INFO)

        # Create SchemaManager
        manager = SchemaManager(db, logger=logger)

        # Sync schema for all test models
        # This will create tables if they don't exist, or add missing columns/indexes
        changes_applied = manager.sync_schema(
            models=[
                ProductWithReservedKeywords,
                SimpleProduct,
                AuditedProduct,
            ],
            allow_destructive=False,  # Don't drop columns/tables
            dry_run=False,  # Actually apply changes
        )

        logger.info(f"Schema setup complete: {changes_applied} changes applied")

        # Yield control to tests
        yield

    finally:
        # Cleanup: disconnect from database
        db.close_connection()
