# Contributing to Fenix-Packages

Thank you for your interest in contributing to Fenix-Packages! This document provides guidelines and setup instructions for developers.

## Development Setup

### Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer

### Initial Setup

1. **Clone the repository**:
   ```bash
   git clone https://gitlab.com/fenixflow/fenix-packages.git
   cd fenix-packages
   ```

2. **Install all packages in editable mode**:
   ```bash
   uv pip install -e ff-storage -e ff-logger -e ff-cli -e ff-parsers
   ```

   This installs all packages in development mode, allowing you to make changes and immediately see the effects in tests.

3. **Install pre-commit hooks** (recommended):
   ```bash
   uv pip install pre-commit
   pre-commit install
   ```

### Package Structure

The repository is organized as a monorepo with four independent packages:

```
fenix-packages/
├── ff-storage/     # Database and object storage (v3.5.0)
├── ff-logger/      # Logging utilities (v0.4.3)
├── ff-cli/         # CLI tools (v0.4.1)
└── ff-parsers/     # Document parsers (v1.2.1)
```

Each package:
- Has its own `pyproject.toml`, tests, and documentation
- Can be installed independently
- Can be versioned independently
- Has its own CHANGELOG (ff-storage and ff-logger only)

## Running Tests

### All Packages

Run the complete test suite (480 tests):
```bash
pytest
```

### Individual Packages

Run tests for a specific package:
```bash
pytest ff-storage/tests/   # 334 tests
pytest ff-logger/tests/    # 97 tests
pytest ff-cli/tests/       # 25 tests
pytest ff-parsers/tests/   # 34 tests
```

### Test Options

```bash
# Fast-fail (stop on first failure)
pytest -x

# Verbose output
pytest -v

# Run specific test
pytest ff-storage/tests/unit/test_postgres.py::test_connection

# Skip slow tests
pytest -m "not slow"

# Run only integration tests
pytest -m integration
```

## Code Quality

### Linting and Formatting

We use `ruff` for both linting and formatting:

```bash
# Check for issues
uvx ruff check .

# Auto-fix issues
uvx ruff check --fix .

# Format code
uvx ruff format .
```

### Pre-commit Hooks

Pre-commit hooks automatically run on every commit:
- Trailing whitespace removal
- End-of-file fixes
- YAML/TOML validation
- Ruff linting and formatting
- Full pytest suite

To run hooks manually:
```bash
pre-commit run --all-files
```

## Making Changes

### Workflow

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/my-feature
   # or
   git checkout -b fix/my-bugfix
   ```

2. **Make your changes**:
   - Edit code in `src/` directories
   - Add/update tests
   - Update CHANGELOG.md (ff-storage and ff-logger only)

3. **Run tests**:
   ```bash
   pytest
   ```

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat: Add new feature"
   ```

   We follow [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` New feature
   - `fix:` Bug fix
   - `docs:` Documentation changes
   - `style:` Code style changes (formatting)
   - `refactor:` Code refactoring
   - `test:` Test changes
   - `chore:` Build/tooling changes

5. **Push and create merge request**:
   ```bash
   git push -u origin feature/my-feature
   ```

### Version Bumping

Each package has independent versioning in its `pyproject.toml`:

- **Patch** (x.x.X): Bug fixes, no API changes
- **Minor** (x.X.x): New features, backward compatible
- **Major** (X.x.x): Breaking changes

Update the version in `pyproject.toml` and add an entry to `CHANGELOG.md` (for ff-storage and ff-logger).

## Package-Specific Guidelines

### ff-storage

- Always add integration tests for database operations
- Update schema sync tests when modifying type mappings
- Document breaking changes in CHANGELOG with migration guide

### ff-logger

- Zero dependencies policy - only use Python stdlib
- All loggers must be instance-based (no global state)
- Add tests for new log formats

### ff-cli

- Commands should be Typer-based
- Follow the plugin architecture for extensibility
- Test with real Docker services when possible

### ff-parsers

- Support streaming for large files
- Add tests with actual document samples
- Document supported formats

## Troubleshooting

### Tests Importing Wrong Package Version

If tests fail with "method not found" errors:

```bash
# Reinstall packages in editable mode
uv pip install -e ff-storage -e ff-logger -e ff-cli -e ff-parsers
```

### Pre-commit Hook Failures

If pre-commit hooks modify files:

```bash
# Stage the changes and commit again
git add .
git commit -m "your message"
```

## Questions or Issues?

- Check existing [issues](https://gitlab.com/fenixflow/fenix-packages/-/issues)
- Review [CLAUDE.md](./CLAUDE.md) for AI-specific guidelines
- Contact: dev@fenixflow.com

## License

All packages are licensed under MIT License.
