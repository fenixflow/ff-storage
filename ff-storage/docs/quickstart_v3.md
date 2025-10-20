# FF-Storage v3.0.0 Quickstart Guide

Get started with ff-storage's Pydantic ORM and temporal data management in 5 minutes.

## Installation

```bash
# From source (for POC development)
cd /path/to/fenix-packages
uv pip install -e ./ff-storage
```

## 5-Minute Example: User Management with Audit Trail

This example demonstrates:
- Defining a Pydantic model with temporal tracking
- Auto-syncing schema to database
- CRUD operations with automatic audit trail
- Querying audit history

### 1. Define Your Model

```python
from datetime import datetime
from uuid import UUID
from ff_storage import PydanticModel, Field

class User(PydanticModel):
    """User model with field-level audit trail."""

    # Table configuration
    __table_name__ = "users"
    __schema__ = "public"
    __temporal_strategy__ = "copy_on_change"  # Field-level audit
    __soft_delete__ = True   # Default (can omit)
    __multi_tenant__ = True  # Default (can omit)

    # User-defined fields with validation and database metadata
    email: str = Field(
        max_length=255,
        description="User email address",
        db_unique=True,  # UNIQUE constraint
        db_index=True,   # Index for fast lookups
    )

    name: str = Field(
        max_length=255,
        description="Full name",
    )

    age: int = Field(
        ge=0,
        le=150,
        description="User age",
    )

    role: str = Field(
        max_length=50,
        default="user",
        description="User role",
        db_index=True,  # Index on role for filtering
    )
```

### 2. Auto-Sync Schema to Database

```python
from ff_storage import PostgresPool, SchemaManager

# Connect to database
db_pool = PostgresPool(
    dbname="fenix_dev",
    user="fenix",
    password="password",
    host="localhost",
    port=5432,
)
db_pool.connect()

# Create schema manager
manager = SchemaManager(db_pool)

# Auto-sync schema (creates main table + audit table)
changes = manager.sync_schema(
    models=[User],
    allow_destructive=False,  # Safe by default
    dry_run=False,  # Set to True to preview changes
)

print(f"Applied {changes} schema changes")
# Applied 2 schema changes
# - CREATE TABLE users
# - CREATE TABLE users_audit (for copy_on_change)
```

### 3. CRUD Operations with Audit Trail

```python
from uuid import uuid4
from ff_storage import PydanticRepository

# Create repository (tenant-scoped)
org_id = uuid4()  # Tenant ID
user_id = uuid4()  # Current user (for audit trail)

repo = PydanticRepository(
    User,
    db_pool,
    tenant_id=org_id,
)

# CREATE
alice = User(
    email="alice@example.com",
    name="Alice Smith",
    age=30,
    role="admin",
)
created = await repo.create(alice, user_id=user_id)
print(f"Created user: {created.id}")

# UPDATE (field-level audit)
created.age = 31
created.role = "superadmin"
updated = await repo.update(created.id, created, user_id=user_id)
print(f"Updated user: {updated.name}, age={updated.age}, role={updated.role}")

# GET
user = await repo.get(created.id)
print(f"Retrieved: {user.name}")

# LIST with filters
admins = await repo.list(
    filters={"role": "superadmin"},
    limit=10,
)
print(f"Found {len(admins)} superadmins")

# SOFT DELETE
deleted = await repo.delete(created.id, user_id=user_id)
print(f"Soft deleted: {deleted}")

# Verify deletion (excluded by default)
user = await repo.get(created.id)
print(f"User after delete: {user}")  # None

# Get including deleted
user_deleted = await repo.get(created.id, include_deleted=True)
print(f"User with include_deleted: {user_deleted.name}")
print(f"Deleted at: {user_deleted.deleted_at}")

# RESTORE
restored = await repo.restore(created.id)
print(f"Restored: {restored.name}")
```

### 4. Query Audit History

```python
# Get full audit history
history = await repo.get_audit_history(created.id)
print(f"Total audit entries: {len(history)}")

for entry in history:
    print(f"{entry.changed_at}: {entry.field_name} "
          f"changed from {entry.old_value} to {entry.new_value} "
          f"(by {entry.changed_by})")

# Output:
# 2025-10-20 12:00:00: age changed from 30 to 31 (by user_id)
# 2025-10-20 12:00:00: role changed from admin to superadmin (by user_id)
# 2025-10-20 12:01:00: deleted_at changed from None to 2025-10-20 12:01:00 (by user_id)

# Get history for specific field
age_history = await repo.get_field_history(created.id, "age")
for entry in age_history:
    print(f"{entry.changed_at}: {entry.old_value} → {entry.new_value}")
```

## Complete Example

```python
import asyncio
from uuid import uuid4
from ff_storage import (
    PydanticModel,
    Field,
    PydanticRepository,
    PostgresPool,
    SchemaManager,
)

class User(PydanticModel):
    __table_name__ = "users"
    __temporal_strategy__ = "copy_on_change"

    email: str = Field(max_length=255, db_unique=True, db_index=True)
    name: str = Field(max_length=255)
    age: int = Field(ge=0, le=150)
    role: str = Field(max_length=50, default="user", db_index=True)

async def main():
    # Setup
    org_id = uuid4()
    user_id = uuid4()

    db_pool = PostgresPool(
        dbname="fenix_dev",
        user="fenix",
        password="password",
        host="localhost",
    )
    db_pool.connect()

    # Schema sync
    manager = SchemaManager(db_pool)
    manager.sync_schema(models=[User], dry_run=False)

    # Repository
    repo = PydanticRepository(User, db_pool, tenant_id=org_id)

    # CRUD
    alice = User(email="alice@example.com", name="Alice", age=30, role="admin")
    created = await repo.create(alice, user_id=user_id)

    created.age = 31
    updated = await repo.update(created.id, created, user_id=user_id)

    # Audit history
    history = await repo.get_audit_history(created.id)
    for entry in history:
        print(f"{entry.field_name}: {entry.old_value} → {entry.new_value}")

    # Cleanup
    db_pool.close_connection()

if __name__ == "__main__":
    asyncio.run(main())
```

## Key Features

### Field Metadata

Use enhanced `Field()` for complete SQL control:

```python
from ff_storage import Field

class Product(PydanticModel):
    # Foreign key with CASCADE
    category_id: UUID = Field(
        db_foreign_key="public.categories(id)",
        db_on_delete="CASCADE",
        db_index=True,
    )

    # Decimal with precision
    price: Decimal = Field(
        ge=0,
        db_precision=10,
        db_scale=2,
        db_check="price >= 0",  # CHECK constraint
    )

    # Partial index for active records
    status: str = Field(
        db_index=True,
        db_index_where="deleted_at IS NULL",  # Partial index
    )
```

### Temporal Strategies

Choose the right strategy for your use case:

```python
# None: Standard CRUD (no history)
__temporal_strategy__ = "none"

# Copy-on-Change: Field-level audit trail
__temporal_strategy__ = "copy_on_change"

# SCD2: Immutable version history (time travel)
__temporal_strategy__ = "scd2"
```

See [Strategy Selection Guide](guides/strategy_selection.md) for details.

### Multi-Tenant by Default

```python
# Tenant ID auto-injected and filtered
repo = PydanticRepository(User, db_pool, tenant_id=org_id)

# All operations scoped to tenant
users = await repo.list()  # Only returns org_id's users
```

### Soft Delete by Default

```python
# Soft delete (sets deleted_at)
await repo.delete(user_id, user_id=admin_id)

# Excluded by default
user = await repo.get(user_id)  # None

# Include deleted
user = await repo.get(user_id, include_deleted=True)

# Restore
await repo.restore(user_id)
```

## Next Steps

- **[Strategy Selection Guide](guides/strategy_selection.md)** - Choose the right temporal strategy
- **[API Reference](api/pydantic_orm.md)** - Complete API documentation
- **[SCD2 Foreign Keys](guides/scd2_foreign_keys.md)** - FK patterns for versioned data
- **[Production Deployment](guides/production_deployment.md)** - Operational best practices
- **[Examples](examples/)** - More complete examples

## Troubleshooting

### Validation Errors

```python
from ff_storage import TemporalValidator

# Validate model configuration
errors = TemporalValidator.validate_model(User)
for error in errors:
    if error.level == "error":
        raise ValueError(error.message)
    print(f"{error.level.upper()}: {error.message}")
```

### Schema Sync Issues

```python
# Dry run to preview changes
manager.sync_schema(models=[User], dry_run=True)

# Check logs for errors
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Connection Pooling

```python
# Async pool for high concurrency
from ff_storage import PostgresPool

pool = PostgresPool(
    dbname="fenix_dev",
    user="fenix",
    password="password",
    host="localhost",
    min_size=10,  # Minimum pool size
    max_size=20,  # Maximum pool size
)
await pool.connect()
```

---

**Ready to build!** You now have a production-ready Pydantic ORM with temporal data management. 🚀
