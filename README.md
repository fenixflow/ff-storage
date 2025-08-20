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
pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-storage

# Local development
pip install -e ./ff-storage
```

## CI/CD Pipeline

This repository uses GitLab CI/CD for automated building and publishing of packages.

### How It Works

1. **Change Detection**: The pipeline detects which packages have changed
2. **Version Check**: Only publishes if the version in `pyproject.toml` is new
3. **Selective Building**: Only changed packages are built and tested
4. **Automatic Publishing**: New versions are published to GitLab Package Registry

### Triggering a Release

1. Make your changes to a package
2. Update the version in `<package>/pyproject.toml`
3. Commit and push to main
4. The pipeline will automatically build and publish the new version

### Manual Operations

```bash
# Build all packages locally
./scripts/build_all.sh

# Build a specific package
./scripts/build_package.sh ff-storage

# Test a package
./scripts/test_package.sh ff-storage
```

## Development

### Setting Up Local Environment

```bash
# Clone the repository
git clone git@gitlab.com:fenixflow/fenix-packages.git
cd fenix-packages

# Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Set up a package for development
cd ff-storage
uv sync --extra dev
```

### Testing
```bash
# Test a specific package
cd ff-storage && uv run pytest tests/

# Run linting
cd ff-storage && uv run ruff check src/
cd ff-storage && uv run black --check src/
```

### Publishing (Automated)
Packages are automatically published to GitLab Package Registry when:
1. Changes are pushed to main
2. The package version in `pyproject.toml` has been updated
3. Tests pass successfully

## Structure
```
fenix-packages/
├── ff-storage/         # Database & file storage
├── ff-tools/          # Future: utility packages
├── ff-auth/           # Future: authentication
└── scripts/           # Build and deployment scripts
```

## Contributing
1. Create feature branch
2. Make changes
3. Add tests
4. Submit merge request

## License
Proprietary - Fenixflow Internal Use Only