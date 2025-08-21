# ff-storage

Database and object storage operations for Fenixflow applications.

## Features

- **Database Connections**: PostgreSQL and MySQL with connection pooling
- **Multi-Database Support**: Consistent API for PostgreSQL and MySQL
- **Migration Management**: Simple SQL file-based migrations
- **Object Storage**: Async local filesystem and S3/S3-compatible storage
- **Streaming Support**: Read/write large files without loading into memory
- **Atomic Operations**: Safe file writes with temp file + rename
- **Metadata Management**: Store and retrieve metadata with objects
- **Base Models**: Dataclass-based models with UUID and timestamp support
- **Query Builder**: SQL query construction utilities

## Installation

```bash
# From GitLab
pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-storage

# Local development
pip install -e .
```

## Usage

### PostgreSQL Connection

```python
from ff_storage import PostgresPool

# Create connection pool
db = PostgresPool(
    dbname="fenix_db",
    user="fenix",
    password="password",
    host="localhost",
    port=5432,
    pool_size=20
)

# Connect and execute query
db.connect()
results = db.read_query("SELECT * FROM documents WHERE status = %s", {"status": "active"})

# Execute with RETURNING
new_id = db.execute_query(
    "INSERT INTO documents (title) VALUES (%s) RETURNING id",
    {"title": "New Document"}
)

# Return connection to pool
db.close_connection()
```

### MySQL Connection

```python
from ff_storage import MySQLPool

# Create connection pool
db = MySQLPool(
    dbname="fenix_db",
    user="root",
    password="password",
    host="localhost",
    port=3306,
    pool_size=10
)

# Connect and execute query
db.connect()
results = db.read_query("SELECT * FROM documents WHERE status = %s", {"status": "active"})

# Execute INSERT (returns last insert ID)
new_id = db.execute_query(
    "INSERT INTO documents (title) VALUES (%s)",
    {"title": "New Document"}
)

# Check open connections
open_conns = db.get_open_connections()

# Return connection to pool
db.close_connection()
```

### Migrations

```python
from ff_storage.db.migrations import MigrationManager

# Setup migration manager
manager = MigrationManager(db_connection, "./migrations")

# Run all pending migrations
manager.migrate()
```

### Object Storage

```python
from ff_storage import LocalObjectStorage, S3ObjectStorage
import asyncio

async def main():
    # Local filesystem storage
    local = LocalObjectStorage("/var/data/documents")
    await local.write("docs/report.pdf", pdf_bytes, {"content-type": "application/pdf"})
    data = await local.read("docs/report.pdf")
    exists = await local.exists("docs/report.pdf")
    files = await local.list_keys(prefix="docs/")
    
    # S3 storage (AWS or S3-compatible)
    s3 = S3ObjectStorage(
        bucket="fenix-documents",
        region="us-east-1"
    )
    await s3.write("docs/report.pdf", pdf_bytes)
    data = await s3.read("docs/report.pdf")
    
    # Stream large files
    async for chunk in s3.read_stream("large_file.bin", chunk_size=8192):
        process_chunk(chunk)

asyncio.run(main())
```

## Database Classes

### SQL Base Class
Abstract base providing interface for all SQL operations:
- `connect()`: Establish connection
- `read_query()`: Execute SELECT queries
- `execute()`: Execute INSERT/UPDATE/DELETE
- `execute_query()`: Execute with RETURNING
- `execute_many()`: Batch operations
- Transaction management methods

### PostgreSQL
- `Postgres`: Direct connection without pooling
- `PostgresPool`: Connection pooling for production use

### MySQL
- `MySQL`: Direct connection without pooling
- `MySQLPool`: Connection pooling for production use

## Testing

```bash
# Run tests
pytest tests/

# With coverage
pytest --cov=ff_storage tests/
```

## License

Proprietary - Fenixflow Internal Use Only