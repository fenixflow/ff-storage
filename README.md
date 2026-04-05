# ff-storage

[![PyPI version](https://badge.fury.io/py/ff-storage.svg)](https://badge.fury.io/py/ff-storage)
[![Python Support](https://img.shields.io/pypi/pyversions/ff-storage.svg)](https://pypi.org/project/ff-storage/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A comprehensive storage package for Fenixflow applications, providing **async connection pools** for modern Python applications, database connections, object storage abstractions, migration management, and model utilities. Supports PostgreSQL, MySQL, Microsoft SQL Server, local filesystem storage, S3-compatible services, and Azure Blob Storage.

Created by **Ben Moag** at **[Fenixflow](https://fenixflow.com)**

## 🧪 Version 4.8.0 - Mock Data Generation & ERD

**New testing infrastructure**:

- **Mock Factory** - Generate realistic test data from Pydantic models
- **ERD Builder** - Auto-discover models and generate Entity Relationship Diagrams
- **Generator Extensions** - Add domain-specific patterns for your industry

```python
from ff_storage import PydanticModel, Field
from ff_storage.mock import MockFactory, GeneratorExtension
from ff_storage.erd import ERDBuilder, to_mermaid

# Simple mock creation - uses Field() constraints
user = User.create_mock(seed=42)
users = User.create_mock_batch(100, seed=42)

# Custom patterns for your domain
class InsuranceExtension(GeneratorExtension):
    NAME_PATTERNS = [
        (r"^policy_number$", lambda f, m: f.bothify("POL-####-????").upper()),
        (r"^premium$", lambda f, m: Decimal(str(f.pyfloat(100, 10000)))),
    ]

factory = MockFactory(seed=42)
factory.registry.extend(InsuranceExtension())
policy = factory.create(Policy)

# ERD generation
builder = ERDBuilder()
erd = builder.build()
print(to_mermaid(erd))  # Mermaid diagram syntax
```

**100% backward compatible** - all existing code works unchanged.

---

## 🔥 Version 4.7.0 - Query Builder & Relationships

**Major new features**:

- **Query Builder** - Fluent, type-safe query API with JOINs and aggregations
- **Relationships** - ORM-style model relationships with eager loading
- **Transactions** - Full transaction management with Unit of Work pattern
- **Bulk Operations** - Efficient batch insert/update/delete

```python
from ff_storage import Query, F, Relationship

# Fluent query API
results = await (
    Query(Product)
    .filter(F.price > 100)
    .filter(F.status == "active")
    .order_by(F.created_at.desc())
    .limit(10)
    .execute(db_pool, tenant_id=tenant)
)

# Model relationships
class Author(PydanticModel):
    posts: list["Post"] = Relationship(back_populates="author")

# Eager loading (prevents N+1 queries)
authors = await Query(Author).load(["posts"]).execute(db_pool)
```

**100% backward compatible** - all existing code works unchanged.

---

## 🎯 Version 4.4.0 - Multi-Tenant Permissive Scope

Flexible multi-tenant access with separate `tenant_id` and `tenant_ids` parameters:

- **🔒 Strict Scope** (`tenant_id`): Single UUID - forces tenant_id on writes, strict isolation for broker/UW operations
- **🌐 Permissive Scope** (`tenant_ids`): List of UUIDs - validates writes, enables admin cross-tenant queries
- **✅ Clear Semantics** - Different behavior for single vs multi-tenant use cases

```python
# Strict scope (broker writes) - forces tenant_id on all records
repo = PydanticRepository(Product, db_pool, tenant_id=org_id)

# Permissive scope (admin reads) - IN clause filtering
repo_admin = PydanticRepository(Product, db_pool, tenant_ids=[tenant1, tenant2])
```

---

## 🎉 Version 3.0.0 - Pydantic ORM & Temporal Data Management

**Major features in v3.0.0**: Production-ready Pydantic ORM with built-in temporal data management!

- **🔥 Pydantic Models** - Type-safe models with automatic schema generation
- **⏱️ Temporal Strategies** - Choose from 3 strategies: none, copy_on_change (audit trail), scd2 (time travel)
- **🎯 Multi-Tenant by Default** - Automatic tenant_id injection and filtering
- **📝 Audit Trails** - Field-level change tracking with copy_on_change
- **⏰ Time Travel** - Query historical data with scd2 strategy
- **🔧 Rich Field Metadata** - Complete SQL control (FK, CHECK, defaults, partial indexes)
- **🚀 Auto-Sync Schema** - SchemaManager now creates auxiliary tables (audit tables)

**[📚 Documentation](docs/README.md)** | **[⚡ Quickstart Guide](docs/quickstart.md)** | **[🎯 Strategy Selection](docs/guides/strategy_selection.md)**

**Backwards Compatible**: All v2 features work unchanged. v3 is fully opt-in.

---

## Version 2.0.0 - Schema Sync System

**Added in 2.0.0**: Terraform-like automatic schema synchronization! Define schema in model classes and let SchemaManager handle migrations automatically.

**Important**: v3.3.0 fixes critical false positive detection bugs in schema sync. Upgrade from v2.x/v3.2.x immediately.

**Breaking Change in 2.0.0**: Removed file-based migrations (`MigrationManager`). Use `SchemaManager` for automatic schema sync from model definitions.

**New in 1.1.0**: Added Azure Blob Storage backend with support for both Azurite (local development) and production Azure Blob Storage.

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

### Async Pool (FastAPI, Production)

```python
from ff_storage.db import PostgresPool

# Create async connection pool
pool = PostgresPool(
    dbname="fenix_db",
    user="fenix",
    password="password",
    host="localhost",
    port=5432,
    min_size=10,
    max_size=20
)

# Connect once at startup
await pool.connect()

# Use many times - pool handles connections internally
# Returns dictionaries by default for easy access
results = await pool.fetch_all("SELECT id, title, status FROM documents WHERE status = $1", "active")
# results = [{'id': 1, 'title': 'Doc 1', 'status': 'active'}, ...]

print(results[0]['title'])  # Access by column name - intuitive!

# Fetch single row
user = await pool.fetch_one("SELECT id, name, email FROM users WHERE id = $1", 123)
# user = {'id': 123, 'name': 'Alice', 'email': 'alice@example.com'}

# Disconnect once at shutdown
await pool.disconnect()
```

### Sync Connection (Scripts, Simple Apps)

```python
from ff_storage.db import Postgres

# Create direct connection
db = Postgres(
    dbname="fenix_db",
    user="fenix",
    password="password",
    host="localhost",
    port=5432
)

# Connect and query - returns dicts by default
db.connect()
results = db.read_query("SELECT id, title, status FROM documents WHERE status = %(status)s", {"status": "active"})
# results = [{'id': 1, 'title': 'Doc 1', 'status': 'active'}, ...]

print(results[0]['title'])  # Easy access by column name

db.close_connection()
```

### FastAPI Integration

```python
from fastapi import FastAPI
from ff_storage.db import PostgresPool

app = FastAPI()

# Create pool once
app.state.db = PostgresPool(
    dbname="fenix_db",
    user="fenix",
    password="password",
    host="localhost",
    min_size=10,
    max_size=20
)

@app.on_event("startup")
async def startup():
    await app.state.db.connect()

@app.on_event("shutdown")
async def shutdown():
    await app.state.db.disconnect()

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    # Pool handles connection automatically
    user = await app.state.db.fetch_one(
        "SELECT * FROM users WHERE id = $1", user_id
    )
    return user
```

## Migration Guide

### v3.2.x → v3.3.0 (Backward Compatible)

**No action required** - Internal architecture improvements only.

**Changes**:
- Schema normalization now centralized (eliminates false positives)
- WHERE clause parser added (fixes precedence bugs)
- All public APIs unchanged

**Impact**: If using schema sync, upgrade immediately to eliminate false positives causing index recreation on every run.

### v2.x → v3.0.0 (Breaking - Pydantic ORM)

See [docs/quickstart.md](docs/quickstart.md) for full migration guide.

### v0.x → v1.0.0 (Breaking - Async Pools)

**Pools are now async** - all `*Pool` classes require `await`. Use direct connections for sync code (Postgres, MySQL, SQLServer - unchanged).

## Features

### Database Operations
- **Async Connection Pools**: High-performance async pools for PostgreSQL, MySQL, and SQL Server
- **Sync Direct Connections**: Simple sync connections for scripts and non-async code
- **Multi-Database Support**: Uniform interface across PostgreSQL, MySQL, and Microsoft SQL Server
- **Transaction Management**: Full transaction support with savepoints and isolation levels
- **Batch Operations**: Execute many queries efficiently with bulk insert/update/delete
- **Query Builder**: Fluent, type-safe query API with JOINs and aggregations
- **Model Relationships**: ORM-style relationships with eager loading (N+1 prevention)

### Schema Sync System (v2.0.0+, Fixed in v3.3.0)
- **Production-Ready**: v3.3.0 fixes critical false positive detection bugs
- **Normalization Framework**: Centralized schema comparison (eliminates index churn)
- **WHERE Clause Parser**: SQL AST parsing with proper precedence handling
- **Terraform-like Migrations**: Define schema in code, auto-sync on startup
- **Automatic Detection**: Detects schema changes from model definitions
- **Safe by Default**: Additive changes auto-apply, destructive changes require explicit approval
- **Dry Run Mode**: Preview changes without applying them
- **Transaction-Wrapped**: All changes in single atomic transaction
- **Provider Detection**: Auto-detects PostgreSQL, MySQL, or SQL Server

### Object Storage
- **Multiple Backends**: Local filesystem, S3/S3-compatible services, and Azure Blob Storage
- **Async Operations**: Non-blocking I/O for better performance
- **Streaming Support**: Handle large files without memory overhead
- **Atomic Writes**: Safe file operations with temp file + rename
- **Metadata Management**: Store and retrieve metadata with objects

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

# Use connection from pool - returns dicts by default
db.connect()
try:
    # Execute queries - returns list of dicts
    results = db.read_query("SELECT id, title, status FROM documents WHERE status = %s", {"status": "active"})
    # results = [{'id': 1, 'title': 'Doc 1', 'status': 'active'}, ...]
    print(results[0]['title'])  # Easy access by column name

    # Execute with RETURNING
    new_id = db.execute_query(
        "INSERT INTO documents (title) VALUES (%s) RETURNING id",
        {"title": "New Document"}
    )
    # new_id = [{'id': 123}]

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

# Similar usage pattern as PostgreSQL - returns dicts by default
db.connect()
results = db.read_query("SELECT id, title, status FROM documents WHERE status = %s", {"status": "active"})
# results = [{'id': 1, 'title': 'Doc 1', 'status': 'active'}, ...]
print(results[0]['title'])  # Easy access by column name
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

# Connect and execute queries - returns dicts by default
db.connect()
try:
    # Read query - returns list of dicts
    results = db.read_query("SELECT id, title, status FROM documents WHERE status = ?", {"status": "active"})
    # results = [{'id': 1, 'title': 'Doc 1', 'status': 'active'}, ...]
    print(results[0]['title'])  # Easy access by column name

    # Execute with OUTPUT clause
    new_id = db.execute_query(
        "INSERT INTO documents (title) OUTPUT INSERTED.id VALUES (?)",
        {"title": "New Document"}
    )
    # new_id = [{'id': 123}]

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

#### Azure Blob Storage
```python
from ff_storage import AzureBlobObjectStorage
from azure.identity import DefaultAzureCredential
import asyncio

async def main():
    # Azurite (local development with connection string)
    storage = AzureBlobObjectStorage(
        container_name="fenix-documents",
        connection_string="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    )

    # Production with connection string (access key)
    storage = AzureBlobObjectStorage(
        container_name="fenix-documents",
        connection_string="DefaultEndpointsProtocol=https;AccountName=myaccount;AccountKey=...;EndpointSuffix=core.windows.net",
        prefix="documents/"  # Optional prefix for all keys
    )

    # Production with Managed Identity (DefaultAzureCredential)
    storage = AzureBlobObjectStorage(
        container_name="fenix-documents",
        account_url="https://mystorageaccount.blob.core.windows.net"
    )

    # Production with custom credential
    storage = AzureBlobObjectStorage(
        container_name="fenix-documents",
        account_url="https://mystorageaccount.blob.core.windows.net",
        credential=DefaultAzureCredential()
    )

    # Write file with metadata
    await storage.write(
        "reports/2025/quarterly.pdf",
        pdf_bytes,
        metadata={"content-type": "application/pdf", "author": "system"}
    )

    # Read file
    data = await storage.read("reports/2025/quarterly.pdf")

    # Stream large files
    async for chunk in storage.read_stream("large_file.bin", chunk_size=8192):
        await process_chunk(chunk)

    # Check existence
    exists = await storage.exists("reports/2025/quarterly.pdf")

    # List blobs with prefix
    files = await storage.list_keys(prefix="reports/2025/")

    # Get metadata
    metadata = await storage.get_metadata("reports/2025/quarterly.pdf")
    print(metadata["content-type"])

    # Delete blob
    await storage.delete("reports/2025/quarterly.pdf")

asyncio.run(main())
```

**Note**: Azure Blob Storage has restrictions on metadata keys (must be valid C# identifiers). The implementation automatically converts hyphens to underscores (e.g., `content-type` becomes `content_type`) when storing and converts them back when retrieving.

### Schema Sync (Terraform-like Migrations)

```python
from ff_storage import Postgres, SchemaManager, PydanticModel, Field

# Define your model with PydanticModel
class Document(PydanticModel):
    __table_name__ = "documents"
    __schema__ = "public"

    title: str = Field(max_length=255)
    content: str | None = None
    status: str = Field(default="draft", max_length=50)

# Connect to database
db = Postgres(dbname="mydb", user="user", password="pass", host="localhost", port=5432)
db.connect()

# Create schema manager (auto-detects PostgreSQL)
manager = SchemaManager(db)

# Dry run to preview changes
print("Preview of changes:")
manager.sync_schema(
    models=[Document],
    allow_destructive=False,
    dry_run=True
)

# Apply changes automatically
changes_applied = manager.sync_schema(
    models=[Document],
    allow_destructive=False,  # Safe by default
    dry_run=False
)

print(f"Applied {changes_applied} schema changes")
```

**Features**:
- **Automatic Detection**: Detects new tables, missing columns, and indexes
- **Safe by Default**: Additive changes (CREATE, ADD) auto-apply; destructive changes (DROP) require explicit flag
- **Dry Run Mode**: Preview all changes before applying
- **Transaction-Wrapped**: All changes in a single atomic transaction
- **Provider-Agnostic**: Works with PostgreSQL (full support), MySQL/SQL Server (stubs for future implementation)

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

### Fluent Query Builder (v4.7.0+)

```python
from ff_storage import Query, F, AND, OR

# Simple filtering
products = await (
    Query(Product)
    .filter(F.price > 100)
    .filter(F.status == "active")
    .order_by(F.created_at.desc())
    .limit(10)
    .execute(db_pool, tenant_id=tenant)
)

# Complex filters with AND/OR
results = await (
    Query(Product)
    .filter(AND(
        F.category == "electronics",
        OR(F.price < 50, F.on_sale == True)
    ))
    .execute(db_pool)
)

# String operations
results = await (
    Query(User)
    .filter(F.email.icontains("@example.com"))
    .filter(F.name.startswith("John"))
    .execute(db_pool)
)

# Aggregations
from ff_storage import func

total = await (
    Query(Order)
    .filter(F.status == "completed")
    .select(func.sum(F.total))
    .execute(db_pool)
)

# First result or None
user = await Query(User).filter(F.email == email).first(db_pool)

# Check existence
exists = await Query(User).filter(F.email == email).exists(db_pool)
```

### Model Relationships (v4.7.0+)

```python
from ff_storage import PydanticModel, Relationship, Field

class Author(PydanticModel):
    __table_name__ = "authors"
    name: str = Field(max_length=255)

    # One-to-many relationship
    posts: list["Post"] = Relationship(back_populates="author")

class Post(PydanticModel):
    __table_name__ = "posts"
    title: str = Field(max_length=255)
    author_id: UUID  # Foreign key

    # Many-to-one relationship
    author: "Author" = Relationship(back_populates="posts")

# Query with JOINs
results = await (
    Query(Author)
    .filter(F.name.contains("John"))
    .join(Author.posts)  # JOIN posts table
    .execute(db_pool)
)

# Eager loading (prevents N+1 queries)
authors = await (
    Query(Author)
    .load(["posts"])  # Batch load all posts
    .execute(db_pool)
)

for author in authors:
    print(f"{author.name} has {len(author.posts)} posts")
```

### Transactions (v4.7.0+)

```python
from ff_storage import Transaction, IsolationLevel

# Simple transaction
async with Transaction(db_pool) as tx:
    await tx.execute("INSERT INTO orders ...")
    await tx.execute("UPDATE inventory ...")
    # Auto-commits on success, rollbacks on exception

# With isolation level
async with Transaction(db_pool, isolation=IsolationLevel.SERIALIZABLE) as tx:
    await tx.execute("SELECT ... FOR UPDATE")
    await tx.execute("UPDATE ...")

# Savepoints for nested transactions
async with Transaction(db_pool) as tx:
    await tx.execute("INSERT INTO parent ...")

    async with tx.savepoint("child_ops"):
        await tx.execute("INSERT INTO child ...")
        # Can rollback just this savepoint
```

### Legacy Query Builder Utilities
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