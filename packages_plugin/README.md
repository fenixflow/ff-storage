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

# Example commands (if using the template)
fenix ff-packages hello "Your Name"
fenix ff-packages status --verbose
fenix ff-packages config --list
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
        └── cli.py          # CLI commands
```

### Adding New Commands

Edit `src/packages_plugin/cli.py` and add new commands using the Typer decorator:

```python
@app.command()
def my_new_command(arg: str = typer.Argument(..., help="Command argument")):
    """Description of your new command."""
    console.print(f"Executing command with: {arg}")
```

### Testing

```bash
# Run the plugin directly
fenix ff-packages hello "Test"

# Check available commands
fenix ff-packages --help
```

## Author

Ben

## License

Proprietary

---
Created with Fenix CLI Plugin Creator on 2025-10-17
