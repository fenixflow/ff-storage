# packages_plugin

Plugin to manage the self publishing of the packages for fenix

## Overview

This is a Fenix CLI plugin that adds commands under the `fenix ff-packages` namespace.

## Installation

### For Development

1. Navigate to the plugin directory:
   ```bash
   cd packages_plugin
   ```

2. Install in editable mode:
   ```bash
   uv pip install -e .
   ```

3. Verify installation:
   ```bash
   fenix ff-packages --help
   ```

### From Source

```bash
fenix plugins install /path/to/packages_plugin
```

## Usage

After installation, the plugin commands are available under `fenix ff-packages`:

```bash
# Show help
fenix ff-packages --help

# List all packages with current versions and status
fenix ff-packages list

# Check publishing configuration (PyPI, GitHub authentication)
fenix ff-packages check

# Publish a package to PyPI
fenix ff-packages pypi <package-name>              # Production PyPI
fenix ff-packages pypi <package-name> --test       # TestPyPI
fenix ff-packages pypi <package-name> --dry-run    # Build and check only
fenix ff-packages pypi <package-name> --no-tag     # Skip git tag creation

# Create a GitHub release
fenix ff-packages github <package-name>
fenix ff-packages github <package-name> --draft    # Create as draft

# Sync package to GitLab Package Registry
fenix ff-packages sync <package-name>
```

### Examples

```bash
# Check if everything is configured correctly
fenix ff-packages check

# See all packages and their versions
fenix ff-packages list

# Publish ff-storage to PyPI (with confirmation prompts)
fenix ff-packages pypi ff-storage

# Test publishing to TestPyPI first
fenix ff-packages pypi ff-storage --test

# Create a GitHub release for ff-logger
fenix ff-packages github ff-logger

# Sync ff-cli to GitLab Package Registry
fenix ff-packages sync ff-cli
```

## Development

### Project Structure

```
packages_plugin/
├── pyproject.toml          # Package configuration
├── README.md               # This file
└── src/
    └── packages_plugin/
        ├── __init__.py     # Package marker
        ├── cli.py          # Main CLI app
        ├── commands/       # Command modules
        │   ├── list.py     # List packages command
        │   ├── check.py    # Check configuration command
        │   ├── pypi.py     # PyPI publishing command
        │   ├── github.py   # GitHub release command
        │   └── sync.py     # GitLab sync command
        └── utils/          # Utility modules
            ├── build.py    # Package building utilities
            ├── check.py    # Configuration checking
            ├── github.py   # GitHub API utilities
            ├── pypi.py     # PyPI utilities
            └── constants.py # Shared constants
```

### Adding New Commands

To add a new command:

1. Create a new file in `src/packages_plugin/commands/` with your command function
2. Import and register it in `src/packages_plugin/cli.py`

Example command structure:

```python
# src/packages_plugin/commands/my_command.py
import typer
from rich.console import Console

console = Console()

def my_command(
    package: str = typer.Argument(..., help="Package name"),
    option: bool = typer.Option(False, "--flag", help="Optional flag"),
):
    """Description of your new command."""
    console.print(f"Executing command with: {package}")
```

### Testing

```bash
# Check available commands
fenix ff-packages --help

# Test listing packages
fenix ff-packages list

# Test configuration check
fenix ff-packages check

# Test build with dry-run (doesn't publish)
fenix ff-packages pypi ff-storage --dry-run
```

## Author

Ben

## License

Proprietary

---
Created with Fenix CLI Plugin Creator on 2025-10-17
