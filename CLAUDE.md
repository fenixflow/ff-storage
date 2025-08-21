# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fenix-Packages is a monorepo containing reusable Python packages for Fenixflow applications. The repository follows a modular architecture with each package providing specific functionality that can be independently installed and versioned.

### Current Packages

**ff-storage**: Database and object storage operations package providing:
- PostgreSQL and MySQL connections with connection pooling
- SQL query builder and transaction management
- Async object storage for local filesystem and S3/S3-compatible services
- Streaming support for large files without memory overhead
- Atomic writes with metadata management
- Migration management system for database schema updates

**ff-logger**: Scoped, instance-based logging package providing:
- Self-contained logger instances that can be passed as objects
- Context binding for permanent field attachment
- Multiple output formats (console, JSON, file, database, null)
- Zero external dependencies (built on Python's standard logging)

**ff-cli**: Unified CLI for the Fenix ecosystem with plugin architecture:
- Single `fenix` command entry point for all tools
- Plugin architecture allowing projects to add namespaced commands
- Dynamic plugin discovery via Python entry points
- Configuration management in `~/.fenix/config.toml`
- uvx compatible for easy execution without installation

## Architecture

### ff-storage Package Structure

The package follows a layered architecture:

**Database Layer** (`src/ff_storage/db/`):
- `sql.py`: Abstract SQL base class defining the interface for all database operations
- `postgres.py`: PostgreSQL implementation with direct connection and connection pooling
- `models.py`: Dataclass-based models with UUID and timestamp support
- `migrations.py`: SQL file-based migration management system

**Object Storage Layer** (`src/ff_storage/object/`):
- `base.py`: Abstract ObjectStorage base class defining the async interface
- `local.py`: LocalObjectStorage with atomic writes and metadata sidecar files
- `s3.py`: S3ObjectStorage supporting AWS S3 and S3-compatible services (MinIO, etc.)
- Features: streaming, multipart upload, metadata management, path traversal protection

### ff-logger Package Structure

Instance-based logging architecture:

**Core Components** (`src/ff_logger/`):
- `base.py`: ScopedLogger base class for all logger types
- `console.py`: Human-readable colored console output
- `json_logger.py`: Structured JSON logging for aggregation
- `file.py`: File logging with rotation support
- `database.py`: Database logging integration
- `null.py`: Zero-cost null logger for testing

### ff-cli Package Structure

Plugin-based CLI architecture:

**Core Components** (`src/ff_cli/`):
- `main.py`: Main CLI entry point with plugin loading
- `plugin_manager.py`: Dynamic plugin discovery and registration
- `config.py`: Configuration management with TOML
- `commands/plugins.py`: Built-in plugin management commands

**Plugin System**:
- Plugins are Python packages with Typer apps
- Register via entry points in pyproject.toml
- Loaded as namespaced subcommands (e.g., `fenix ff-agents status`)

### Key Design Patterns

1. **Abstract Base Classes**: SQL base class provides flexible interface for different database backends
2. **Connection Pooling**: Production-ready pooling for PostgreSQL and MySQL
3. **Transaction Management**: Built-in support for database transactions with rollback
4. **Migration System**: Version-controlled SQL migrations with automatic tracking
5. **Scoped Loggers**: Instance-based loggers that can be passed as dependencies
6. **Plugin Architecture**: Extensible CLI through Python entry points

## Development Commands

### Package Management

```bash
# Install for local development (from repository root)
uv pip install -e ./ff-storage
uv pip install -e ./ff-logger
uv pip install -e ./ff-cli

# Install with development dependencies
uv pip install -e "./ff-storage[dev]"
uv pip install -e "./ff-logger[dev]"
uv pip install -e "./ff-cli[dev]"

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

### Database Operations (ff-storage)

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

### Object Storage (ff-storage)

```python
from ff_storage import LocalObjectStorage, S3ObjectStorage

# Local storage
storage = LocalObjectStorage("/path/to/storage")
await storage.write("documents/file.pdf", data, {"content-type": "application/pdf"})
data = await storage.read("documents/file.pdf")

# S3 storage
storage = S3ObjectStorage(bucket="my-bucket", region="us-east-1")
await storage.write("documents/file.pdf", data)

# Streaming for large files
async for chunk in storage.read_stream("large_file.bin", chunk_size=8192):
    process_chunk(chunk)
```

### Logging (ff-logger)

```python
from ff_logger import ConsoleLogger, NullLogger

# Create a scoped logger with context
logger = ConsoleLogger(
    name="my_service",
    context={"service": "api", "env": "prod"}
)

# All logs include the context
logger.info("Request received", request_id="123")

# Pass logger as dependency
def process_data(data, logger=NullLogger):
    logger.info("Processing data")
    return data
```

### CLI Usage (ff-cli)

```bash
# Install the CLI
uv pip install git+https://gitlab.com/fenixflow/fenix-packages.git#subdirectory=ff-cli

# Install a plugin
fenix plugins install git+https://gitlab.com/fenixflow/fenix-agents.git

# Use plugin commands
fenix ff-agents status
fenix ff-agents run workflow

# Run with uvx (no installation)
uvx --from git+https://gitlab.com/fenixflow/fenix-packages.git#subdirectory=ff-cli fenix --help
```

### Creating a CLI Plugin

```python
# In your project's cli_plugin.py
import typer

app = typer.Typer(help="My project CLI plugin")

@app.command()
def status():
    """Check project status."""
    print("Project is running")

def plugin():
    return app
```

```toml
# In your project's pyproject.toml
[project.entry-points."fenix.plugins"]
ff-myproject = "myproject.cli_plugin:plugin"
```

## Integration with fenix-agents

These packages are designed to support the Evidence-First Document QA System in fenix-agents:

**ff-storage**:
- Database connections for storing documents, questions, answers, and evidence
- File storage for document ingestion pipeline
- Migration management for schema evolution

**ff-logger**:
- Scoped logging for request tracking
- Structured logging for observability
- Context propagation through processing pipelines

**ff-cli**:
- Unified CLI for agent operations
- Plugin architecture for fenix-agents commands
- Consistent interface for both developers and AI agents

When working on fenix-agents, use these packages as foundations:
- ff-storage for all database and file operations
- ff-logger for consistent logging across services
- ff-cli plugin for exposing agent commands

## Installation from GitLab

For production use:
```bash
# Install individual packages
uv pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-storage
uv pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-logger
uv pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-cli

# Or use uvx for the CLI without installation
uvx --from git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-cli fenix --help
```

## Python Version Requirement

All packages in this repository require **Python 3.12+** for stability and modern features.

## Future Packages

The monorepo structure is designed to accommodate additional packages:
- `ff-tools`: Utility functions and helpers
- `ff-auth`: Authentication and authorization
- `ff-api`: Common API utilities and middleware
- `ff-ml`: Machine learning utilities and model management
- `ff-cache`: Caching abstractions for Redis/Memcached