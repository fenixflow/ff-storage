# FF-Storage v4.7.0 Documentation

Complete documentation for ff-storage's Pydantic ORM, Query Builder, Relationships, and Temporal Data Management.

> **🔥 v4.7.0 Major Release**: Adds Query Builder, Model Relationships, Transactions, and Bulk Operations. 100% backward compatible.

## Getting Started

**New to ff-storage?** Start here:

- **[Quickstart Guide](quickstart.md)** - Get up and running in 5 minutes
- **[Strategy Selection Guide](guides/strategy_selection.md)** - Choose the right temporal strategy

## Guides

### Core Concepts
- **[Strategy Selection](guides/strategy_selection.md)** - none vs copy_on_change vs scd2
- **[SCD2 Foreign Keys](guides/scd2_foreign_keys.md)** - FK patterns for versioned data
- **[Production Deployment](PRODUCTION_GUIDE.md)** - Operational best practices

### API Reference
- **[Pydantic ORM API](api/pydantic_orm.md)** - PydanticModel, Field, Repository
- **[Temporal Strategies](api/temporal_strategies.md)** - Strategy interfaces and methods

## Examples

### Complete Examples
- **[Schema Manager Example](examples/schema_manager_example.py)** - Auto-create main + audit tables
- **[Basic Product Model](examples/basic_product_model.py)** - copy_on_change strategy
- **[Regulation SCD2](examples/regulation_scd2.py)** - SCD2 with time travel

## What's New

### v4.7.0 (Query Builder & Relationships)

**Query Builder**:
- **Fluent API** with chaining: `Query(Model).filter(...).order_by(...).limit(...).execute()`
- **Type-safe filtering** with `F.field` syntax and comparison operators
- **Complex filters** with `AND()`, `OR()` composite expressions
- **Aggregations** with `func.count()`, `func.sum()`, `func.avg()`, etc.
- **JOINs** with automatic temporal and tenant safety

**Relationships**:
- **One-to-many**: `posts: list["Post"] = Relationship(back_populates="author")`
- **Many-to-one**: `author: "Author" = Relationship(back_populates="posts")`
- **Many-to-many**: Junction table support
- **Eager loading**: `Query(Model).load(["relationship"])` prevents N+1 queries

**Transactions**:
- **Context manager**: `async with Transaction(pool) as tx:`
- **Savepoints**: Nested transactions with rollback
- **Isolation levels**: READ_COMMITTED, REPEATABLE_READ, SERIALIZABLE
- **Unit of Work**: Complex multi-repository operations

**Bulk Operations**:
- **insert_many()**: Batch inserts with RETURNING
- **update_many()**: Batch updates with filters
- **delete_many()**: Batch deletes with filters

### v3.3.0 (Schema Sync Fixes)
- **Schema Normalization Framework**: Centralized comparison logic
- **WHERE Clause Parser**: SQL AST parsing with proper precedence
- **Production Bug Fix**: Eliminates false positives in schema sync

### v3.0.0 (Pydantic ORM)
- **Type-safe models** with Pydantic validation
- **Temporal strategies**: none, copy_on_change, scd2
- **Multi-tenant by default** with automatic filtering
- **Audit trails** and **time travel** queries

## Architecture

```
ff_storage/
├── pydantic_support/         # Pydantic ORM layer
│   ├── base.py               # PydanticModel base class
│   ├── repository.py         # PydanticRepository CRUD
│   └── schema_sync.py        # Schema synchronization
│
├── query/                    # Query Builder (v4.7.0)
│   ├── builder.py            # Query class with fluent API
│   ├── expressions.py        # FilterExpression, FieldProxy, F
│   ├── executor.py           # QueryExecutor with temporal awareness
│   └── bulk.py               # Bulk operations
│
├── relationships/            # Relationships (v4.7.0)
│   ├── descriptor.py         # Relationship descriptor
│   ├── loader.py             # RelationshipLoader (N+1 prevention)
│   └── registry.py           # RelationshipRegistry
│
├── transactions/             # Transactions (v4.7.0)
│   ├── context.py            # Transaction context manager
│   └── unit_of_work.py       # Unit of Work pattern
│
├── temporal/
│   ├── strategies/           # none, scd2, copy_on_change
│   └── repository.py         # TemporalRepository base
│
└── db/
    └── schema_sync/          # Schema introspection
```

## Quick Reference

### Query Builder

```python
from ff_storage import Query, F

# Fluent query API
results = await (
    Query(Product)
    .filter(F.price > 100)
    .filter(F.status == "active")
    .order_by(F.created_at.desc())
    .limit(10)
    .execute(db_pool, tenant_id=tenant)
)

# Convenience methods
user = await Query(User).filter(F.email == email).first(db_pool)
exists = await Query(User).filter(F.email == email).exists(db_pool)
count = await Query(Product).filter(F.active == True).count(db_pool)
```

### Relationships

```python
from ff_storage import PydanticModel, Relationship, Field

class Author(PydanticModel):
    __table_name__ = "authors"
    posts: list["Post"] = Relationship(back_populates="author")

class Post(PydanticModel):
    __table_name__ = "posts"
    author_id: UUID
    author: "Author" = Relationship(back_populates="posts")

# Eager loading
authors = await Query(Author).load(["posts"]).execute(db_pool)
```

### CRUD Operations

```python
from ff_storage import PydanticRepository

repo = PydanticRepository(User, db_pool, tenant_id=org_id)

user = await repo.create(User(...), user_id=admin_id)
updated = await repo.update(user.id, User(...), user_id=admin_id)
user = await repo.get(user_id)
users = await repo.list(filters={"role": "admin"})
await repo.delete(user_id, user_id=admin_id)
```

### Transactions

```python
from ff_storage import Transaction

async with Transaction(db_pool) as tx:
    await tx.execute("INSERT INTO ...")
    await tx.execute("UPDATE ...")
    # Auto-commits on success, rollbacks on exception
```

## Migration from Earlier Versions

v4.7.0 is **100% backwards compatible**. All existing code works unchanged.

New features are opt-in:
- Existing `repo.list(filters={...})` syntax continues to work
- Query Builder is an alternative API, not a replacement
- Relationships are optional model attributes

---

**Ready to build?** Start with the [Quickstart Guide](quickstart.md)!
