# FF-Storage v3.3.0 Documentation

Complete documentation for ff-storage's Pydantic ORM and temporal data management.

> **🔥 v3.3.0 Critical Update**: Fixes production bug in schema sync causing false positives. If you're using schema sync (v2.0+), upgrade immediately.

## Getting Started

**New to ff-storage v3?** Start here:

- **[Quickstart Guide](quickstart_v3.md)** - Get up and running in 5 minutes
- **[Strategy Selection Guide](guides/strategy_selection.md)** - Choose the right temporal strategy

## Guides

### Core Concepts
- **[Strategy Selection](guides/strategy_selection.md)** - none vs copy_on_change vs scd2
- **[SCD2 Foreign Keys](guides/scd2_foreign_keys.md)** - FK patterns for versioned data
- **[Production Deployment](FF_STORAGE_V3_PRODUCTION_GUIDE.md)** - Operational best practices

### API Reference
- **[Pydantic ORM API](api/pydantic_orm.md)** - PydanticModel, Field, Repository (coming soon)
- **[Temporal Strategies](api/temporal_strategies.md)** - Strategy interfaces and methods (coming soon)

## Examples

### Complete Examples
- **[Schema Manager Example](examples/schema_manager_example.py)** - Auto-create main + audit tables
- **[Basic Product Model](examples/basic_product_model.py)** - copy_on_change strategy
- **[Regulation SCD2](examples/regulation_scd2.py)** - SCD2 with time travel
- **[Complete Integration](examples/complete_example.py)** - Multi-model setup (coming soon)
- **[Temporal Queries](examples/temporal_queries.py)** - Advanced query patterns (coming soon)

## What's New

### v3.3.0 (Critical Production Fix)
- **Schema Normalization Framework**: Centralized comparison logic (DRY principle)
- **WHERE Clause Parser**: SQL AST parsing with proper precedence handling
- **Production Bug Fix**: Eliminates false positives causing index recreation on every schema sync
- **327 Tests**: Including 93 new normalization tests for comprehensive coverage
- **Backward Compatible**: Internal improvements only, no API changes

### v3.0.0 (Pydantic ORM)

**Pydantic ORM**:
- **Type-safe models** with Pydantic validation
- **Automatic schema generation** from model definitions
- **Rich field metadata** for complete SQL control (FK, CHECK, defaults, partial indexes)

**Temporal Data Management**:
- **Three strategies**: none, copy_on_change, scd2
- **Multi-tenant by default** with automatic filtering
- **Soft delete by default** with restore capability
- **Audit trails** with copy_on_change (field-level tracking)
- **Time travel** with scd2 (immutable versions)

**Schema Management**:
- **Auto-sync schema** from Pydantic models
- **Auxiliary table support** (audit tables auto-created)
- **Terraform-like migrations** (state-based, not file-based)

### Production Features
- **Row-level locking** in copy_on_change (prevents race conditions)
- **Validation system** to catch configuration errors
- **Connection pooling** for high concurrency

## Architecture

```
ff_storage/
├── pydantic_support/
│   ├── base.py              # PydanticModel base class
│   ├── field_metadata.py    # Enhanced Field() with SQL metadata
│   ├── repository.py        # PydanticRepository CRUD
│   ├── introspector.py      # Schema extraction
│   └── type_mapping.py      # Python → SQL type mapping
│
├── temporal/
│   ├── enums.py             # TemporalStrategyType
│   ├── repository_base.py   # TemporalRepository base
│   ├── validation.py        # Configuration validation
│   ├── strategies/
│   │   ├── none.py          # No history strategy
│   │   ├── copy_on_change.py # Field-level audit
│   │   └── scd2.py          # Immutable versions
│   └── utils/               # Query helpers, cleanup, etc.
│
└── db/
    └── schema_sync/
        └── manager.py       # SchemaManager (auto-sync)
```

## Quick Reference

### Define Model

```python
from ff_storage import PydanticModel, Field

class User(PydanticModel):
    __table_name__ = "users"
    __temporal_strategy__ = "copy_on_change"

    email: str = Field(max_length=255, db_unique=True)
    name: str
```

### Auto-Sync Schema

```python
from ff_storage import SchemaManager

manager = SchemaManager(db_pool)
manager.sync_schema(models=[User], dry_run=False)
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

### Query Audit History

```python
# Full history
history = await repo.get_audit_history(user_id)

# Field-specific history
email_changes = await repo.get_field_history(user_id, "email")
```

### Time Travel (SCD2)

```python
# Current version
user = await repo.get(user_id)

# Historical version
user_at_time = await repo.get(user_id, as_of=datetime(2024, 1, 1))

# Version comparison
diff = await repo.compare_versions(user_id, version1=1, version2=2)
```

## Migration from v2.x

v3 is **fully backwards compatible**. Existing v2 code works unchanged.

New v3 features are opt-in:
- Keep using SQL base classes (Postgres, MySQL) for direct SQL
- Add Pydantic models alongside existing code
- Migrate models incrementally

See `CLAUDE.md` for full architecture details.

## Support & Contributing

- **Issues**: https://gitlab.com/fenixflow/fenix-packages/-/issues
- **Discussions**: https://gitlab.com/fenixflow/fenix-packages/-/discussions
- **Contributing**: See `CONTRIBUTING.md` (coming soon)

---

**Ready to build?** Start with the [Quickstart Guide](quickstart_v3.md)!
