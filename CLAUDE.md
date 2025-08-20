# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fenix-Packages is a monorepo containing reusable Python packages for Fenixflow applications. The repository follows a modular architecture with each package providing specific functionality that can be independently installed and versioned.

### Current Packages

**ff-storage**: Database and file storage operations package providing:
- PostgreSQL and MySQL connections with connection pooling
- SQL query builder and transaction management
- File storage interfaces for local, S3, and Azure Blob Storage
- Migration management system for database schema updates

## Architecture

### ff-storage Package Structure

The package follows a layered architecture:

**Database Layer** (`src/ff_storage/db/`):
- `sql.py`: Abstract SQL base class defining the interface for all database operations
- `postgres.py`: PostgreSQL implementation with direct connection and connection pooling
- `models.py`: Dataclass-based models with UUID and timestamp support
- `migrations.py`: SQL file-based migration management system

**File Storage Layer** (`src/ff_storage/file/`):
- Provides unified interface for different storage backends
- Supports local filesystem, AWS S3, and Azure Blob Storage

### Key Design Patterns

1. **Abstract Base Classes**: SQL base class provides flexible interface for different database backends
2. **Connection Pooling**: Production-ready pooling for PostgreSQL and MySQL
3. **Transaction Management**: Built-in support for database transactions with rollback
4. **Migration System**: Version-controlled SQL migrations with automatic tracking

## Development Commands

### Package Management

```bash
# Install for local development (from repository root)
pip install -e ./ff-storage

# Install with development dependencies
pip install -e "./ff-storage[dev]"

# Build package
cd ff-storage && python -m build

# Build all packages
./scripts/build_all.sh
```

### Testing

```bash
# Run tests for specific package
cd ff-storage && pytest tests/

# Run with coverage
cd ff-storage && pytest --cov=ff_storage tests/

# Test all packages
./scripts/test_all.sh
```

### Code Quality

```bash
# Format code with black
cd ff-storage && black src/

# Lint with ruff
cd ff-storage && ruff check src/

# Type check (when mypy is added)
cd ff-storage && mypy src/
```

## Usage Examples

### Database Operations

```python
from ff_storage.db.postgres import PostgresPool

# Initialize connection pool
db = PostgresPool(
    dbname="fenix_db",
    user="fenix",
    password="password",
    host="localhost",
    port=5432,
    pool_size=20
)

# Connect and execute queries
db.connect()
results = db.read_query("SELECT * FROM documents WHERE status = %s", {"status": "active"})
db.close_connection()
```

### Migration Management

```python
from ff_storage.db.migrations import MigrationManager

manager = MigrationManager(db_connection, "./migrations")
manager.migrate()  # Run all pending migrations
```

## Integration with fenix-agents

This package is designed to support the Evidence-First Document QA System in fenix-agents by providing:
- Database connections for storing documents, questions, answers, and evidence
- File storage for document ingestion pipeline
- Migration management for schema evolution

When working on database-related features in fenix-agents, use ff-storage as the foundation for:
- PostgreSQL connections with pooling
- Transaction management for data consistency
- Schema migrations for database updates

## Installation from GitLab

For production use:
```bash
pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-storage
```

## Future Packages

The monorepo structure is designed to accommodate additional packages:
- `ff-tools`: Utility functions and helpers
- `ff-auth`: Authentication and authorization
- `ff-api`: Common API utilities and middleware