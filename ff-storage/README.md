# ff-storage

[![PyPI version](https://badge.fury.io/py/ff-storage.svg)](https://badge.fury.io/py/ff-storage)
[![Python Support](https://img.shields.io/pypi/pyversions/ff-storage.svg)](https://pypi.org/project/ff-storage/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A comprehensive storage package for Fenixflow applications, providing database connections with pooling, object storage abstractions, migration management, and model utilities. Supports PostgreSQL, MySQL, Microsoft SQL Server, local filesystem storage, and S3-compatible services.

Created by **Ben Moag** at **[Fenixflow](https://fenixflow.com)**

## Quick Start

### Installation

#### From PyPI
```bash
pip install ff-storage
```

#### From GitLab
```bash
pip install git+https://gitlab.com/fenixflow/fenix-packages.git#subdirectory=ff-storage
```

### Basic Usage

```python
from ff_storage import PostgresPool

# Create a connection pool
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

## Features

### Database Operations
- **Multi-Database Support**: PostgreSQL, MySQL, and Microsoft SQL Server with connection pooling
- **Consistent API**: Same interface across all database types
- **Transaction Management**: Built-in support for transactions with rollback
- **Batch Operations**: Execute many queries efficiently
- **Query Builder**: SQL query construction utilities

### Object Storage
- **Multiple Backends**: Local filesystem and S3/S3-compatible services
- **Async Operations**: Non-blocking I/O for better performance
- **Streaming Support**: Handle large files without memory overhead
- **Atomic Writes**: Safe file operations with temp file + rename
- **Metadata Management**: Store and retrieve metadata with objects

### Migration System
- **SQL File-Based**: Simple, version-controlled migrations
- **Automatic Tracking**: Keeps track of applied migrations
- **Rollback Support**: Undo migrations when needed

## Core Components

### Database Connections

#### PostgreSQL with Connection Pooling
```python
from ff_storage import PostgresPool

# Initialize pool
db = PostgresPool(
    dbname="fenix_db",
    user="fenix",
    password="password",
    host="localhost",
    port=5432,
    pool_size=20
)

# Use connection from pool
db.connect()
try:
    # Execute queries
    results = db.read_query("SELECT * FROM documents WHERE status = %s", {"status": "active"})

    # Execute with RETURNING
    new_id = db.execute_query(
        "INSERT INTO documents (title) VALUES (%s) RETURNING id",
        {"title": "New Document"}
    )

    # Transaction example
    db.begin_transaction()
    try:
        db.execute("UPDATE documents SET status = %s WHERE id = %s", {"status": "archived", "id": 123})
        db.execute("INSERT INTO audit_log (action) VALUES (%s)", {"action": "archive"})
        db.commit_transaction()
    except Exception:
        db.rollback_transaction()
        raise
finally:
    # Return connection to pool
    db.close_connection()
```

#### MySQL with Connection Pooling
```python
from ff_storage import MySQLPool

# Initialize pool
db = MySQLPool(
    dbname="fenix_db",
    user="root",
    password="password",
    host="localhost",
    port=3306,
    pool_size=10
)

# Similar usage pattern as PostgreSQL
db.connect()
results = db.read_query("SELECT * FROM documents WHERE status = %s", {"status": "active"})
db.close_connection()
```

#### Microsoft SQL Server with Connection Pooling
```python
from ff_storage import SQLServerPool

# Initialize pool
db = SQLServerPool(
    dbname="fenix_db",
    user="sa",
    password="YourPassword123",
    host="localhost",
    port=1433,
    driver="ODBC Driver 18 for SQL Server",
    pool_size=10
)

# Connect and execute queries
db.connect()
try:
    # Read query
    results = db.read_query("SELECT * FROM documents WHERE status = ?", {"status": "active"})

    # Execute with OUTPUT clause
    new_id = db.execute_query(
        "INSERT INTO documents (title) OUTPUT INSERTED.id VALUES (?)",
        {"title": "New Document"}
    )

    # Check table existence
    if db.table_exists("users", schema="dbo"):
        columns = db.get_table_columns("users", schema="dbo")
finally:
    db.close_connection()
```

### Object Storage

#### Local Filesystem Storage
```python
from ff_storage import LocalObjectStorage
import asyncio

async def main():
    # Initialize local storage
    storage = LocalObjectStorage("/var/data/documents")

    # Write file with metadata
    await storage.write(
        "reports/2025/quarterly.pdf",
        pdf_bytes,
        metadata={"content-type": "application/pdf", "author": "system"}
    )

    # Read file
    data = await storage.read("reports/2025/quarterly.pdf")

    # Check existence
    exists = await storage.exists("reports/2025/quarterly.pdf")

    # List files with prefix
    files = await storage.list_keys(prefix="reports/2025/")

    # Delete file
    await storage.delete("reports/2025/quarterly.pdf")

asyncio.run(main())
```

#### S3-Compatible Storage
```python
from ff_storage import S3ObjectStorage
import asyncio

async def main():
    # AWS S3
    s3 = S3ObjectStorage(
        bucket="fenix-documents",
        region="us-east-1"
    )

    # Or MinIO/other S3-compatible
    s3 = S3ObjectStorage(
        bucket="fenix-documents",
        endpoint_url="http://localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin"
    )

    # Write file
    await s3.write("docs/report.pdf", pdf_bytes)

    # Stream large files
    async for chunk in s3.read_stream("large_file.bin", chunk_size=8192):
        await process_chunk(chunk)

    # Multipart upload for large files (automatic)
    await s3.write("huge_file.bin", huge_data)  # Automatically uses multipart if > 5MB

asyncio.run(main())
```

### Migration Management

```python
from ff_storage.db.migrations import MigrationManager

# Setup migration manager
manager = MigrationManager(db_connection, "./migrations")

# Run all pending migrations
manager.migrate()

# Create new migration
manager.create_migration("add_user_roles")

# Check migration status
pending = manager.get_pending_migrations()
applied = manager.get_applied_migrations()
```

Migration files follow the naming pattern: `001_initial_schema.sql`, `002_add_indexes.sql`, etc.

### Base Models

```python
from ff_storage.db.models import BaseModel, BaseModelWithDates
from dataclasses import dataclass
from typing import Optional
import uuid

@dataclass
class Document(BaseModelWithDates):
    title: str
    content: str
    status: str = "draft"
    author_id: Optional[uuid.UUID] = None

# Automatic UUID and timestamp handling
doc = Document(
    title="Quarterly Report",
    content="...",
    status="published"
)
# doc.id = UUID automatically generated
# doc.created_at = current timestamp
# doc.updated_at = current timestamp
```

## Advanced Features

### Transaction Management
```python
# Context manager for automatic transaction handling
async def transfer_ownership(db, doc_id, new_owner_id):
    db.begin_transaction()
    try:
        # Multiple operations in single transaction
        db.execute("UPDATE documents SET owner_id = %s WHERE id = %s",
                  {"owner_id": new_owner_id, "id": doc_id})
        db.execute("INSERT INTO audit_log (action, doc_id, user_id) VALUES (%s, %s, %s)",
                  {"action": "transfer", "doc_id": doc_id, "user_id": new_owner_id})
        db.commit_transaction()
    except Exception as e:
        db.rollback_transaction()
        raise
```

### Connection Pool Monitoring
```python
# Check pool statistics
pool = PostgresPool(...)
open_connections = pool.get_open_connections()
print(f"Open connections: {open_connections}")

# Graceful shutdown
pool.close_all_connections()
```

### Query Builder Utilities
```python
from ff_storage.db.sql import build_insert, build_update, build_select

# Build INSERT query
query, params = build_insert("documents", {
    "title": "New Doc",
    "status": "draft"
})

# Build UPDATE query
query, params = build_update("documents",
    {"status": "published"},
    {"id": doc_id}
)

# Build SELECT with conditions
query, params = build_select("documents",
    columns=["id", "title"],
    where={"status": "published", "author_id": user_id}
)
```

## Error Handling

```python
from ff_storage.exceptions import StorageError, DatabaseError

try:
    db.connect()
    results = db.read_query("SELECT * FROM documents")
except DatabaseError as e:
    print(f"Database error: {e}")
except StorageError as e:
    print(f"Storage error: {e}")
finally:
    db.close_connection()
```

## Testing

```bash
# Run tests
pytest tests/

# With coverage
pytest --cov=ff_storage tests/

# Run specific test file
pytest tests/test_postgres.py

# Run with verbose output
pytest -v tests/
```

## Configuration

### Environment Variables
```bash
# Database
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=fenix_db
export DB_USER=fenix
export DB_PASSWORD=secret

# S3 Storage
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
export AWS_DEFAULT_REGION=us-east-1

# Local Storage
export STORAGE_PATH=/var/data/documents
```

### Configuration File
```python
# config.py
from ff_storage import PostgresPool, S3ObjectStorage

# Database configuration
DATABASE = {
    "dbname": os.getenv("DB_NAME", "fenix_db"),
    "user": os.getenv("DB_USER", "fenix"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "pool_size": 20
}

# Storage configuration
STORAGE = {
    "bucket": os.getenv("S3_BUCKET", "fenix-documents"),
    "region": os.getenv("AWS_DEFAULT_REGION", "us-east-1")
}

# Initialize
db = PostgresPool(**DATABASE)
storage = S3ObjectStorage(**STORAGE)
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - See [LICENSE](LICENSE) file for details.

## Author

Created and maintained by **Ben Moag** at **[Fenixflow](https://fenixflow.com)**

For more information, visit the [GitLab repository](https://gitlab.com/fenixflow/fenix-packages).