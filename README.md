# Fenix Packages

[![Pipeline Status](https://gitlab.com/fenixflow/fenix-packages/badges/main/pipeline.svg)](https://gitlab.com/fenixflow/fenix-packages/-/pipelines)

Monorepo for all Fenixflow Python packages.

## Packages

### ff-storage
Database and file storage operations package. Provides PostgreSQL, MySQL connections with pooling support and file storage interfaces for local, S3, and Azure.

**Installation:**
```bash
# From GitLab Package Registry (recommended)
# See docs/PACKAGE_INSTALLATION.md for authentication setup
uv pip install ff-storage \
  --index-url https://<token_name>:<token>@gitlab.com/api/v4/projects/<project_id>/packages/pypi/simple

# From Git repository
uv pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-storage

# Local development
uv pip install -e ./ff-storage
```

### ff-logger
Structured logging package with scoped loggers. Provides ConsoleLogger, FileLogger, JSONLogger, and NullLogger implementations with instance-based architecture for better testing and flexibility.

**Key Features:**
- Instance-based loggers (not singletons)
- Scoped logging with context binding
- Zero-configuration NullLogger for testing
- Multiple output formats (console, file, JSON)
- Built on Python's standard logging

**Installation:**
```bash
# From GitLab Package Registry (recommended)
uv pip install ff-logger \
  --index-url https://<token_name>:<token>@gitlab.com/api/v4/projects/<project_id>/packages/pypi/simple

# From Git repository
uv pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-logger

# Local development
uv pip install -e ./ff-logger
```

### ff-cli
Unified CLI for the Fenix ecosystem with plugin architecture. Provides a single `fenix` command entry point with support for dynamically loaded plugins via Python entry points.

**Key Features:**
- Single entry point for all Fenix tools
- Plugin architecture for extensibility
- Dynamic command discovery
- Configuration management
- uvx compatible for easy execution

**Installation:**
```bash
# From GitLab Package Registry (recommended)
uv pip install ff-cli \
  --index-url https://<token_name>:<token>@gitlab.com/api/v4/projects/<project_id>/packages/pypi/simple

# From Git repository
uv pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-cli

# Local development
uv pip install -e ./ff-cli

# Run without installation using uvx
uvx --from git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-cli fenix --help
```

### ff-parsers
Document parsing utilities for various file formats. Provides parsers for PDF, DOCX, JSON, Markdown, and other common document formats.

**Key Features:**
- Multi-format document parsing
- Text extraction from PDFs and Office documents
- Structured data extraction
- Metadata extraction
- Streaming support for large files

**Installation:**
```bash
# From GitLab Package Registry (recommended)
uv pip install ff-parsers \
  --index-url https://<token_name>:<token>@gitlab.com/api/v4/projects/<project_id>/packages/pypi/simple

# From Git repository
uv pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-parsers

# Local development
uv pip install -e ./ff-parsers
```

## CI/CD Pipeline

This repository uses GitLab CI/CD for automated building, testing, and publishing of packages.

### Automatic Pipeline (Main Branch & MRs)

The main CI/CD pipeline (`.gitlab-ci.yml`) runs automatically on:
- Push to main branch
- Merge requests

**Pipeline Stages:**
1. **Build**: All packages are built in parallel
2. **Test**: All packages are tested in parallel
3. **Publish**: Packages are published to GitLab Package Registry (main branch only)

### Manual Release Pipeline

For controlled releases with version management, use the manual release pipeline (`.gitlab-ci-manual-release.yml`).

**Features:**
- Selective package releases via dropdown menus
- Semantic version bumping (patch/minor/major)
- Reads current versions from GitLab Package Registry
- Creates git tags for each release
- Single atomic commit prevents race conditions

**To trigger a manual release:**
1. Go to **CI/CD > Pipelines** in GitLab
2. Click **"Run pipeline"**
3. Select `.gitlab-ci-manual-release.yml`
4. Choose version bump type for each package:
   - `none`: Skip this package (default)
   - `patch`: Bug fixes (0.1.2 → 0.1.3)
   - `minor`: New features (0.1.2 → 0.2.0)
   - `major`: Breaking changes (0.1.2 → 1.0.0)
5. Click **"Run pipeline"**

See [docs/MANUAL_RELEASE.md](docs/MANUAL_RELEASE.md) for detailed instructions.

### Version Management

**Manual Version Updates:**
Developers are responsible for updating version numbers in `pyproject.toml` files:

```bash
# Edit the version in pyproject.toml
vim ff-storage/pyproject.toml

# Commit the change
git commit -m "chore: Bump ff-storage version to 0.2.0"
git push origin main
```

**Automatic Publishing:**
When changes are pushed to main, the pipeline automatically:
1. Builds all packages in parallel
2. Runs tests in parallel
3. Publishes new versions to GitLab Package Registry (if version doesn't exist)

### Local Development

**Building Packages:**
```bash
# Build a specific package
cd ff-storage && python -m build

# Build all packages (run from repository root)
for pkg in ff-storage ff-logger ff-cli ff-parsers; do
  (cd "$pkg" && python -m build)
done
```

**Testing:**
```bash
# Test a specific package
cd ff-storage && pytest tests/

# Test all packages (run from repository root)
for pkg in ff-storage ff-logger ff-cli ff-parsers; do
  (cd "$pkg" && pytest tests/)
done
```

**Package Management (using packages_plugin):**
```bash
# Install the packages plugin
uv pip install -e ./packages_plugin

# List all packages with versions
fenix ff-packages list

# Check publishing configuration
fenix ff-packages check

# Publish to PyPI (with interactive prompts)
fenix ff-packages pypi ff-storage

# Create GitHub release
fenix ff-packages github ff-storage

# Sync version to GitLab Package Registry
fenix ff-packages sync ff-storage
```

## Installation from GitLab Package Registry

### Setting up Authentication

Create a personal access token with `read_api` scope:
1. Go to GitLab > User Settings > Access Tokens
2. Create token with `read_api` scope
3. Save the token securely

### Installing Packages

```bash
# Set environment variables
export GITLAB_TOKEN="your-token-here"
export GITLAB_PROJECT_ID="73458224"  # fenix-packages project ID

# Install a package
uv pip install ff-storage \
  --index-url https://gitlab-ci-token:${GITLAB_TOKEN}@gitlab.com/api/v4/projects/${GITLAB_PROJECT_ID}/packages/pypi/simple

# Or add to requirements.txt
--index-url https://gitlab-ci-token:${GITLAB_TOKEN}@gitlab.com/api/v4/projects/73458224/packages/pypi/simple
ff-storage==0.1.3
ff-logger==0.1.2
ff-cli==0.1.2
ff-parsers==0.1.1
```

See [docs/PACKAGE_INSTALLATION.md](docs/PACKAGE_INSTALLATION.md) for more details.

## Development Setup

### Prerequisites

- Python 3.12+
- uv (recommended) or pip
- Git

### Clone and Setup

```bash
# Clone the repository
git clone https://gitlab.com/fenixflow/fenix-packages.git
cd fenix-packages

# Install all packages in development mode
uv pip install -e ./ff-storage
uv pip install -e ./ff-logger
uv pip install -e ./ff-cli
uv pip install -e ./ff-parsers

# Install development dependencies
uv pip install -e "./ff-storage[dev]"
uv pip install -e "./ff-logger[dev]"
uv pip install -e "./ff-cli[dev]"
uv pip install -e "./ff-parsers[dev]"
```

### Running Tests

```bash
# Test individual package
cd ff-storage && pytest tests/

# Test all packages (run from repository root)
for pkg in ff-storage ff-logger ff-cli ff-parsers; do
  (cd "$pkg" && pytest tests/)
done

# Run with coverage
cd ff-storage && pytest --cov=ff_storage tests/
```

### Code Quality

```bash
# Format code with black
black ff-storage/src/

# Lint with ruff
ruff check ff-storage/src/

# Pre-commit hooks (runs automatically on commit)
pre-commit run --all-files
```

## Contributing

1. Create a feature branch
2. Make your changes
3. Update tests as needed
4. Update version in `pyproject.toml` if needed
5. Create a merge request

## License

Proprietary - Fenixflow