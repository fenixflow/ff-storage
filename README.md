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
pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-logger

# Local development
pip install -e ./ff-logger
```

## CI/CD Pipeline

This repository uses GitLab CI/CD for automated building and publishing of packages.

### How It Works

1. **Change Detection**: The pipeline detects which packages have changed
2. **Automatic Version Bumping**: Versions are automatically bumped based on commit messages
3. **Selective Building**: Only changed packages are built and tested
4. **Automatic Publishing**: New versions are published to GitLab Package Registry

### Version Management

The pipeline automatically manages package versions using semantic versioning (MAJOR.MINOR.PATCH).

#### Automatic Version Bumping

Versions are automatically bumped based on commit message tags:

- **No tag or `[patch]`**: Bumps patch version (0.1.0 → 0.1.1) - Default for bug fixes
  ```bash
  git commit -m "Fix NullLogger initialization issue"
  git commit -m "[patch] Fix database connection timeout"
  ```

- **`[minor]`**: Bumps minor version (0.1.1 → 0.2.0) - For new features
  ```bash
  git commit -m "[minor] Add new DatabaseLogger class"
  ```

- **`[major]`**: Bumps major version (0.1.0 → 1.0.0) - For breaking changes
  ```bash
  git commit -m "[major] Refactor API with breaking changes"
  ```

- **`[skip-version]`**: No version change - For documentation, CI/CD changes
  ```bash
  git commit -m "[skip-version] Update README documentation"
  ```

#### Manual Version Control

You can also manually set versions:

1. Edit `<package>/pyproject.toml` directly
2. Update the `version = "X.Y.Z"` line
3. Commit with `[skip-version]` to avoid double-bumping:
   ```bash
   git commit -m "[skip-version] Manually set version to 2.0.0"
   ```

#### How Version Syncing Works

1. When changes are pushed to `main`, the pipeline:
   - Detects changed packages
   - Analyzes commit messages for version bump tags
   - Updates `pyproject.toml` with new versions
   - Commits the version changes back to `main` with `[skip-ci]` tag
   - Publishes packages to the registry

2. The `[skip-ci]` tag prevents infinite loops by telling the pipeline not to run again

#### Local Version Bumping

You can test version bumping locally:

```bash
# Check what would be bumped (dry run)
./scripts/bump_version.sh

# For testing in CI-like environment
echo '["ff-logger"]' > changed_packages.json
./scripts/bump_version.sh
```

### Triggering a Release

Simply push your changes to main with an appropriate commit message:

```bash
# For a bug fix (patch bump)
git commit -m "Fix critical bug in logger"
git push origin main

# For a new feature (minor bump)
git commit -m "[minor] Add async support to logger"
git push origin main

# For breaking changes (major bump)
git commit -m "[major] Redesign logger API"
git push origin main
```

The pipeline will automatically:
1. Detect the changed packages
2. Bump versions based on commit messages
3. Build and test the packages
4. Publish to GitLab Package Registry
5. Commit version changes back to main

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