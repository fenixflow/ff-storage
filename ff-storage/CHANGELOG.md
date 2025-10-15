# Changelog

All notable changes to ff-storage will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v2.0.0...HEAD
[2.0.0]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v1.0.0...ff-storage-v2.0.0
[1.0.0]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.3.0...ff-storage-v1.0.0
[0.3.0]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.2.0...ff-storage-v0.3.0
[0.2.0]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.4...ff-storage-v0.2.0
[0.1.4]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.3...ff-storage-v0.1.4
[0.1.3]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.2...ff-storage-v0.1.3
[0.1.2]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.1...ff-storage-v0.1.2
[0.1.1]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.0...ff-storage-v0.1.1
[0.1.0]: https://gitlab.com/fenixflow/fenix-packages/-/releases/ff-storage-v0.1.0