# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Important Git Commit Guidelines

**CRITICAL: ALL commits must appear to be made entirely by the human developer. NO AI attribution whatsoever.**

When creating git commits:
- NEVER add Claude, Claude Code, or any AI as an author or co-author
- NEVER include "Generated with Claude Code", "Co-Authored-By: Claude", or similar AI attribution
- NEVER use "Claude Code" or "Claude" as the git author name
- ALWAYS use the existing git user configuration (Ben <ben@fenixflow.com> for this repository)
- ALWAYS write commit messages as if written by the human developer
- ALWAYS follow conventional commit format without ANY AI attribution or references
- If git config shows "Claude Code" as the author, STOP and reconfigure it to the human developer's name before committing

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
- Optional dynamic branding system for custom configurations
- Plugin architecture allowing projects to add namespaced commands
- Service management for Docker containers (PostgreSQL, Redis, RabbitMQ, MinIO)
- Enhanced status command with health checks and recommendations
- Dynamic plugin discovery via Python entry points
- Configuration management in `~/.fenix/config.toml` (or custom branded directory)
- uvx compatible for easy execution without installation

**ff-parsers**: Document parsing utilities for various formats:
- Multi-format document parsing (PDF, DOCX, JSON, Markdown, etc.)
- Text extraction from PDFs and Office documents
- Structured data extraction and metadata parsing
- Streaming support for large files
- Extensible parser architecture for adding new formats

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

Plugin-based CLI architecture with enhanced features:

**Core Components** (`src/ff_cli/`):
- `main.py`: Main CLI entry point with plugin loading
- `branding.py`: Dynamic branding configuration system
- `plugin_manager.py`: Dynamic plugin discovery and registration
- `plugin_base.py`: Base classes for plugin development with health checks
- `plugin_creator.py`: Interactive plugin scaffolding tool
- `config.py`: Enhanced configuration management with TOML
- `commands/plugins.py`: Built-in plugin management commands
- `commands/services.py`: Docker service management commands
- `commands/status.py`: Unified status command with health aggregation
- `commands/branding.py`: Branding configuration commands

**Service Management** (`src/ff_cli/services/`):
- `manager.py`: Docker Compose-based service orchestration
- `models.py`: Service configuration models
- Default service definitions for PostgreSQL, Redis, RabbitMQ, MinIO

**Utilities** (`src/ff_cli/utils/`):
- `docker.py`: Docker and OrbStack integration utilities
- `shell.py`: Shell execution and environment management
- `editor.py`: Interactive file editing support
- `scaffold.py`: Template-based file generation

**Plugin System**:
- Plugins are Python packages with Typer apps
- Register via entry points in pyproject.toml
- Loaded as namespaced subcommands (e.g., `fenix ff-agents status`)
- Enhanced base classes for status reporting and health checks

### ff-parsers Package Structure

Document parsing architecture:

**Core Components** (`src/ff_parsers/`):
- `base.py`: Abstract base classes for parser implementations
- `pdf.py`: PDF document parsing with text and metadata extraction
- `docx.py`: Microsoft Word document parsing
- `markdown.py`: Markdown parsing and processing
- `json_parser.py`: JSON and structured data parsing
- Features: streaming support, metadata extraction, extensible architecture

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
uv pip install -e ./ff-parsers

# Install with development dependencies
uv pip install -e "./ff-storage[dev]"
uv pip install -e "./ff-logger[dev]"
uv pip install -e "./ff-cli[dev]"
uv pip install -e "./ff-parsers[dev]"

# Build package
cd ff-storage && python -m build
```

### Testing

```bash
# Run tests for specific package
cd ff-storage && pytest tests/

# Run with coverage
cd ff-storage && pytest --cov=ff_storage tests/
```

### Code Quality

```bash
# Format code with isort and ruff
cd ff-storage && uvx isort . && uvx ruff format .

# Lint with ruff
cd ff-storage && uvx ruff check --fix .

# Type check (when mypy is added)
cd ff-storage && mypy src/
```

### Publishing (packages_plugin)

```bash
# List all publishable packages
fenix ff-packages list

# Check authentication status
fenix ff-packages check

# Publish to PyPI
fenix ff-packages pypi ff-storage

# Mirror to GitHub
fenix ff-packages github ff-storage

# Full sync (test, build, mirror, publish)
fenix ff-packages sync ff-storage
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

# Configure custom branding (optional)
fenix branding configure
fenix branding show

# Manage services
fenix services init
fenix services up postgres
fenix services list
fenix services down --all

# Install a plugin
fenix plugins install git+https://gitlab.com/fenixflow/fenix-agents.git
fenix plugins list
fenix plugins create my-plugin

# Use plugin commands
fenix ff-agents status
fenix ff-agents run workflow

# Check overall system status
fenix status
fenix status --json

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

**ff-parsers**:
- Document parsing for ingestion pipeline
- Support for multiple document formats
- Text and metadata extraction for processing

When working on fenix-agents, use these packages as foundations:
- ff-storage for all database and file operations
- ff-logger for consistent logging across services
- ff-cli plugin for exposing agent commands
- ff-parsers for document processing and extraction

## Installation from GitLab

For production use:
```bash
# Install individual packages
uv pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-storage
uv pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-logger
uv pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-cli
uv pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-parsers

# Or use uvx for the CLI without installation
uvx --from git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-cli fenix --help
```

## Python Version Requirement

All packages in this repository require **Python 3.10+** for stability and modern features.

## CI/CD Pipeline

### Automatic Pipeline
The repository uses a simple, reliable CI/CD pipeline that:
- Builds all packages in parallel using GitLab's native matrix jobs
- Runs tests for all packages in parallel
- Publishes to GitLab Package Registry when merged to main (if version doesn't exist)
- Requires manual version updates in pyproject.toml files

### Manual Release Pipeline
A separate manual release pipeline (`.gitlab-ci-manual-release.yml`) provides:
- Selective package releases via dropdown inputs
- Semantic version bumping (none/patch/minor/major per package)
- Version detection from GitLab Package Registry
- Automatic git tagging and version commits
- Single atomic commit to prevent race conditions

See `docs/MANUAL_RELEASE.md` for detailed usage instructions.

## Future Packages

The monorepo structure is designed to accommodate additional packages:
- `ff-tools`: Utility functions and helpers
- `ff-auth`: Authentication and authorization
- `ff-api`: Common API utilities and middleware
- `ff-ml`: Machine learning utilities and model management
- `ff-cache`: Caching abstractions for Redis/Memcached