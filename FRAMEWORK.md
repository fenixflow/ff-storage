# FF-STORAGE FRAMEWORK GUIDE

> **For AI Assistants**: This document is your comprehensive guide to ff-storage v4.7.0, a Pydantic-first ORM with built-in temporal versioning, fluent Query Builder, ORM-style Relationships, and Transaction management. Read this before writing any ff-storage code.

---

## IDENTITY

**ff-storage** is a Python ORM that treats **Pydantic models as the single source of truth** for both API validation AND database schema. It provides:

- Automatic schema synchronization (Terraform-like)
- Built-in temporal versioning (audit trails, SCD2 history)
- Multi-tenant isolation
- Soft delete with restore capability
- Multi-database support (PostgreSQL, MySQL, SQL Server)
- **Fluent Query Builder** with type-safe filtering (v4.7.0)
- **ORM-style Relationships** with eager loading (v4.7.0)
- **Transaction management** with savepoints (v4.7.0)
- **Bulk operations** for batch inserts/updates (v4.7.0)

**Philosophy**: Define your model once in Pydantic, get validation, serialization, AND database schema automatically.

---

## QUICK REFERENCE

### Imports
```python
# Core ORM
from ff_storage import PydanticModel, PydanticRepository, Field
from ff_storage.db.connections.postgres import PostgresPool
from ff_storage.db.schema_sync import SchemaManager

# Query Builder (v4.7.0)
from ff_storage import Query, F, AND, OR, func

# Relationships (v4.7.0)
from ff_storage import Relationship

# Transactions (v4.7.0)
from ff_storage import Transaction, UnitOfWork, IsolationLevel

# Standard library
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from typing import Optional
```

### Model Class Variables
| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `__table_name__` | `str` | Class name lowercase | Database table name |
| `__schema__` | `str` | `"public"` | Database schema |
| `__temporal_strategy__` | `str` | `"none"` | `"none"`, `"copy_on_change"`, or `"scd2"` |
| `__soft_delete__` | `bool` | `True` | Enable soft delete (deleted_at field) |
| `__multi_tenant__` | `bool` | `True` | Enable tenant isolation (tenant_id field) |
| `__tenant_field__` | `str` | `"tenant_id"` | Name of tenant column |

### Temporal Strategy Comparison
| Strategy | Use Case | History Storage | Query Pattern |
|----------|----------|-----------------|---------------|
| `none` | Simple data, no audit needed | None | Direct CRUD |
| `copy_on_change` | Field-level audit trail | Separate `{table}_audit` table | Current in main, history in audit |
| `scd2` | Full version history, time-travel | Same table with versions | `valid_to IS NULL` for current |

---

## CORE CONCEPTS

### 1. PydanticModel Base Class

All models inherit from `PydanticModel`:

```python
from ff_storage import PydanticModel, Field
from decimal import Decimal
from uuid import UUID

class Product(PydanticModel):
    # Table configuration
    __table_name__ = "products"
    __schema__ = "inventory"
    __temporal_strategy__ = "scd2"
    __soft_delete__ = True
    __multi_tenant__ = True

    # Your fields (Pydantic validation + DB schema)
    name: str = Field(max_length=255)
    price: Decimal = Field(
        gt=Decimal("0"),
        json_schema_extra={"db_precision": 10, "db_scale": 2}
    )
    sku: str = Field(
        max_length=50,
        json_schema_extra={"db_unique": True, "db_index": True}
    )
    category_id: UUID | None = Field(
        default=None,
        json_schema_extra={
            "db_foreign_key": "inventory.categories.id",
            "db_on_delete": "SET NULL"
        }
    )
```

**Auto-Injected Fields** (DO NOT define these yourself):
| Field | Type | Injected When |
|-------|------|---------------|
| `id` | `UUID` | Always (primary key) |
| `created_at` | `datetime` | Always |
| `updated_at` | `datetime` | Always |
| `created_by` | `UUID \| None` | Always |
| `updated_by` | `UUID \| None` | Always |
| `tenant_id` | `UUID` | When `__multi_tenant__ = True` |
| `deleted_at` | `datetime \| None` | When `__soft_delete__ = True` |
| `deleted_by` | `UUID \| None` | When `__soft_delete__ = True` |
| `version` | `int` | When `__temporal_strategy__ = "scd2"` |
| `valid_from` | `datetime` | When `__temporal_strategy__ = "scd2"` |
| `valid_to` | `datetime \| None` | When `__temporal_strategy__ = "scd2"` |

---

### 2. Temporal Strategies

#### Strategy: `none`
Basic CRUD with timestamps. No history tracking.

```python
class SimpleLog(PydanticModel):
    __temporal_strategy__ = "none"
    message: str
```

#### Strategy: `copy_on_change`
Field-level audit trail. Main table has current values; changes logged to `{table}_audit`.

```python
class FXRate(PydanticModel):
    __temporal_strategy__ = "copy_on_change"
    __multi_tenant__ = False  # Global reference data

    currency_from: str = Field(max_length=3)
    currency_to: str = Field(max_length=3)
    rate: Decimal = Field(json_schema_extra={"db_precision": 18, "db_scale": 8})
```

**Audit table structure** (`fx_rates_audit`):
```
audit_id | record_id | field_name | old_value | new_value | changed_at | changed_by | transaction_id
```

**Use when**: You need to know WHAT changed and WHEN, but don't need full snapshots.

#### Strategy: `scd2` (Slowly Changing Dimension Type 2)
Immutable versions in the same table. Each update creates a new row.

```python
class Country(PydanticModel):
    __temporal_strategy__ = "scd2"
    __multi_tenant__ = False

    code: str = Field(
        max_length=3,
        json_schema_extra={
            "db_unique": True,
            "db_index_where": "valid_to IS NULL"  # Only current version
        }
    )
    name: str = Field(max_length=255)
    capital_lat: Decimal | None = Field(default=None)
    capital_lon: Decimal | None = Field(default=None)
```

**Table structure**:
```
id | version | valid_from | valid_to | code | name | capital_lat | capital_lon | deleted_at | ...
```

**Use when**: You need time-travel queries ("What was the state on 2024-01-15?") or full audit history.

---

### 3. Repository Pattern

#### Basic Usage
```python
from ff_storage import PydanticRepository

# Create repository with tenant scope
repo = PydanticRepository(
    model_class=Product,
    db_pool=db_pool,
    tenant_id=org_id  # UUID - strict single-tenant scope
)

# CRUD operations
product = Product(name="Widget", price=Decimal("99.99"), sku="WDG-001")
created = await repo.create(product, user_id=current_user.id)

# Get by ID
fetched = await repo.get(created.id)

# List with filters
widgets = await repo.list(
    filters={"category_id": category_uuid},
    limit=50,
    offset=0
)

# Update (creates audit trail or new SCD2 version)
created.price = Decimal("89.99")
updated = await repo.update(created.id, created, user_id=current_user.id)

# Soft delete
await repo.delete(created.id, user_id=current_user.id)

# Restore soft-deleted record
await repo.restore(created.id)

# Include deleted in queries
all_products = await repo.list(filters=None, include_deleted=True)
```

#### Tenant Scoping Modes

**Strict Scope** (single tenant - use for normal operations):
```python
repo = PydanticRepository(Product, db_pool, tenant_id=org_id)
# - Reads: Filters to this tenant only
# - Writes: Forces tenant_id on all records
```

**Permissive Scope** (multi-tenant - use for admin/B2B):
```python
repo = PydanticRepository(Product, db_pool, tenant_ids=[tenant1, tenant2])
# - Reads: Filters with IN clause
# - Writes: Validates tenant_id is in the list
```

**No Tenant** (global data):
```python
repo = PydanticRepository(Country, db_pool, tenant_id=None)
# - For reference data shared across all tenants
# - Model should have __multi_tenant__ = False
```

#### Repository Methods Reference

```python
# CREATE
await repo.create(model: T, user_id: UUID | None = None) -> T
await repo.create_many(models: list[T], user_id: UUID | None = None) -> list[T]

# READ
await repo.get(id: UUID, include_deleted: bool = False) -> T | None
await repo.list(
    filters: dict | None = None,
    limit: int = 100,
    offset: int = 0,
    include_deleted: bool = False
) -> list[T]

# UPDATE
await repo.update(id: UUID, model: T, user_id: UUID | None = None) -> T

# DELETE
await repo.delete(id: UUID, user_id: UUID | None = None) -> bool
await repo.restore(id: UUID) -> T | None

# TEMPORAL (strategy-dependent)
await repo.get_audit_history(record_id: UUID) -> list[AuditEntry]  # copy_on_change
await repo.get_version_history(id: UUID) -> list[T]  # scd2
```

---

### 4. Schema Synchronization

ff-storage uses a Terraform-like approach: define desired state in Pydantic, sync to database.

```python
from ff_storage.db.schema_sync import SchemaManager

async def sync_schemas(db_pool):
    async with db_pool.acquire() as conn:
        manager = SchemaManager(conn)

        # Dry run first (preview changes)
        changes = await manager.sync_schema(
            models=[Product, Category, Order],
            dry_run=True
        )
        print(f"Would make {changes} changes")

        # Apply changes
        changes = await manager.sync_schema(
            models=[Product, Category, Order],
            dry_run=False
        )
        print(f"Applied {changes} changes")
```

**What gets synced**:
- Tables and columns
- Indexes (including partial indexes)
- Foreign keys
- Check constraints
- Auxiliary tables (e.g., `_audit` tables for copy_on_change)

---

### 5. Query Builder (v4.7.0)

The Query Builder provides a fluent, type-safe API for database queries as an alternative to `repo.list(filters={...})`.

#### Basic Usage
```python
from ff_storage import Query, F

# Simple filtering
results = await (
    Query(Product)
    .filter(F.price > 100)
    .filter(F.status == "active")
    .order_by(F.created_at.desc())
    .limit(10)
    .execute(db_pool, tenant_id=tenant)
)

# Convenience methods
product = await Query(Product).filter(F.sku == "ABC123").first(db_pool, tenant_id=tenant)
exists = await Query(Product).filter(F.sku == "ABC123").exists(db_pool, tenant_id=tenant)
count = await Query(Product).filter(F.status == "active").count(db_pool, tenant_id=tenant)
```

#### Filter Operators
```python
# Comparison
F.price > 100           # Greater than
F.price >= 100          # Greater than or equal
F.price < 100           # Less than
F.price <= 100          # Less than or equal
F.price == 100          # Equal
F.price != 100          # Not equal

# String matching
F.name.contains("widget")      # LIKE '%widget%'
F.name.icontains("widget")     # ILIKE '%widget%' (case-insensitive)
F.name.startswith("Pro")       # LIKE 'Pro%'
F.name.endswith("Plus")        # LIKE '%Plus'

# Collections
F.status.in_(["active", "pending"])     # IN clause
F.status.not_in_(["deleted", "archived"])
F.price.between(10, 100)                # BETWEEN

# Null checks
F.deleted_at.is_null()
F.category_id.is_not_null()
```

#### Composite Expressions
```python
from ff_storage import AND, OR

# Combine with AND (implicit when chaining .filter())
Query(Product).filter(AND(F.price > 100, F.status == "active"))

# Combine with OR
Query(Product).filter(OR(F.status == "sale", F.price < 50))

# Complex nested logic
Query(Product).filter(
    AND(
        F.category_id == category_id,
        OR(F.status == "active", F.featured == True)
    )
)
```

#### Ordering and Pagination
```python
# Single order
Query(Product).order_by(F.price.asc())
Query(Product).order_by(F.created_at.desc())

# Multiple orders
Query(Product).order_by(F.category_id.asc(), F.price.desc())

# Pagination
Query(Product).limit(20).offset(40)  # Page 3 with 20 per page
```

#### Aggregations
```python
from ff_storage import func

# Count
total = await Query(Product).select(func.count()).scalar(db_pool, tenant_id=tenant)

# With grouping
stats = await (
    Query(Product)
    .group_by(F.category_id)
    .select(
        F.category_id,
        func.count().label("total"),
        func.avg(F.price).label("avg_price"),
        func.sum(F.quantity).label("total_quantity")
    )
    .execute(db_pool, tenant_id=tenant)
)
```

#### Row Locking
```python
# SELECT ... FOR UPDATE
product = await (
    Query(Product)
    .filter(F.id == product_id)
    .for_update()
    .first(db_pool, tenant_id=tenant)
)

# Non-blocking variants
.for_update_nowait()      # Fail immediately if locked
.for_update_skip_locked() # Skip locked rows
```

#### Query vs Repository
| Use Case | Repository | Query Builder |
|----------|------------|---------------|
| Simple CRUD | ✅ `repo.get()`, `repo.create()` | - |
| Simple filters | ✅ `repo.list(filters={...})` | ✅ Works too |
| Complex filters (OR, nested) | ❌ Limited | ✅ `AND()`, `OR()` |
| JOINs | ❌ | ✅ `.join()` |
| Aggregations | ❌ | ✅ `func.count()`, etc. |
| Row locking | ❌ | ✅ `.for_update()` |

**Automatic Safety**: Query Builder automatically applies:
- SCD2 filter (`valid_to IS NULL`) for temporal models
- Soft delete filter (`deleted_at IS NULL`)
- Tenant isolation (`tenant_id = ?`)

---

### 6. Relationships (v4.7.0)

Define ORM-style relationships between models with automatic eager loading to prevent N+1 queries.

#### Defining Relationships
```python
from ff_storage import PydanticModel, Relationship, Field
from uuid import UUID

class Author(PydanticModel):
    __table_name__ = "authors"

    name: str = Field(max_length=255)
    # One-to-many: Author has many Posts
    posts: list["Post"] = Relationship(back_populates="author")

class Post(PydanticModel):
    __table_name__ = "posts"

    title: str = Field(max_length=255)
    author_id: UUID  # Foreign key (auto-detected from field name)
    # Many-to-one: Post belongs to Author
    author: "Author" = Relationship(back_populates="posts")
```

#### Relationship Types

**One-to-Many** (collection on parent):
```python
class Author(PydanticModel):
    posts: list["Post"] = Relationship(back_populates="author")
```

**Many-to-One** (reference on child):
```python
class Post(PydanticModel):
    author_id: UUID
    author: "Author" = Relationship(back_populates="posts")
```

**Many-to-Many** (junction table):
```python
class Post(PydanticModel):
    tags: list["Tag"] = Relationship(
        link_model="PostTag",
        link_local_key="post_id",
        link_remote_key="tag_id"
    )
```

#### Eager Loading (N+1 Prevention)
```python
# Without eager loading: 1 + N queries (N+1 problem)
authors = await Query(Author).execute(db_pool)
for author in authors:
    print(author.posts)  # Each access = 1 query!

# With eager loading: 2 queries total
authors = await (
    Query(Author)
    .load(["posts"])
    .execute(db_pool)
)
for author in authors:
    print(author.posts)  # Already loaded!

# Nested loading: 3 queries total
authors = await (
    Query(Author)
    .load(["posts", "posts.comments"])
    .execute(db_pool)
)
```

#### Foreign Key Auto-Detection
The `author_id` field is automatically detected as the FK for `author` relationship:
```python
author_id: UUID              # FK field
author: "Author" = Relationship(...)  # Relationship uses author_id
```

Override with explicit `foreign_key` parameter if needed:
```python
creator: "User" = Relationship(foreign_key="created_by_user_id")
```

---

### 7. Transactions (v4.7.0)

Full transaction support with automatic commit/rollback and savepoints for partial rollback.

#### Basic Transaction
```python
from ff_storage import Transaction

async with Transaction(db_pool) as txn:
    repo = PydanticRepository(Author, db_pool, connection=txn.connection)
    author = await repo.create(Author(name="John"))

    post_repo = PydanticRepository(Post, db_pool, connection=txn.connection)
    await post_repo.create(Post(title="Hello", author_id=author.id))
    # Auto-commits on successful exit
    # Auto-rollbacks on exception
```

#### Isolation Levels
```python
from ff_storage import Transaction, IsolationLevel

# Default: READ COMMITTED
async with Transaction(db_pool) as txn:
    ...

# Stricter isolation for financial operations
async with Transaction(db_pool, isolation=IsolationLevel.SERIALIZABLE) as txn:
    ...

# Available levels:
# - IsolationLevel.READ_UNCOMMITTED
# - IsolationLevel.READ_COMMITTED (default)
# - IsolationLevel.REPEATABLE_READ
# - IsolationLevel.SERIALIZABLE
```

#### Savepoints (Partial Rollback)
```python
async with Transaction(db_pool) as txn:
    repo = PydanticRepository(Author, db_pool, connection=txn.connection)
    author = await repo.create(Author(name="Jane"))  # Will be committed

    try:
        async with txn.savepoint():
            # This might fail
            risky_operation = await repo.create(Author(name="duplicate"))
    except IntegrityError:
        pass  # Only savepoint rolled back, author still exists

    # Transaction continues, author will be committed
```

#### Unit of Work Pattern
For complex multi-repository operations, use `UnitOfWork` which manages repository instances and ensures all use the same transaction:

```python
from ff_storage import UnitOfWork

async with UnitOfWork(db_pool) as uow:
    # Repositories are auto-bound to the transaction
    author_repo = uow.repository(Author, tenant_id=tenant)
    post_repo = uow.repository(Post, tenant_id=tenant)

    author = await author_repo.create(Author(name="Jane"))
    await post_repo.create(Post(title="First Post", author_id=author.id))

    # Read-your-writes: can immediately query what you just wrote
    posts = await post_repo.list(filters={"author_id": author.id})
    # Auto-commits all changes on exit
```

---

### 8. Bulk Operations (v4.7.0)

Efficient batch operations for inserting or updating many records.

#### Bulk Insert
```python
from ff_storage.query.bulk import bulk_insert

products = [
    Product(name="Widget A", price=Decimal("10.00")),
    Product(name="Widget B", price=Decimal("20.00")),
    Product(name="Widget C", price=Decimal("30.00")),
]

# Insert all in efficient batches (default: 1000 per batch)
created = await bulk_insert(
    model_class=Product,
    records=products,
    db_pool=db_pool,
    tenant_id=tenant,
    user_id=current_user.id
)
```

#### Bulk Update
```python
from ff_storage.query.bulk import bulk_update

# Update all matching records
updated_count = await bulk_update(
    model_class=Product,
    updates={"status": "archived"},
    filters={"category_id": old_category_id},
    db_pool=db_pool,
    tenant_id=tenant
)
```

---

## FIELD METADATA REFERENCE

Use `json_schema_extra` in `Field()` for database-specific configuration:

```python
from ff_storage import Field

# Basic field with DB metadata
email: str = Field(
    max_length=255,
    json_schema_extra={
        "db_unique": True,
        "db_index": True,
        "db_nullable": False
    }
)
```

### All Field Options

| Option | Type | Description |
|--------|------|-------------|
| `db_type` | `str` | Override SQL type (e.g., `"TEXT"`, `"JSONB"`) |
| `db_default` | `str` | SQL default expression (e.g., `"NOW()"`, `"gen_random_uuid()"`) |
| `db_nullable` | `bool` | Override nullable (normally inferred from `Optional`) |
| `db_precision` | `int` | Numeric precision (total digits) |
| `db_scale` | `int` | Numeric scale (decimal places) |
| `db_primary_key` | `bool` | Mark as primary key |
| `db_unique` | `bool` | Add UNIQUE constraint |
| `db_index` | `bool` | Create index on column |
| `db_index_name` | `str` | Custom index name |
| `db_index_where` | `str` | Partial index condition |
| `db_index_columns` | `list[str]` | Composite index columns |
| `db_foreign_key` | `str` | FK reference (`"schema.table.column"`) |
| `db_on_delete` | `str` | FK action: `"CASCADE"`, `"SET NULL"`, `"RESTRICT"` |
| `db_check` | `str` | CHECK constraint expression |

### Composite/Partial Index Example
```python
class Carrier(PydanticModel):
    __temporal_strategy__ = "scd2"

    carrier_identifier: str = Field(
        max_length=50,
        json_schema_extra={
            "db_unique": True,
            "db_index_name": "idx_carrier_identifier_current",
            "db_index_where": "valid_to IS NULL"  # Only index current versions
        }
    )
```

---

## TYPE MAPPING

### Python to PostgreSQL

| Python Type | PostgreSQL Type |
|-------------|-----------------|
| `str` | `VARCHAR(n)` or `TEXT` |
| `int` | `INTEGER` |
| `float` | `DOUBLE PRECISION` |
| `bool` | `BOOLEAN` |
| `Decimal` | `NUMERIC(precision, scale)` |
| `UUID` | `UUID` |
| `datetime` | `TIMESTAMP WITH TIME ZONE` |
| `date` | `DATE` |
| `time` | `TIME` |
| `bytes` | `BYTEA` |
| `dict` | `JSONB` |
| `list` | `JSONB` (or native array for simple types) |
| `list[UUID]` | `UUID[]` |
| `list[str]` | `TEXT[]` |
| `list[int]` | `INTEGER[]` |
| `Optional[T]` | Same as `T` but nullable |

### Override Type
```python
# Force JSONB for complex nested data
metadata: dict = Field(
    default_factory=dict,
    json_schema_extra={"db_type": "JSONB"}
)

# Force TEXT instead of VARCHAR
description: str = Field(
    json_schema_extra={"db_type": "TEXT"}
)
```

---

## FASTAPI INTEGRATION

### Lifespan Pattern
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from ff_storage import PydanticRepository
from ff_storage.db.connections.postgres import PostgresPool
from ff_storage.db.schema_sync import SchemaManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db_pool = PostgresPool(
        dbname="myapp",
        user="postgres",
        password="secret",
        host="localhost",
        min_size=5,
        max_size=20
    )
    await db_pool.connect()
    app.state.db = db_pool

    # Sync schema on startup
    async with db_pool.acquire() as conn:
        manager = SchemaManager(conn)
        await manager.sync_schema(models=[Product, Order, User])

    yield

    # Shutdown
    await db_pool.disconnect()

app = FastAPI(lifespan=lifespan)

# Dependency
async def get_db() -> PostgresPool:
    return app.state.db

DbPool = Annotated[PostgresPool, Depends(get_db)]
```

### Route Example
```python
from fastapi import APIRouter, HTTPException
from uuid import UUID

router = APIRouter(prefix="/api/v1/products", tags=["products"])

@router.post("")
async def create_product(
    data: ProductCreateRequest,
    db_pool: DbPool,
    user: CurrentUser
) -> ProductResponse:
    repo = PydanticRepository(Product, db_pool, tenant_id=user.tenant_id)
    product = Product(**data.model_dump())
    created = await repo.create(product, user_id=user.id)
    return ProductResponse.model_validate(created)

@router.get("/{product_id}")
async def get_product(
    product_id: UUID,
    db_pool: DbPool,
    user: CurrentUser
) -> ProductResponse:
    repo = PydanticRepository(Product, db_pool, tenant_id=user.tenant_id)
    product = await repo.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductResponse.model_validate(product)

@router.put("/{product_id}")
async def update_product(
    product_id: UUID,
    data: ProductUpdateRequest,
    db_pool: DbPool,
    user: CurrentUser
) -> ProductResponse:
    repo = PydanticRepository(Product, db_pool, tenant_id=user.tenant_id)
    existing = await repo.get(product_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")

    # Partial update pattern
    update_dict = data.model_dump(exclude_unset=True)
    updated_model = existing.model_copy(update=update_dict)
    result = await repo.update(product_id, updated_model, user_id=user.id)
    return ProductResponse.model_validate(result)

@router.delete("/{product_id}")
async def delete_product(
    product_id: UUID,
    db_pool: DbPool,
    user: CurrentUser
) -> dict:
    repo = PydanticRepository(Product, db_pool, tenant_id=user.tenant_id)
    await repo.delete(product_id, user_id=user.id)
    return {"deleted": True}
```

### SCD2 History Endpoint
```python
@router.get("/{product_id}/history")
async def get_product_history(
    product_id: UUID,
    db_pool: DbPool,
    user: CurrentUser
) -> list[ProductVersionResponse]:
    repo = PydanticRepository(Product, db_pool, tenant_id=user.tenant_id)
    versions = await repo.get_version_history(product_id)
    return [
        ProductVersionResponse(
            version=v.version,
            valid_from=v.valid_from,
            valid_to=v.valid_to,
            **v.model_dump(exclude={"version", "valid_from", "valid_to"})
        )
        for v in versions
    ]
```

---

## COMMON PATTERNS

### Upsert Pattern
```python
async def upsert_by_sku(self, product: Product, user_id: UUID) -> tuple[Product, bool]:
    """Returns (product, was_created)"""
    existing = await self.get_by_sku(product.sku)
    if existing is None:
        created = await self.create(product, user_id=user_id)
        return created, True

    # Check if data actually changed
    if existing.name == product.name and existing.price == product.price:
        return existing, False

    # Update (creates audit trail / new version)
    product.id = existing.id
    updated = await self.update(existing.id, product, user_id=user_id)
    return updated, False
```

### Partial Update Pattern
```python
# Use Pydantic's model_copy for clean partial updates
update_data = request.model_dump(exclude_unset=True)
updated_model = existing.model_copy(update=update_data)
result = await repo.update(existing.id, updated_model, user_id=user_id)
```

### Custom Repository with Business Logic
```python
class ProductRepository(PydanticRepository[Product]):
    def __init__(self, db_pool, tenant_id: UUID, logger=None):
        super().__init__(
            model_class=Product,
            db_pool=db_pool,
            tenant_id=tenant_id,
            logger=logger
        )

    async def get_by_sku(self, sku: str) -> Product | None:
        items = await self.list(filters={"sku": sku}, limit=1)
        return items[0] if items else None

    async def list_by_category(self, category_id: UUID) -> list[Product]:
        return await self.list(filters={"category_id": category_id})

    async def get_price_history(self, product_id: UUID) -> list[dict]:
        """Get price changes from audit table (copy_on_change strategy)"""
        # For copy_on_change, query the audit table directly
        query = """
            SELECT changed_at, old_value, new_value, changed_by
            FROM inventory.products_audit
            WHERE record_id = $1 AND field_name = 'price'
            ORDER BY changed_at DESC
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, product_id)
        return [dict(row) for row in rows]
```

### Global Reference Data Pattern
```python
class Country(PydanticModel):
    __temporal_strategy__ = "scd2"
    __multi_tenant__ = False  # No tenant isolation
    __soft_delete__ = True

    code: str = Field(max_length=3, json_schema_extra={"db_unique": True})
    name: str = Field(max_length=255)

# Repository without tenant scope
repo = PydanticRepository(Country, db_pool, tenant_id=None)
```

---

## ANTI-PATTERNS (DON'T DO THESE)

### 1. Don't Define Auto-Injected Fields
```python
# WRONG - these are auto-injected
class Product(PydanticModel):
    id: UUID = Field(default_factory=uuid4)  # DON'T
    created_at: datetime = Field(...)        # DON'T
    tenant_id: UUID                          # DON'T
    version: int = 1                         # DON'T (for SCD2)
```

### 2. Don't Mix Tenant Scoping Modes
```python
# WRONG - can't use both
repo = PydanticRepository(Product, db_pool,
    tenant_id=org_id,      # Can't use both
    tenant_ids=[org1, org2] # Can't use both
)
```

### 3. Don't Forget Partial Index for SCD2
```python
# WRONG - unique constraint conflicts with versions
class Product(PydanticModel):
    __temporal_strategy__ = "scd2"
    sku: str = Field(json_schema_extra={"db_unique": True})  # Will fail!

# CORRECT - partial index on current version only
class Product(PydanticModel):
    __temporal_strategy__ = "scd2"
    sku: str = Field(json_schema_extra={
        "db_unique": True,
        "db_index_where": "valid_to IS NULL"  # Only current
    })
```

### 4. Don't Manually Manage Temporal Fields
```python
# WRONG - let the strategy handle these
product.valid_from = datetime.now()
product.valid_to = None
product.version = 2
await repo.update(...)

# CORRECT - just update the data
product.price = new_price
await repo.update(product.id, product, user_id=user.id)
# Strategy automatically manages temporal fields
```

---

## TROUBLESHOOTING

### Schema Drift Detected
**Problem**: Schema sync reports differences that shouldn't exist.
**Solution**: This was largely fixed in v3.4.0. Ensure you're on latest version. The normalizer handles PostgreSQL type aliases (e.g., `float8` = `double precision`).

### Tenant Isolation Error
**Problem**: `TenantNotConfigured` or `TenantIsolationError`
**Solution**:
- For multi-tenant models, always pass `tenant_id` or `tenant_ids` to repository
- For global data, set `__multi_tenant__ = False` on model AND pass `tenant_id=None`

### Version Conflict
**Problem**: `TemporalVersionConflict` during update
**Solution**: Re-fetch the record and retry. Another process updated it. Consider implementing optimistic locking in your application layer.

### Unique Constraint Violation (SCD2)
**Problem**: Can't insert because unique constraint fails
**Solution**: For SCD2 models, add `db_index_where: "valid_to IS NULL"` to unique fields so only current versions are constrained.

---

## FILE STRUCTURE (ff-storage internals)

```
ff-storage/src/ff_storage/
├── pydantic_support/
│   ├── base.py           # PydanticModel base class
│   ├── repository.py     # PydanticRepository
│   ├── introspector.py   # Model → Schema extraction
│   ├── type_mapping.py   # Python → SQL type mapping
│   └── field_metadata.py # Field() with DB metadata
├── query/                    # Query Builder (v4.7.0)
│   ├── builder.py            # Query class with fluent API
│   ├── expressions.py        # FilterExpression, FieldProxy, F
│   ├── executor.py           # QueryExecutor with temporal awareness
│   ├── bulk.py               # bulk_insert, bulk_update
│   ├── aggregations.py       # AggregateExpression, GroupByClause
│   └── functions.py          # func factory (count, sum, avg, etc.)
├── relationships/            # Relationships (v4.7.0)
│   ├── descriptor.py         # Relationship class
│   ├── loader.py             # RelationshipLoader (N+1 prevention)
│   ├── registry.py           # RelationshipRegistry
│   └── config.py             # RelationshipConfig
├── transactions/             # Transactions (v4.7.0)
│   ├── context.py            # Transaction context manager
│   ├── unit_of_work.py       # UnitOfWork pattern
│   ├── savepoint.py          # Savepoint class
│   └── isolation.py          # IsolationLevel enum
├── temporal/
│   ├── strategies/
│   │   ├── none.py           # No temporal tracking
│   │   ├── copy_on_change.py # Field-level audit
│   │   └── scd2.py           # Version history
│   ├── repository_base.py    # TemporalRepository
│   └── registry.py           # Strategy factory
├── db/
│   ├── connections/
│   │   └── postgres.py   # PostgresPool
│   ├── query_builder/
│   │   └── postgres.py   # SQL generation
│   └── schema_sync/
│       └── manager.py    # SchemaManager
└── exceptions.py         # FFStorageError hierarchy
```

---

## SUMMARY FOR LLMs

When writing code with ff-storage:

1. **Define models** by inheriting from `PydanticModel` with class variables for config
2. **Choose temporal strategy**: `none` (simple), `copy_on_change` (audit), `scd2` (versions)
3. **Use Field metadata** via `json_schema_extra` for DB-specific settings
4. **Create repositories** with appropriate tenant scoping
5. **Let the framework handle** temporal fields, soft delete, and audit trails
6. **Use partial indexes** with `db_index_where` for SCD2 unique constraints
7. **Sync schema** on app startup with `SchemaManager`
8. **Use Query Builder** for complex queries with `Query(Model).filter(F.field > value)`
9. **Define Relationships** with `Relationship(back_populates="...")` for eager loading
10. **Wrap multi-repo operations** in `Transaction` or `UnitOfWork` for atomicity

The framework handles:
- UUID generation, timestamps, user tracking
- Tenant isolation in queries
- Audit trails and version history
- Schema creation and migration
- Soft delete and restore
- Query Builder temporal/tenant safety (v4.7.0)
- N+1 prevention via relationship eager loading (v4.7.0)
- Transaction commit/rollback (v4.7.0)