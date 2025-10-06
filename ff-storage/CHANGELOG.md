# Changelog

All notable changes to ff-storage will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.3.0...HEAD
[0.3.0]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.2.0...ff-storage-v0.3.0
[0.2.0]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.4...ff-storage-v0.2.0
[0.1.4]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.3...ff-storage-v0.1.4
[0.1.3]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.2...ff-storage-v0.1.3
[0.1.2]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.1...ff-storage-v0.1.2
[0.1.1]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.0...ff-storage-v0.1.1
[0.1.0]: https://gitlab.com/fenixflow/fenix-packages/-/releases/ff-storage-v0.1.0