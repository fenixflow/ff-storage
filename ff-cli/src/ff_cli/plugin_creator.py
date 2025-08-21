"""
Plugin creation utilities for Fenix CLI.

This module provides templates and utilities for creating new Fenix CLI plugins.
"""

import re
from datetime import datetime
from pathlib import Path

from rich.console import Console

console = Console()


def sanitize_plugin_name(name: str) -> str:
    """
    Sanitize a plugin name for use in package names and module names.

    Args:
        name: The raw plugin name from user input

    Returns:
        A sanitized name suitable for Python packages
    """
    # Convert to lowercase and replace spaces/hyphens with underscores
    name = name.lower().replace(" ", "_").replace("-", "_")
    # Remove any characters that aren't alphanumeric or underscore
    name = re.sub(r"[^a-z0-9_]", "", name)
    # Ensure it doesn't start with a number
    if name and name[0].isdigit():
        name = f"plugin_{name}"
    return name or "my_plugin"


def get_pyproject_template(
    plugin_name: str,
    display_name: str,
    description: str,
    author_name: str = "Your Name",
    author_email: str = "you@example.com",
) -> str:
    """Generate pyproject.toml content for a new plugin."""
    module_name = sanitize_plugin_name(plugin_name)

    return f"""[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{plugin_name}"
version = "0.1.0"
description = "{description}"
readme = "README.md"
requires-python = ">=3.12"
license = {{text = "Proprietary"}}
authors = [
    {{name = "{author_name}", email = "{author_email}"}}
]
dependencies = [
    "typer>=0.16.0",
    "rich>=13.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
    "black>=23.0",
    "ruff>=0.1",
]

# Register the plugin with Fenix CLI
[project.entry-points."fenix.plugins"]
{display_name} = "{module_name}.cli:plugin"

[tool.hatch.build.targets.wheel]
packages = ["src/{module_name}"]
"""


def get_cli_module_template(
    plugin_name: str,
    display_name: str,
    description: str,
    include_examples: bool = True,
) -> str:
    """Generate cli.py content for a new plugin."""

    if include_examples:
        return f'''"""
{description}

This plugin adds commands to the Fenix CLI under the '{display_name}' namespace.
"""

import typer
from rich.console import Console
from rich.table import Table

console = Console()

# Create the Typer app for this plugin
app = typer.Typer(
    help="{description}",
    no_args_is_help=True,
)


@app.command()
def hello(
    name: str = typer.Argument("World", help="Name to greet"),
    formal: bool = typer.Option(False, "--formal", "-f", help="Use formal greeting"),
):
    """Say hello to someone."""
    if formal:
        console.print(f"[bold blue]Greetings, {{name}}![/bold blue]")
    else:
        console.print(f"[bold green]Hello, {{name}}![/bold green]")
    console.print(f"This is the [cyan]{display_name}[/cyan] plugin speaking!")


@app.command()
def status(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed status"),
):
    """Show plugin status and information."""
    console.print(f"[bold cyan]{display_name.upper()} Plugin Status[/bold cyan]")
    console.print("✅ Plugin is loaded and working")
    console.print("📦 Version: 0.1.0")

    if verbose:
        table = Table(title="Plugin Details")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Name", "{plugin_name}")
        table.add_row("Display Name", "{display_name}")
        table.add_row("Description", "{description}")
        table.add_row("Commands", "hello, status, config")

        console.print(table)


@app.command()
def config(
    list_all: bool = typer.Option(False, "--list", "-l", help="List all configuration"),
    get: str = typer.Option(None, "--get", help="Get a configuration value"),
    set_key: str = typer.Option(None, "--set", help="Set a configuration key"),
    value: str = typer.Option(None, "--value", help="Configuration value to set"),
):
    """Manage plugin configuration."""
    if list_all:
        console.print("[cyan]Current Configuration:[/cyan]")
        # In a real plugin, this would read from actual config
        console.print("  example_key: example_value")
        console.print("  another_key: another_value")
    elif get:
        console.print(f"[cyan]Getting config value for: {{get}}[/cyan]")
        # In a real plugin, this would read from actual config
        console.print(f"Value: example_value")
    elif set_key and value:
        console.print(f"[cyan]Setting {{set_key}} = {{value}}[/cyan]")
        # In a real plugin, this would save to actual config
        console.print("[green]Configuration updated successfully![/green]")
    else:
        console.print("[yellow]Usage:[/yellow]")
        console.print("  --list: Show all configuration")
        console.print("  --get KEY: Get a specific value")
        console.print("  --set KEY --value VALUE: Set a configuration value")


def plugin():
    """Entry point for the plugin.

    This function is called by Fenix CLI to get the Typer app for this plugin.
    It's registered in pyproject.toml under [project.entry-points."fenix.plugins"].

    Returns:
        typer.Typer: The Typer app with all plugin commands
    """
    return app
'''
    else:
        return f'''"""
{description}

This plugin adds commands to the Fenix CLI under the '{display_name}' namespace.
"""

import typer
from rich.console import Console

console = Console()

# Create the Typer app for this plugin
app = typer.Typer(
    help="{description}",
    no_args_is_help=True,
)


@app.command()
def hello(name: str = typer.Argument("World", help="Name to greet")):
    """A simple hello command."""
    console.print(f"[bold green]Hello, {{name}}![/bold green]")
    console.print(f"Welcome to the [cyan]{display_name}[/cyan] plugin!")


# Add your custom commands here
# @app.command()
# def my_command():
#     """Description of your command."""
#     console.print("Your command logic here")


def plugin():
    """Entry point for the plugin.

    This function is called by Fenix CLI to get the Typer app for this plugin.
    It's registered in pyproject.toml under [project.entry-points."fenix.plugins"].

    Returns:
        typer.Typer: The Typer app with all plugin commands
    """
    return app
'''


def get_readme_template(
    plugin_name: str,
    display_name: str,
    description: str,
    author_name: str = "Your Name",
) -> str:
    """Generate README.md content for a new plugin."""
    return f'''# {plugin_name}

{description}

## Overview

This is a Fenix CLI plugin that adds commands under the `fenix {display_name}` namespace.

## Installation

### For Development

1. Navigate to the plugin directory:
   ```bash
   cd {plugin_name}
   ```

2. Install in editable mode:
   ```bash
   uv pip install -e .
   ```

3. Verify installation:
   ```bash
   fenix {display_name} --help
   ```

### From Source

```bash
fenix plugins install /path/to/{plugin_name}
```

## Usage

After installation, the plugin commands are available under `fenix {display_name}`:

```bash
# Show help
fenix {display_name} --help

# Example commands (if using the template)
fenix {display_name} hello "Your Name"
fenix {display_name} status --verbose
fenix {display_name} config --list
```

## Development

### Project Structure

```
{plugin_name}/
├── pyproject.toml          # Package configuration
├── README.md               # This file
└── src/
    └── {sanitize_plugin_name(plugin_name)}/
        ├── __init__.py     # Package marker
        └── cli.py          # CLI commands
```

### Adding New Commands

Edit `src/{sanitize_plugin_name(plugin_name)}/cli.py` and add new commands using the Typer decorator:

```python
@app.command()
def my_new_command(arg: str = typer.Argument(..., help="Command argument")):
    """Description of your new command."""
    console.print(f"Executing command with: {{arg}}")
```

### Testing

```bash
# Run the plugin directly
fenix {display_name} hello "Test"

# Check available commands
fenix {display_name} --help
```

## Author

{author_name}

## License

Proprietary

---
Created with Fenix CLI Plugin Creator on {datetime.now().strftime("%Y-%m-%d")}
'''


def get_init_template() -> str:
    """Generate __init__.py content for a new plugin."""
    return '''"""
Plugin package initialization.
"""

__version__ = "0.1.0"
'''


def create_plugin_structure(
    base_path: Path,
    plugin_name: str,
    display_name: str,
    description: str,
    author_name: str,
    author_email: str,
    include_examples: bool = True,
) -> Path:
    """
    Create the complete plugin directory structure with all necessary files.

    Args:
        base_path: Directory where the plugin folder will be created
        plugin_name: Package name for the plugin
        display_name: Display name for CLI commands (e.g., ff-myplugin)
        description: Plugin description
        author_name: Author's name
        author_email: Author's email
        include_examples: Whether to include example commands

    Returns:
        Path to the created plugin directory
    """
    # Create the main plugin directory
    plugin_dir = base_path / plugin_name
    if plugin_dir.exists():
        raise FileExistsError(f"Directory already exists: {plugin_dir}")

    plugin_dir.mkdir(parents=True)

    # Create source directory structure
    module_name = sanitize_plugin_name(plugin_name)
    src_dir = plugin_dir / "src" / module_name
    src_dir.mkdir(parents=True)

    # Write pyproject.toml
    pyproject_content = get_pyproject_template(
        plugin_name=plugin_name,
        display_name=display_name,
        description=description,
        author_name=author_name,
        author_email=author_email,
    )
    (plugin_dir / "pyproject.toml").write_text(pyproject_content)

    # Write README.md
    readme_content = get_readme_template(
        plugin_name=plugin_name,
        display_name=display_name,
        description=description,
        author_name=author_name,
    )
    (plugin_dir / "README.md").write_text(readme_content)

    # Write __init__.py
    init_content = get_init_template()
    (src_dir / "__init__.py").write_text(init_content)

    # Write cli.py
    cli_content = get_cli_module_template(
        plugin_name=plugin_name,
        display_name=display_name,
        description=description,
        include_examples=include_examples,
    )
    (src_dir / "cli.py").write_text(cli_content)

    return plugin_dir


def copy_plugin_for_installation(plugin_dir: Path, plugin_name: str) -> None:
    """
    Copy the plugin to the Fenix CLI's installed_plugins directory.

    This is similar to what the install command does but for newly created plugins.
    """
    from ff_cli import plugin_registry

    module_name = sanitize_plugin_name(plugin_name)
    src_module_path = plugin_dir / "src" / module_name

    if not src_module_path.exists():
        raise FileNotFoundError(f"Plugin module not found at {src_module_path}")

    # Copy to installed plugins directory
    plugin_registry.copy_plugin_files(plugin_dir, module_name, plugin_name)
