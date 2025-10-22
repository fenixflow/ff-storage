"""
Example: Basic Product Model with copy_on_change strategy.

This example demonstrates:
- PydanticModel with field-level audit tracking
- Multi-tenant and soft delete (enabled by default)
- Basic CRUD operations
- Audit history queries
"""

import asyncio
from decimal import Decimal
from uuid import uuid4

from ff_storage import Field, PydanticModel, PydanticRepository
from ff_storage.db.connections.postgres import PostgresPool

# ==================== Model Definition ====================


class Product(PydanticModel):
    """
    Product model with field-level change tracking.

    Features:
    - Field-level audit (copy_on_change strategy)
    - Multi-tenant (tenant_id auto-injected)
    - Soft delete (deleted_at, deleted_by auto-injected)
    - Type-safe with Pydantic validation
    """

    __table_name__ = "products"
    __temporal_strategy__ = "copy_on_change"
    __soft_delete__ = True  # Default, but explicit here
    __multi_tenant__ = True  # Default, but explicit here

    # User-defined fields with validation
    name: str = Field(
        max_length=255,
        description="Product name",
    )

    price: Decimal = Field(
        ge=0,
        description="Product price (must be >= 0)",
        db_precision=10,
        db_scale=2,
    )

    status: str = Field(
        max_length=50,
        default="active",
        description="Product status",
        db_index=True,  # Create index on status
    )

    category: str = Field(
        max_length=100,
        description="Product category",
    )

    stock: int = Field(
        ge=0,
        default=0,
        description="Stock quantity",
    )


# ==================== Usage Example ====================


async def main():
    """Demonstrate product CRUD with audit tracking."""

    # Setup
    org_id = uuid4()  # Tenant ID
    user_id = uuid4()  # User ID

    # Connect to database
    db_pool = PostgresPool(
        dbname="fenix_dev",
        user="fenix",
        password="password",
        host="localhost",
        port=5432,
    )
    await db_pool.connect()

    # Create repository (tenant-scoped)
    repo = PydanticRepository(
        Product,
        db_pool,
        tenant_id=org_id,
    )

    print("=== Product CRUD Example ===\n")

    # ==================== CREATE ====================

    print("1. Creating product...")
    product = Product(
        name="Laptop Pro",
        price=Decimal("1299.99"),
        status="active",
        category="electronics",
        stock=50,
    )

    created = await repo.create(product, user_id=user_id)
    print(f"   Created: {created.name} (ID: {created.id})")
    print(f"   Price: ${created.price}")
    print()

    # ==================== UPDATE (Field-Level Audit) ====================

    print("2. Updating price (single field)...")
    created.price = Decimal("1199.99")
    updated = await repo.update(created.id, created, user_id=user_id)
    print(f"   Updated price: ${updated.price}")
    print()

    print("3. Updating multiple fields...")
    updated.stock = 45
    updated.status = "low_stock"
    updated2 = await repo.update(updated.id, updated, user_id=user_id)
    print(f"   Updated stock: {updated2.stock}")
    print(f"   Updated status: {updated2.status}")
    print()

    # ==================== AUDIT HISTORY ====================

    print("4. Getting audit history (field-level)...")
    history = await repo.get_audit_history(created.id)
    print(f"   Total changes: {len(history)}")
    for entry in history:
        print(
            f"   - {entry.changed_at}: {entry.field_name} changed from {entry.old_value} to {entry.new_value}"
        )
    print()

    print("5. Getting history for specific field (price)...")
    price_history = await repo.get_field_history(created.id, "price")
    print(f"   Price changes: {len(price_history)}")
    for entry in price_history:
        print(f"   - {entry.changed_at}: ${entry.old_value} → ${entry.new_value}")
    print()

    # ==================== LIST WITH FILTERS ====================

    print("6. Listing products (filtered by status)...")
    products = await repo.list(
        filters={"status": "low_stock"},
        limit=10,
    )
    print(f"   Found {len(products)} low stock products")
    for p in products:
        print(f"   - {p.name}: {p.stock} units")
    print()

    # ==================== SOFT DELETE ====================

    print("7. Soft deleting product...")
    deleted = await repo.delete(created.id, user_id=user_id)
    print(f"   Deleted: {deleted}")
    print()

    print("8. Verifying deletion (default: excludes deleted)...")
    found = await repo.get(created.id)
    print(f"   Found (without include_deleted): {found}")
    print()

    print("9. Getting deleted record (include_deleted=True)...")
    found_deleted = await repo.get(created.id, include_deleted=True)
    print(f"   Found (with include_deleted): {found_deleted.name if found_deleted else None}")
    print(f"   Deleted at: {found_deleted.deleted_at if found_deleted else None}")
    print()

    # ==================== RESTORE ====================

    print("10. Restoring deleted product...")
    restored = await repo.restore(created.id)
    print(f"   Restored: {restored.name}")
    print(f"   Deleted at: {restored.deleted_at}")  # Should be None
    print()

    # Cleanup
    await db_pool.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
