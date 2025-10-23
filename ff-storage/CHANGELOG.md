# Changelog

All notable changes to ff-storage will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.2.0] - 2025-10-23

### Fixed

- **NOT NULL Column Handling**: Fixed PostgreSQL errors when adding NOT NULL columns without DEFAULT values to tables with existing data
  - **ADD_COLUMN NOT NULL without DEFAULT**: Now generates safe multi-step SQL that allows existing rows to have NULL while enforcing constraint for new inserts
  - **ALTER_COLUMN nullable→NOT NULL without DEFAULT**: Now fails fast with clear error message providing 3 resolution options (add DEFAULT, manual backfill, or drop column)
  - **ALTER_COLUMN nullable→NOT NULL with DEFAULT**: Now automatically backfills NULL values before adding constraint
  - **Root Cause**: Schema sync generated single-step SQL that PostgreSQL rejected when existing rows couldn't satisfy NOT NULL constraint
  - **Impact**: Schema migrations no longer fail when adding required fields to existing tables

### Changed

- **SQL Generation for ADD_COLUMN NOT NULL without DEFAULT**:
  ```sql
  -- Step 1: Add as nullable (safe for existing rows)
  ALTER TABLE schema.table ADD COLUMN IF NOT EXISTS col TYPE NULL;
  -- Step 2: Enforce NOT NULL (for future inserts only)
  ALTER TABLE schema.table ALTER COLUMN col SET NOT NULL;
  ```
  - **Existing rows**: `col = NULL` (backward compatible, no data modified)
  - **New inserts**: Must provide value (enforced by constraint)
  - **Applications**: Should handle NULL values for records created before migration

- **Enhanced ALTER_COLUMN for nullable changes**:
  - Automatically backfills NULL values when DEFAULT is present
  - Generates clear validation error when DEFAULT is missing
  - Provides 3 explicit resolution paths for developers

### Architecture

**Safety Model** for different scenarios:

| Scenario | is_destructive | Requires Flag | Behavior |
|----------|---------------|---------------|----------|
| ADD NOT NULL without DEFAULT | `False` | No | Always runs, existing rows NULL |
| ADD NOT NULL with DEFAULT | `False` | No | Always runs, all rows get DEFAULT |
| ALTER nullable→NOT NULL with DEFAULT | `True` | Yes | Backfills, requires allow_destructive=True |
| ALTER nullable→NOT NULL without DEFAULT | N/A | N/A | Validation error, never generates SQL |

**Multi-step SQL generation**:
```
ADD_COLUMN NOT NULL without DEFAULT (non-destructive):
  1. ALTER TABLE ... ADD COLUMN col TYPE NULL;
  2. ALTER TABLE ... ALTER COLUMN col SET NOT NULL;
  → Existing rows: NULL | New inserts: required

ALTER nullable→NOT NULL with DEFAULT (destructive):
  1. UPDATE ... SET col = DEFAULT WHERE col IS NULL;
  2. ALTER TABLE ... ALTER COLUMN col SET NOT NULL;
  → All rows backfilled, constraint enforced

ALTER nullable→NOT NULL without DEFAULT:
  → ValueError: "Cannot alter column from nullable to NOT NULL without DEFAULT value"
  → Options: (1) Add DEFAULT, (2) Manual backfill, (3) Drop column
```

### Migration Notes

**Behavior Change for ADD_COLUMN**:
- **Before v3.2.0**: Migration failed with PostgreSQL error
- **After v3.2.0**: Migration succeeds, existing rows have NULL

**If you need ALL rows to have non-NULL values**, add a DEFAULT:
```python
# All rows get the default value immediately
new_field: str = Field(default="")
```

**Or use two-step migration**:
```python
# Step 1: Add as nullable
new_field: Optional[str] = None

# Manually backfill, then Step 2: Make required with DEFAULT
new_field: str = Field(default="backfilled_value")
```

### Real-World Example

**Problem (before v3.2.0)**:
```python
class InscopingContingencySUI(PydanticModel):
    ixr_number: str = Field(..., max_length=50)  # Adding required field

# ❌ Migration failed: column "ixr_number" contains null values
```

**Solution (v3.2.0)**:
```sql
-- Generated SQL (safe multi-step):
ALTER TABLE inscoping_contingency_sui ADD COLUMN IF NOT EXISTS "ixr_number" VARCHAR(50) NULL;
ALTER TABLE inscoping_contingency_sui ALTER COLUMN "ixr_number" SET NOT NULL;

-- ✅ Migration succeeds
-- Existing rows: ixr_number = NULL
-- New inserts: ixr_number required
```

## [3.1.1] - 2025-10-23

### Changed

- **Architecture Refactor**: Established clean separation between database adapters, query builders, and temporal strategies
  - Removed `UniversalPool` wrapper class - no longer needed with clean adapter architecture
  - Made `DatabaseAdapter` parameter optional in `TemporalRepository` and `PydanticRepository`
  - Repository now auto-detects adapter from pool type using `detect_adapter()`
  - **Benefits**:
    - Simpler API: No need to manually wrap pools or pass adapters
    - Backward compatible: All existing code continues to work without changes
    - Clean architecture: Clear separation of concerns (pool → adapter → query builder → strategy)
    - Future-proof: Easy to add support for new database types

### Fixed

- **Adapter Detection**: Fixed `detect_adapter()` to handle wrapper classes (PostgresPool, MySQLPool) before `connect()` is called
  - Previously failed when repository was instantiated before pool connection
  - Now checks wrapper class module paths in addition to underlying pool
  - **Impact**: Repositories can now be created at application startup before database connection

- **Identifier Quoting in Repository Methods**: Fixed unquoted identifiers in `count()` and `get_many()` methods
  - Both methods now use `QueryBuilder.quote_identifier()` for tenant field
  - Completes the identifier quoting work started in v3.0.1, v3.0.2, and v3.1.0
  - **Impact**: Repository methods work correctly with reserved keyword tenant fields

- **Version Filter Quoting**: Enhanced `get_current_version_filters()` to quote field names
  - Base strategy now quotes `deleted_at` field
  - SCD2 strategy override now quotes `valid_to` field
  - **Impact**: Prevents SQL errors when soft_delete or SCD2 fields use reserved keywords

### Architecture

The refactored architecture provides clean layering without unnecessary wrappers:

```
┌─────────────────────────┐
│  PydanticRepository     │
│  (High-level API)       │
└───────────┬─────────────┘
            │ auto-detects
            ▼
┌─────────────────────────┐
│  DatabaseAdapter        │  ← Removed UniversalPool
│  (Database Abstraction) │  ← Made optional (auto-detect)
│  - PostgresAdapter      │
│  - MySQLAdapter         │
│  - SQLServerAdapter     │
└───────────┬─────────────┘
            │ provides
            ▼
┌─────────────────────────┐
│  QueryBuilder           │
│  (SQL Generation)       │
│  - PostgresQueryBuilder │
└───────────┬─────────────┘
            │ used by
            ▼
┌─────────────────────────┐
│  Temporal Strategies    │
│  (Business Logic)       │
│  - NoneStrategy         │
│  - CopyOnChangeStrategy │
│  - SCD2Strategy         │
└─────────────────────────┘
```

### Backward Compatibility

**v3.1.1 is fully backward compatible with v3.1.0 and v3.0.x**:
- All existing code continues to work without changes
- Adapter parameter can still be explicitly provided if needed
- Auto-detection only used when adapter is not provided
- No breaking changes to any public APIs

## [3.1.0] - 2025-10-22

### Changed

- **Architecture Improvement**: Refactored SQL query building to use proper QueryBuilder pattern
  - Created `db/query_builder/` module with database-agnostic `QueryBuilder` base class
  - Implemented `PostgresQueryBuilder` with comprehensive identifier quoting and parameter placeholder generation
  - Refactored all temporal strategies (`NoneStrategy`, `SCD2Strategy`, `CopyOnChangeStrategy`) to use QueryBuilder
  - Updated strategy registry to inject QueryBuilder instances into strategies
  - **Benefits**:
    - DRY principle: Single source of truth for SQL query generation
    - Modular: Clear separation between business logic (strategies) and database-specific SQL syntax
    - Testable: QueryBuilder can be unit tested independently
    - Extensible: Easy to add support for other databases (MySQL, SQL Server)
    - Type-safe: Returns `(query_string, [values])` tuples with proper parameter ordering

### Fixed

- **SQL Parser**: Updated `PostgresSQLParser` to handle quoted identifiers from v3.0.1/v3.0.2 changes
  - Fixed regex patterns to parse both quoted (`"table_name"`) and unquoted identifiers
  - Added `_strip_quotes()` helper to normalize identifier comparisons
  - Updated `parse_create_table()`, `parse_columns_from_sql()`, `parse_indexes_from_sql()`
  - **Root Cause**: v3.0.2 added identifier quoting to DDL generation, but SQL parser couldn't parse the quoted output back
  - **Impact**: Schema sync now correctly handles tables with quoted identifiers

### Added

- `db/query_builder/` module:
  - `QueryBuilder` base class defining the query building interface
  - `PostgresQueryBuilder` implementation with:
    - `quote_identifier()`: Always quotes identifiers for safety
    - `build_insert()`: Generates INSERT queries with RETURNING *
    - `build_update()`: Generates UPDATE queries with proper WHERE and SET clauses
    - `build_where_clause()`: Handles NULL values, IN clauses, and parameter placeholders
    - `build_column_list()`: Generates comma-separated quoted column lists

### Architecture

The QueryBuilder pattern provides a clean separation of concerns:

```
┌─────────────────────────┐
│  Temporal Strategies    │
│  (Business Logic)       │
│  - NoneStrategy         │
│  - SCD2Strategy         │
│  - CopyOnChangeStrategy │
└───────────┬─────────────┘
            │ uses
            ▼
┌─────────────────────────┐
│  QueryBuilder           │
│  (SQL Generation)       │
│  - PostgresQueryBuilder │
│  - MySQLQueryBuilder    │ (future)
│  - SQLServerQueryBuilder│ (future)
└─────────────────────────┘
```

This architecture makes it trivial to add support for other databases - just implement a new QueryBuilder subclass without touching strategy code.

## [3.0.2] - 2025-10-22

### Fixed

- **SQL Reserved Keywords in Data Operations (DML)**: Completed the fix started in v3.0.1 by extending identifier quoting to all CRUD operations
  - **Root Cause**: v3.0.1 only fixed DDL (schema generation) but not DML (INSERT/UPDATE/SELECT queries)
  - Created centralized PostgreSQL utilities module (`utils/postgres.py`) with production-grade query builders:
    - `quote_identifier()`: Single source of truth for identifier quoting
    - `build_insert_query()`: Generates safe INSERT statements with quoted identifiers
    - `build_update_set_clause()`: Generates safe UPDATE SET clauses with quoted identifiers
    - `build_where_clause()`: Generates safe WHERE clauses with quoted identifiers
  - Refactored `PostgresMigrationGenerator` to use shared `quote_identifier()` (removed duplicate code)
  - Updated all temporal strategies to use centralized query builders:
    - `SCD2Strategy`: Fixed INSERT queries in create(), update(), and delete() methods
    - `NoneStrategy`: Fixed INSERT and UPDATE queries
    - `CopyOnChangeStrategy`: Fixed INSERT, UPDATE, and audit table queries
    - `TemporalStrategy` base class: Fixed WHERE clause building in `_validate_and_build_filter_clauses()`
  - **Impact**: Models can now use ANY valid Python identifier as a field name, including SQL reserved keywords like:
    - `limit`, `order`, `user`, `select`, `where`, `from`, `join`, etc.
  - **Breaking from v3.0.1**: The v3.0.1 fix was incomplete - it only handled schema sync (DDL), causing runtime SQL syntax errors when using reserved keywords in actual CRUD operations

**What Changed This Morning**: The Pydantic ORM was added in v3.0.0 just 2 days ago, introducing automatic schema generation. Previously, developers wrote SQL manually and would naturally quote reserved keywords themselves. The automatic query generation didn't quote identifiers, exposing this bug.

### Changed

- **Architecture Improvement (DRY)**: Consolidated all PostgreSQL-specific query building into `utils/postgres.py`
  - Eliminated duplicate `quote_identifier()` implementations
  - All DDL (schema sync) and DML (CRUD operations) now use the same quoting logic
  - Clear separation of concerns: schema sync uses shared utilities, temporal strategies use shared utilities
  - Production-ready: Single place to update PostgreSQL query generation logic

### Added

- Comprehensive test suite for SQL identifier quoting (`tests/unit/test_sql_identifier_quoting_fixed.py`)
- Test coverage for all query builders with reserved keywords
- Integration tests demonstrating reserved keywords work across all temporal strategies

## [3.0.1] - 2025-10-22

### Fixed

- **PostgreSQL Reserved Keywords**: Fixed SQL syntax errors when using PostgreSQL reserved keywords (like `limit`, `order`, `user`, etc.) as column names in Pydantic models
  - Added `quote_identifier()` method to `PostgresMigrationGenerator` to properly quote all SQL identifiers
  - All column names, table names, and index names are now wrapped in double quotes in generated SQL
  - Affected methods: `generate_create_table()`, `generate_add_column()`, `generate_alter_column()`, `generate_drop_column()`, `generate_create_index()`, `generate_drop_index()`
  - USING clauses in ALTER COLUMN statements also properly quote column names
  - This ensures any valid Python identifier can be used as a field name, even if it's a SQL reserved keyword

**Example**: A field named `limit` now generates `"limit" JSONB NOT NULL` instead of `limit JSONB NOT NULL`

**Why this wasn't an issue before**: The Pydantic ORM automatic schema generation was added in v3.0.0 (2 days ago). Previously, users wrote SQL manually where they would naturally quote reserved keywords themselves.

## [3.0.0] - 2025-10-22

### 🚨 BREAKING CHANGES

**Pydantic ORM and Temporal Data Management** - major feature release introducing type-safe models with automatic schema generation and built-in temporal data strategies.

#### What's New

This release adds a complete Pydantic-based ORM layer on top of the existing SQL base classes. All v2.x functionality remains unchanged and fully compatible.

**Before (v2.x - Direct SQL)**:
```python
from ff_storage.db import Postgres

db = Postgres(...)
db.execute_query(
    "INSERT INTO users (id, email, name) VALUES (%s, %s, %s)",
    {"id": uuid4(), "email": "user@example.com", "name": "John"}
)
```

**After (v3.0.0 - Pydantic ORM)**:
```python
from ff_storage import PydanticModel, PydanticRepository, Field

class User(PydanticModel):
    __table_name__ = "users"
    __temporal_strategy__ = "copy_on_change"

    email: str = Field(max_length=255, db_unique=True)
    name: str

repo = PydanticRepository(User, db_pool, tenant_id=org_id)
user = await repo.create(User(email="user@example.com", name="John"), user_id=admin_id)
```

### Added

- **Pydantic ORM Layer** (`pydantic_support/`):
  - `PydanticModel`: Base class for type-safe models with Pydantic validation
  - `PydanticRepository`: Generic repository for CRUD operations with temporal support
  - `Field()`: Enhanced field metadata for SQL constraints (FK, CHECK, defaults, partial indexes)
  - Automatic schema generation from model definitions
  - Type mapping from Python types to SQL types (PostgreSQL, MySQL, SQL Server)
  - Schema introspection for extracting model structure

- **Temporal Data Management** (`temporal/`):
  - Three temporal strategies:
    - `none`: Standard CRUD without history
    - `copy_on_change`: Field-level audit trail with automatic audit table
    - `scd2`: Immutable versioning with time travel (Type 2 Slowly Changing Dimension)
  - Multi-tenant support with automatic tenant filtering
  - Soft delete with restore capability
  - Row-level locking in copy_on_change (prevents race conditions)
  - Audit history queries with field-level change tracking
  - Time travel queries for point-in-time data access
  - Version comparison and diff capabilities

- **Enhanced Schema Management**:
  - Auxiliary table support (audit tables auto-created by SchemaManager)
  - Enhanced `SchemaManager` with temporal strategy awareness
  - Automatic foreign key setup for audit tables
  - Validation system to catch configuration errors at startup

- **Production Features**:
  - Connection pooling integration with temporal repositories
  - Async/await support throughout temporal layer
  - Comprehensive validation for temporal configurations
  - Query builders for temporal operations
  - Cleanup utilities for audit data management

### Changed

- `SchemaManager.sync_schema()` now supports `auxiliary_ddl` parameter for temporal audit tables
- Enhanced model base class hierarchy to support both SQL and Pydantic approaches
- Repository pattern now primary API (direct SQL still fully supported)

### Backward Compatibility

**v3.0.0 is fully backward compatible with v2.x**:
- All existing SQL base classes unchanged (Postgres, MySQL, SQLServer)
- Direct SQL operations continue to work
- Connection pooling unchanged
- Schema sync unchanged for non-Pydantic models
- Migration: Pydantic ORM is opt-in, use alongside existing code

### Performance

- Row-level locking prevents concurrent update conflicts in copy_on_change strategy
- Optimized queries for temporal operations (indexed by validity periods)
- Bulk operations supported in repositories
- Connection pooling for high-concurrency scenarios

### Documentation

- Complete v3.0.0 documentation in `docs/` folder
- Quickstart guide for Pydantic ORM
- Strategy selection guide for temporal patterns
- SCD2 foreign key patterns guide
- Production deployment guide
- Migration examples from v2.x

### Architecture

```
ff_storage/
├── pydantic_support/      # NEW: Pydantic ORM layer
│   ├── base.py            # PydanticModel base class
│   ├── field_metadata.py  # Enhanced Field() with SQL metadata
│   ├── repository.py      # PydanticRepository CRUD
│   ├── introspector.py    # Schema extraction
│   └── type_mapping.py    # Python → SQL type mapping
│
├── temporal/              # NEW: Temporal data management
│   ├── enums.py           # TemporalStrategyType
│   ├── repository_base.py # TemporalRepository base
│   ├── validation.py      # Configuration validation
│   ├── strategies/
│   │   ├── none.py        # No history strategy
│   │   ├── copy_on_change.py # Field-level audit
│   │   └── scd2.py        # Immutable versions
│   └── utils/             # Query helpers, cleanup, etc.
│
└── db/                    # UNCHANGED: Existing SQL layer
    ├── postgres.py
    ├── mysql.py
    ├── sqlserver.py
    └── schema_sync/
```

### Usage Examples

See complete examples in `docs/quickstart_v3.md` and `docs/examples/`.

**Define Model**:
```python
from ff_storage import PydanticModel, Field

class Product(PydanticModel):
    __table_name__ = "products"
    __temporal_strategy__ = "copy_on_change"

    name: str = Field(max_length=255)
    price: Decimal = Field(decimal_precision=(10, 2), db_check="price > 0")
    sku: str = Field(max_length=50, db_unique=True)
```

**CRUD Operations**:
```python
from ff_storage import PydanticRepository

repo = PydanticRepository(Product, db_pool, tenant_id=org_id)

# Create with audit
product = await repo.create(Product(...), user_id=admin_id)

# Update with audit trail
updated = await repo.update(product.id, Product(...), user_id=admin_id)

# Query audit history
history = await repo.get_audit_history(product.id)
price_changes = await repo.get_field_history(product.id, "price")

# Soft delete with restore
await repo.delete(product.id, user_id=admin_id)
await repo.restore(product.id, user_id=admin_id)
```

**Time Travel (SCD2)**:
```python
class Regulation(PydanticModel):
    __temporal_strategy__ = "scd2"

    regulation_code: str
    text: str

repo = PydanticRepository(Regulation, db_pool)

# Current version
current = await repo.get(reg_id)

# Historical version
past_version = await repo.get(reg_id, as_of=datetime(2024, 1, 1))

# Compare versions
diff = await repo.compare_versions(reg_id, version1=1, version2=2)
```

### Migration from v2.x

No breaking changes - v3 features are additive:

1. **Continue using v2.x SQL classes** - no changes required
2. **Add Pydantic models** for new tables or incrementally migrate
3. **Use SchemaManager** to auto-create both main and audit tables
4. **Choose temporal strategy** per model based on requirements

See `docs/quickstart_v3.md` for step-by-step migration guide.

### Future Work

- Additional temporal strategies (event sourcing, bi-temporal)
- GraphQL integration for temporal queries
- Real-time change notifications
- Temporal foreign key integrity validation
- Automated audit data archival

## [2.0.1] - 2025-10-15

### Fixed

- **PostgreSQL SQL Parser**: Fixed regex pattern in `PostgresSQLParser.parse_columns_from_sql()` to correctly parse column definitions containing:
  - Multi-word types like `TIMESTAMP WITH TIME ZONE`
  - Foreign key constraints with `REFERENCES` clauses
  - Complex column definitions with multiple constraints
- Previously, columns with these patterns were not detected, causing SchemaManager to incorrectly report them as needing to be dropped
- This fix ensures SchemaManager accurately compares model definitions with actual database schema

## [2.0.0] - 2025-10-15

### 🚨 BREAKING CHANGES

**Schema synchronization replaces file-based migrations** - this is a major architectural shift to automatic, model-driven schema management similar to Terraform.

#### What Changed

- **Removed**: `MigrationManager` and file-based SQL migration system
- **Added**: `SchemaManager` with Terraform-like automatic schema synchronization
- **Migration Path**: Define schema in model `get_create_table_sql()` methods; SchemaManager automatically syncs on startup

#### Migration Required

**Before (v1.x - File-based migrations)**:
```python
from ff_storage.db import MigrationManager

manager = MigrationManager(db, "./migrations")
manager.migrate()  # Runs SQL files in order
```

**After (v2.0.0 - Schema sync)**:
```python
from ff_storage.db import SchemaManager

manager = SchemaManager(db, logger=logger)
changes = manager.sync_schema(
    models=get_all_models(),
    allow_destructive=False,
    dry_run=False
)
```

### Added

- **Schema Sync System**: Terraform-like automatic schema synchronization
  - `SchemaManager`: Main orchestrator for schema sync
  - Provider-agnostic design with abstract base classes
  - Full PostgreSQL implementation (introspection, parsing, generation)
  - MySQL/SQL Server stubs for future implementation
  - Automatic detection of schema changes from model definitions
  - Safe by default (destructive changes require explicit approval)
  - Dry-run mode for previewing changes without applying them
  - Transaction-wrapped migrations for atomicity
  - Comprehensive structured logging throughout

- **Schema Sync Components**:
  - `SchemaIntrospectorBase`: Read current database schema from information_schema
  - `SQLParserBase`: Parse CREATE TABLE statements into structured definitions
  - `MigrationGeneratorBase`: Generate provider-specific DDL statements
  - `SchemaDifferBase`: Compute differences between desired and current schema
  - Provider-specific implementations for PostgreSQL (complete)
  - Stub implementations for MySQL and SQL Server (raise NotImplementedError)

- **Model Compatibility Methods**:
  - `get_create_table_sql()`: Alias for `create_table_sql()` for SchemaManager compatibility
  - `get_table_name()`: Alias for `table_name()` for SchemaManager compatibility

### Changed

- **BREAKING**: Reorganized `db` module structure (completed in v1.1.0)
  - Connection classes moved to `db.connections/` subfolder
  - Updated import paths (backward compatible via `from ff_storage.db import Postgres`)

### Removed

- **BREAKING**: Removed file-based migrations system
  - `MigrationManager` class removed
  - No longer supports SQL migration files in directories
  - Migration: Use SchemaManager with model definitions instead

### Architecture

- **Provider Detection**: Auto-detects database type from connection object
- **Safety First**: Additive changes (CREATE, ADD) auto-apply; destructive changes (DROP, ALTER TYPE) require explicit flag
- **Dry Run Mode**: Preview all changes without applying them
- **Transaction Wrapping**: All schema changes in single atomic transaction
- **IF NOT EXISTS**: Uses safe SQL clauses to prevent errors on re-runs

### Usage Example

```python
from ff_storage.db import Postgres, SchemaManager
from ff_logger import ConsoleLogger

# Define models with create_table_sql()
class Document(BaseModel):
    __table_name__ = "documents"
    __schema__ = "public"

    @classmethod
    def create_table_sql(cls):
        return """
        CREATE TABLE IF NOT EXISTS public.documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title TEXT NOT NULL,
            content TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_documents_title
        ON public.documents(title);
        """

# Connect and sync
db = Postgres(dbname="mydb", user="user", password="pass", host="localhost", port=5432)
db.connect()

logger = ConsoleLogger(name="schema_sync")
manager = SchemaManager(db, logger=logger)

# Dry run to preview changes
changes = manager.sync_schema(
    models=[Document],
    allow_destructive=False,
    dry_run=True
)

# Apply changes
changes = manager.sync_schema(
    models=[Document],
    allow_destructive=False,
    dry_run=False
)

print(f"Applied {changes} schema changes")
```

### Migration Guide

For users upgrading from v1.x:

1. **Remove migration files**: No longer needed (schema is in models)
2. **Update model classes**: Ensure `create_table_sql()` or `get_create_table_sql()` is defined
3. **Replace MigrationManager**: Use SchemaManager instead
4. **Run schema sync**: On application startup, call `manager.sync_schema()`

### Future Work

- MySQL implementation (contributions welcome!)
- SQL Server implementation (contributions welcome!)
- Column type changes detection
- Foreign key constraint management
- Schema versioning and rollback

## [1.0.0] - 2025-10-06

### 🚨 BREAKING CHANGES

**All connection pool classes are now async** - this is a major architectural change for better scalability and modern Python async patterns.

**All database queries now return dictionaries by default** - this provides better code maintainability and intuitive column access across all database types.

#### Migration Required

**Before (v0.3.0 - Sync)**:
```python
from ff_storage.db import PostgresPool

pool = PostgresPool(...)
pool.connect()
results = pool.read_query("SELECT * FROM users")
pool.close_connection()
```

**After (v1.0.0 - Async)**:
```python
from ff_storage.db import PostgresPool

pool = PostgresPool(...)
await pool.connect()  # Once at startup
results = await pool.fetch_all("SELECT * FROM users")  # Many times
await pool.disconnect()  # Once at shutdown
```

**For synchronous code, use direct connections** (still sync, but now returns dicts):
```python
from ff_storage.db import Postgres  # Still sync!

db = Postgres(...)
db.connect()
results = db.read_query("SELECT * FROM users")
# v0.3.0: results = [(1, 'Alice'), (2, 'Bob')]  # Tuples
# v1.0.0: results = [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]  # Dicts!

# To get tuples (legacy behavior):
results = db.read_query("SELECT * FROM users", as_dict=False)
db.close_connection()
```

### Added
- **Async PostgreSQL Pool**: `PostgresPool` now uses `asyncpg` for high-performance async connections
- **Async MySQL Pool**: `MySQLPool` now uses `aiomysql` for async MySQL connections
- **Async SQL Server Pool**: `SQLServerPool` now uses `aioodbc` for async SQL Server connections
- **Dictionary Results by Default**: All query methods now return dictionaries for easy column access
  - `fetch_one()` and `fetch_all()` return dicts with column names as keys
  - `read_query()` (sync) also returns dicts by default
  - Access results naturally: `result['id']` instead of positional indexes
  - Optional `as_dict=False` parameter to get tuples when needed
  - Polymorphic behavior across all database types (PostgreSQL, MySQL, SQL Server)
- Added `aiomysql>=0.2.0` dependency for MySQL async support
- Added `aioodbc>=0.5.0` dependency for SQL Server async support
- New async methods: `fetch_one()`, `fetch_all()`, `execute()`, `execute_many()`
- `connect()` and `disconnect()` lifecycle methods for pool management
- FastAPI-ready async connection pools with automatic connection acquisition

### Changed
- **PostgresPool**: Completely rewritten to use asyncpg instead of psycopg2 pooling
- **MySQLPool**: Completely rewritten to use aiomysql instead of mysql-connector pooling
- **SQLServerPool**: Completely rewritten to use aioodbc instead of pyodbc pooling
- **Return Format**: All query methods now return dictionaries by default instead of tuples
  - Makes code more maintainable and self-documenting
  - Eliminates positional index bugs (e.g., `row[2]` → `row['email']`)
  - Consistent across PostgreSQL, MySQL, and SQL Server
  - Use `as_dict=False` to get tuple format when needed
- Pool methods renamed for clarity:
  - `read_query()` → `fetch_all()`
  - `execute_query()` → `execute()` with return value
  - `close_pool()` → `disconnect()`
- All pool operations now require `await` keyword
- Pools now handle connection acquisition internally - users never manage connections directly

### Removed
- Sync pool implementations (use direct connections for sync code instead)
- `read_query()`, `execute_query()`, `execute()` methods from pool classes (replaced with async equivalents)
- Pool connection acquisition methods (automatic now)

### Performance
- **10-100x better throughput** with async pools under concurrent load
- Non-blocking I/O for all database operations
- Connection reuse without event loop blocking
- Optimal for FastAPI, async frameworks, and high-concurrency applications

### Architecture
- **Sync for simplicity**: `Postgres`, `MySQL`, `SQLServer` - direct connections for scripts
- **Async for scale**: `PostgresPool`, `MySQLPool`, `SQLServerPool` - pools for production
- Uniform async interface across all three databases
- Pool lifecycle tied to application lifecycle (startup/shutdown events)

## [0.3.0] - 2025-10-06

### Added
- Microsoft SQL Server support with `SQLServer`, `SQLServerPool`, and `SQLServerBase` classes
- Full SQL Server operations using pyodbc with ODBC Driver 18
- Connection pooling support for SQL Server with MARS (Multiple Active Result Sets)
- Schema introspection for SQL Server (table existence, column information)
- Encrypted connections with TrustServerCertificate configuration
- SQL Server-specific query methods with OUTPUT clause support
- Added `pyodbc>=5.0` dependency for SQL Server connectivity

### Changed
- Updated package keywords to include "sqlserver"
- Version bump: 0.2.3 → 0.3.0 (minor release for new database support)

## [0.2.0] - 2024-12-16

### Added
- Initial public release
- MIT License for open source distribution
- Comprehensive README with usage examples
- PyPI package metadata and classifiers

### Changed
- Updated package metadata for public distribution
- Changed from proprietary to MIT license

## [0.1.4] - 2024-09-15

### Fixed
- Connection pooling improvements for PostgreSQL
- Thread safety in MySQL connection handling

## [0.1.3] - 2024-09-10

### Added
- MySQL connection pooling support
- Query builder utilities for complex SQL construction

## [0.1.2] - 2024-09-01

### Added
- S3 object storage implementation with streaming support
- Multipart upload for large files
- S3-compatible services support (MinIO, etc.)

### Fixed
- Memory efficiency in streaming operations
- Path traversal protection in local storage

## [0.1.1] - 2024-08-25

### Added
- Local filesystem object storage with atomic writes
- Metadata sidecar files for object properties
- Async/await support throughout object storage

### Fixed
- Race conditions in concurrent file writes

## [0.1.0] - 2024-08-20

### Added
- Initial release with core functionality
- PostgreSQL database support with connection pooling
- MySQL database support
- SQL migration management system
- Abstract base classes for database operations
- Dataclass models with UUID and timestamp support

---

Maintained by **Ben Moag** ([Fenixflow](https://fenixflow.com))

[Unreleased]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v3.0.0...HEAD
[3.0.0]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v2.0.1...ff-storage-v3.0.0
[2.0.1]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v2.0.0...ff-storage-v2.0.1
[2.0.0]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v1.0.0...ff-storage-v2.0.0
[1.0.0]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.3.0...ff-storage-v1.0.0
[0.3.0]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.2.0...ff-storage-v0.3.0
[0.2.0]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.4...ff-storage-v0.2.0
[0.1.4]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.3...ff-storage-v0.1.4
[0.1.3]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.2...ff-storage-v0.1.3
[0.1.2]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.1...ff-storage-v0.1.2
[0.1.1]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.0...ff-storage-v0.1.1
[0.1.0]: https://gitlab.com/fenixflow/fenix-packages/-/releases/ff-storage-v0.1.0