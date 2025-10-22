"""
SchemaManager example: Auto-create main + auxiliary tables.

Demonstrates:
- PydanticModel with copy_on_change strategy
- SchemaManager auto-creates main table + audit table
- Verification both tables exist
- Dry run mode
"""

from ff_storage import Field, Postgres, PydanticModel, SchemaManager

# ==================== Model Definition ====================


class Product(PydanticModel):
    """Product model with field-level audit trail."""

    __table_name__ = "products"
    __temporal_strategy__ = "copy_on_change"  # Creates audit table

    name: str = Field(max_length=255, db_index=True)
    price: float = Field(ge=0, description="Product price")
    status: str = Field(max_length=50, default="active")


# ==================== Schema Management ====================


def main():
    """Demonstrate SchemaManager with auxiliary table creation."""

    # Connect to database (synchronous)
    db = Postgres(
        dbname="fenix_dev",
        user="fenix",
        password="password",
        host="localhost",
        port=5432,
    )
    db.connect()

    print("=== SchemaManager Example ===\n")

    # Create schema manager
    manager = SchemaManager(db)

    # ==================== Dry Run ====================

    print("1. Dry run (preview changes)...")
    changes = manager.sync_schema(
        models=[Product],
        allow_destructive=False,
        dry_run=True,  # Preview only
    )
    print(f"   Would apply {changes} changes\n")

    # ==================== Apply Changes ====================

    print("2. Applying schema changes...")
    changes = manager.sync_schema(
        models=[Product],
        allow_destructive=False,
        dry_run=False,  # Actually apply
    )
    print(f"   Applied {changes} changes")
    print("   - CREATE TABLE products")
    print("   - CREATE TABLE products_audit (auxiliary)")
    print()

    # ==================== Verify Tables Exist ====================

    print("3. Verifying tables exist...")

    # Check main table
    main_exists_query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'products'
        )
    """
    main_exists = db.read_query(main_exists_query, as_dict=False)[0][0]
    print(f"   products table exists: {main_exists}")

    # Check auxiliary audit table
    audit_exists_query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'products_audit'
        )
    """
    audit_exists = db.read_query(audit_exists_query, as_dict=False)[0][0]
    print(f"   products_audit table exists: {audit_exists}")

    # ==================== Inspect Audit Table Schema ====================

    print("\n4. Audit table schema:")
    audit_schema_query = """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'products_audit'
        ORDER BY ordinal_position
    """
    columns = db.read_query(audit_schema_query, as_dict=True)
    for col in columns:
        nullable = "NULL" if col["is_nullable"] == "YES" else "NOT NULL"
        print(f"   {col['column_name']}: {col['data_type']} {nullable}")

    # Expected output:
    # audit_id: uuid NOT NULL
    # record_id: uuid NOT NULL
    # tenant_id: uuid NOT NULL (if multi_tenant)
    # field_name: character varying NOT NULL
    # old_value: jsonb NULL
    # new_value: jsonb NULL
    # operation: character varying NOT NULL
    # changed_at: timestamp with time zone NOT NULL
    # changed_by: uuid NULL
    # transaction_id: uuid NULL
    # metadata: jsonb NULL

    # ==================== Verify Indexes ====================

    print("\n5. Indexes on audit table:")
    index_query = """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
        AND tablename = 'products_audit'
        ORDER BY indexname
    """
    indexes = db.read_query(index_query, as_dict=True)
    for idx in indexes:
        print(f"   {idx['indexname']}")

    # Expected output:
    # idx_products_audit_changed_at
    # idx_products_audit_record_field
    # idx_products_audit_tenant_id (if multi_tenant)

    # ==================== Second Run (No Changes) ====================

    print("\n6. Running sync again (idempotent)...")
    changes = manager.sync_schema(
        models=[Product],
        dry_run=False,
    )
    print(f"   Applied {changes} changes (should be 0)")

    # Cleanup
    db.close_connection()

    print("\n✅ SchemaManager successfully created main + auxiliary tables!")


if __name__ == "__main__":
    main()
