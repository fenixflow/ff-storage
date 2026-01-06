# CLAUDE.md - ff-storage

## Overview

ff-storage is a Pydantic-first ORM with built-in temporal versioning for PostgreSQL, MySQL, and SQL Server. It provides async connection pools, schema synchronization, and object storage abstractions.

## Key Features

- **Pydantic ORM**: Type-safe models with automatic schema generation
- **Temporal Strategies**: none, copy_on_change (audit trail), scd2 (time travel)
- **Query Builder**: Fluent API for type-safe queries with JOINs
- **Relationships**: One-to-many, many-to-one, many-to-many with eager loading
- **Transactions**: Full transaction support with Unit of Work pattern
- **Multi-Tenant**: Automatic tenant isolation with strict/permissive scopes

## Development Commands

```bash
# Navigate to ff-storage
cd /Users/bgmoag/PycharmProjects/fenixflow/worktrees/ff-storage-relationships-query-builder/ff-storage

# Install dependencies
uv sync

# Run tests
uv run pytest tests/

# Format and lint
uvx isort . && uvx ruff format . && uvx ruff check --fix .

# Type check
uv run mypy src/ff_storage/
```

## Package Structure

```
src/ff_storage/
├── pydantic_support/     # Pydantic ORM layer
│   ├── base.py           # PydanticModel base class
│   ├── repository.py     # PydanticRepository CRUD
│   └── schema_sync.py    # Schema synchronization
├── temporal/             # Temporal data management
│   ├── strategies/       # none, scd2, copy_on_change
│   └── repository.py     # TemporalRepository base
├── query/                # Query builder (NEW in v4.7.0)
│   ├── builder.py        # Query class with fluent API
│   ├── expressions.py    # FilterExpression, FieldProxy, F
│   ├── executor.py       # QueryExecutor with temporal awareness
│   └── bulk.py           # Bulk operations
├── relationships/        # Model relationships (NEW in v4.7.0)
│   ├── descriptor.py     # Relationship descriptor
│   ├── loader.py         # RelationshipLoader (N+1 prevention)
│   └── registry.py       # RelationshipRegistry
├── transactions/         # Transaction management (NEW in v4.7.0)
│   ├── context.py        # Transaction context
│   └── unit_of_work.py   # Unit of Work pattern
├── db/                   # Database layer
│   ├── pool/             # Async connection pools
│   ├── query_builder/    # SQL query building
│   └── schema_sync/      # Schema introspection
└── object/               # Object storage
    ├── local.py          # Local filesystem
    ├── s3.py             # S3/S3-compatible
    └── azure.py          # Azure Blob Storage
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

# With relationships
results = await (
    Query(Author)
    .filter(F.name.contains("John"))
    .join(Author.posts)
    .load(["posts"])  # Eager load
    .execute(db_pool)
)
```

### Relationships

```python
from ff_storage import PydanticModel, Relationship, Field

class Author(PydanticModel):
    __table_name__ = "authors"
    name: str = Field(max_length=255)
    posts: list["Post"] = Relationship(back_populates="author")

class Post(PydanticModel):
    __table_name__ = "posts"
    title: str = Field(max_length=255)
    author_id: UUID
    author: "Author" = Relationship(back_populates="posts")
```

### Transactions

```python
from ff_storage import Transaction

async with Transaction(db_pool) as tx:
    await tx.execute("INSERT INTO ...")
    await tx.execute("UPDATE ...")
    # Auto-commits on success, rollbacks on exception
```

## Non-Breaking Changes

All new features are additive. Existing code continues to work:

```python
# Old API still works unchanged
repo = PydanticRepository(Product, db_pool, tenant_id=tenant)
products = await repo.list(filters={"status": "active"})
```

## Documentation

- [Quickstart Guide](docs/quickstart.md)
- [Production Guide](docs/PRODUCTION_GUIDE.md)
- [Type Mapping](docs/TYPE_MAPPING.md)
- [Strategy Selection](docs/guides/strategy_selection.md)
