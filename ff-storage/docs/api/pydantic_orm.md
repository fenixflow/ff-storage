# Pydantic ORM API Reference

Complete API documentation for ff-storage's Pydantic ORM integration.

## Table of Contents

- [PydanticModel](#pydanticmodel)
- [PydanticRepository](#pydanticrepository)
- [Field Metadata](#field-metadata)
- [Schema Synchronization](#schema-synchronization)

## PydanticModel

Base class for all Pydantic models in ff-storage.

```python
from ff_storage import PydanticModel, Field

class User(PydanticModel):
    __table_name__ = "users"
    __schema__ = "public"
    __temporal_strategy__ = "copy_on_change"
    __soft_delete__ = True
    __multi_tenant__ = True

    email: str = Field(max_length=255, db_unique=True)
    name: str
    age: int = Field(ge=0, le=150)
```

### Class Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `__table_name__` | `str` | `None` | Override table name (default: class_name + 's') |
| `__schema__` | `str` | `"public"` | Database schema |
| `__temporal_strategy__` | `str` | `"none"` | Temporal strategy: "none", "copy_on_change", or "scd2" |
| `__soft_delete__` | `bool` | `True` | Enable soft delete |
| `__multi_tenant__` | `bool` | `True` | Enable multi-tenancy |
| `__tenant_field__` | `str` | `"tenant_id"` | Field name for tenant isolation |

### Inherited Fields

All models automatically include:

```python
id: UUID  # Primary key
created_at: datetime  # Creation timestamp (UTC)
updated_at: datetime  # Last update timestamp (UTC)
created_by: Optional[UUID]  # User who created record
updated_by: Optional[UUID]  # User who last updated
```

### Methods

#### `table_name() -> str`

Get the database table name.

```python
User.table_name()  # Returns: "users"
```

#### `full_table_name() -> str`

Get fully qualified table name with schema.

```python
User.full_table_name()  # Returns: "public.users"
```

#### `get_temporal_fields() -> dict`

Get temporal fields based on strategy and configuration.

```python
fields = User.get_temporal_fields()
# Returns: {"tenant_id": (UUID, None), "deleted_at": (Optional[datetime], None), ...}
```

#### `get_create_table_sql() -> str`

Generate CREATE TABLE SQL for the model.

```python
sql = User.get_create_table_sql()
print(sql)
# CREATE TABLE IF NOT EXISTS public.users (
#     id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#     ...
# );
```

## PydanticRepository

Repository for CRUD operations with temporal management.

```python
from ff_storage import PydanticRepository

repo = PydanticRepository(
    model_class=User,
    db_pool=pool,
    tenant_id=tenant_id,
    logger=logger
)
```

### Constructor Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model_class` | `Type[PydanticModel]` | Yes | Pydantic model class |
| `db_pool` | `Pool` | Yes | Database connection pool |
| `tenant_id` | `UUID` | Conditional | Required if model is multi-tenant |
| `logger` | `Logger` | No | Optional logger instance |

### CRUD Methods

#### `create(model, user_id=None) -> T`

Create a new record.

```python
user = await repo.create(
    User(email="john@example.com", name="John", age=30),
    user_id=admin_id
)
```

#### `update(id, model, user_id=None) -> T`

Update an existing record.

```python
updated = await repo.update(
    user.id,
    User(email="john@example.com", name="John Doe", age=31),
    user_id=admin_id
)
```

#### `delete(id, user_id=None) -> bool`

Delete a record (soft or hard delete based on configuration).

```python
deleted = await repo.delete(user.id, user_id=admin_id)
```

#### `get(id, **kwargs) -> Optional[T]`

Get a record by ID.

```python
user = await repo.get(user_id)

# With additional options
user = await repo.get(
    user_id,
    include_deleted=True,  # Include soft-deleted records
    as_of=datetime(2024, 1, 1)  # Time travel (SCD2 only)
)
```

#### `list(filters=None, limit=100, offset=0, **kwargs) -> List[T]`

List records with optional filters.

```python
users = await repo.list(
    filters={"status": "active"},
    limit=20,
    offset=0,
    include_deleted=False
)
```

#### `count(filters=None, **kwargs) -> int`

Count records matching filters.

```python
total = await repo.count(filters={"role": "admin"})
```

### Soft Delete Methods

#### `restore(id) -> Optional[T]`

Restore a soft-deleted record.

```python
restored = await repo.restore(user_id)
```

### Batch Operations

#### `create_many(models, user_id=None, batch_size=100) -> List[T]`

Create multiple records efficiently.

```python
users = [
    User(email=f"user{i}@example.com", name=f"User {i}", age=20+i)
    for i in range(100)
]

created = await repo.create_many(users, user_id=admin_id)
```

#### `get_many(ids) -> Dict[UUID, Optional[T]]`

Get multiple records by IDs.

```python
results = await repo.get_many([id1, id2, id3])
# Returns: {id1: user1, id2: user2, id3: None}  # id3 not found
```

## Field Metadata

Enhanced field definitions with database metadata.

```python
from ff_storage import Field

class Product(PydanticModel):
    # String with constraints
    name: str = Field(
        max_length=255,
        min_length=1,
        db_index=True,
        db_unique=True
    )

    # Decimal with precision
    price: Decimal = Field(
        decimal_places=2,
        ge=0,
        db_index=True
    )

    # Foreign key
    category_id: UUID = Field(
        db_foreign_key="categories.id",
        db_on_delete="CASCADE"
    )

    # JSON field
    metadata: dict = Field(
        db_type="JSONB",
        default_factory=dict
    )

    # With check constraint
    status: str = Field(
        db_check="status IN ('draft', 'active', 'archived')"
    )
```

### Field Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `max_length` | `int` | Maximum string length |
| `min_length` | `int` | Minimum string length |
| `ge` | `numeric` | Greater than or equal |
| `le` | `numeric` | Less than or equal |
| `decimal_places` | `int` | Decimal precision |
| `db_index` | `bool` | Create database index |
| `db_unique` | `bool` | Unique constraint |
| `db_foreign_key` | `str` | Foreign key reference |
| `db_on_delete` | `str` | FK delete action |
| `db_on_update` | `str` | FK update action |
| `db_check` | `str` | Check constraint SQL |
| `db_type` | `str` | Override SQL type |
| `db_default` | `str` | Database default value |
| `db_partial_index` | `str` | Partial index condition |

## Schema Synchronization

Automatic schema management from Pydantic models.

```python
from ff_storage import SchemaManager

manager = SchemaManager(db_pool)

# Check what changes would be made
changes = await manager.compare_schemas([User, Product], dry_run=True)
for change in changes:
    print(f"{change.type}: {change.description}")

# Apply changes
await manager.sync_schema(models=[User, Product], dry_run=False)
```

### SchemaManager Methods

#### `sync_schema(models, dry_run=True) -> List[Change]`

Synchronize database schema with model definitions.

```python
changes = await manager.sync_schema(
    models=[User, Product, Order],
    dry_run=False  # Actually apply changes
)
```

#### `compare_schemas(models, dry_run=True) -> List[Change]`

Compare models with database schema without applying changes.

```python
changes = await manager.compare_schemas([User])
for change in changes:
    if change.type == "ADD_COLUMN":
        print(f"New column: {change.table}.{change.column}")
```

#### `create_tables(models) -> None`

Create tables for models (including auxiliary tables).

```python
await manager.create_tables([User, Product])
```

## Advanced Usage

### Custom Validators

```python
from pydantic import validator

class User(PydanticModel):
    email: str
    age: int

    @validator('email')
    def validate_email(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email')
        return v.lower()

    @validator('age')
    def validate_age(cls, v):
        if v < 0 or v > 150:
            raise ValueError('Invalid age')
        return v
```

### Computed Fields

```python
from pydantic import computed_field

class Product(PydanticModel):
    price: Decimal
    tax_rate: Decimal = Field(default=Decimal("0.10"))

    @computed_field
    @property
    def total_price(self) -> Decimal:
        return self.price * (1 + self.tax_rate)
```

### Model Inheritance

```python
class BaseModel(PydanticModel):
    """Base for all models in the system."""
    __abstract__ = True  # Don't create table

    status: str = Field(default="active")
    notes: Optional[str] = None

class User(BaseModel):
    __table_name__ = "users"

    email: str
    name: str

class Admin(User):
    __table_name__ = "admins"

    permissions: List[str] = Field(default_factory=list)
    super_admin: bool = Field(default=False)
```

### Database Adapter Usage

```python
from ff_storage.db.adapters import UniversalPool

# Wrap any pool type for cross-database compatibility
universal_pool = UniversalPool(original_pool)

# Now works with PostgreSQL, MySQL, or SQL Server
repo = PydanticRepository(User, universal_pool, tenant_id=tenant_id)
```

## Error Handling

```python
from ff_storage.exceptions import (
    TemporalStrategyError,
    TenantIsolationError,
    TenantNotConfigured,
    ValidationError
)

try:
    user = await repo.create(User(...))
except TenantNotConfigured:
    # Multi-tenant model requires tenant_id
    pass
except TemporalStrategyError as e:
    # Strategy-specific error
    print(f"Strategy error: {e}")
except ValidationError as e:
    # Pydantic validation failed
    print(f"Validation errors: {e.errors()}")
```

## Performance Considerations

### Connection Pooling

```python
# PostgreSQL
from ff_storage.db.postgres import PostgresPool

pool = PostgresPool(
    dbname="mydb",
    user="user",
    password="pass",
    host="localhost",
    min_size=10,
    max_size=50
)

# MySQL
from ff_storage.db.mysql import MySQLPool

pool = MySQLPool(
    dbname="mydb",
    user="user",
    password="pass",
    host="localhost",
    min_size=10,
    max_size=50
)
```

### Caching

```python
repo = PydanticRepository(
    User,
    db_pool,
    tenant_id=tenant_id,
    cache_enabled=True,
    cache_ttl=300  # 5 minutes
)

# First call hits database
user1 = await repo.get(user_id)

# Second call uses cache (no database hit)
user2 = await repo.get(user_id)

# Invalidate cache manually if needed
await repo.invalidate_cache(pattern=f"id={user_id}")
```

### Batch Operations

```python
# Efficient batch creation
users = [User(...) for _ in range(1000)]
created = await repo.create_many(
    users,
    batch_size=100  # Process in batches of 100
)

# Efficient batch fetching
ids = [user.id for user in created]
fetched = await repo.get_many(ids)
```

## Migration from Raw SQL

```python
# Before: Raw SQL
result = await db.execute(
    "INSERT INTO users (email, name, age) VALUES ($1, $2, $3) RETURNING *",
    ["john@example.com", "John", 30]
)

# After: Pydantic ORM
user = await repo.create(
    User(email="john@example.com", name="John", age=30)
)
```

## Best Practices

1. **Always use type hints** for better IDE support and validation
2. **Set appropriate temporal strategy** based on audit requirements
3. **Enable multi-tenancy** for SaaS applications
4. **Use Field metadata** for database constraints
5. **Leverage caching** for read-heavy workloads
6. **Use batch operations** for bulk data processing
7. **Handle exceptions** appropriately
8. **Use transactions** for atomic operations
9. **Monitor pool connections** in production
10. **Test with different databases** if supporting multiple backends