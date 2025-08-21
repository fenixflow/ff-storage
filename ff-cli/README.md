# ff-cli

Fenix-wide CLI with plugin architecture for project-specific commands. This provides a unified command-line interface for the entire Fenix ecosystem, allowing individual projects to extend functionality through plugins.

## Features

- **Unified Entry Point**: Single `fenix` command for all Fenix tools
- **Plugin Architecture**: Projects can add their own namespaced commands
- **uvx Compatible**: Can be installed and run with `uvx fenix`
- **Auto-completion**: Shell completion support for all commands
- **Configuration Management**: Centralized config in `~/.fenix/config.toml`
- **Dynamic Discovery**: Automatically discovers installed plugins

## Installation

### Using uv (Recommended)

```bash
# Install from GitLab
uv pip install git+https://gitlab.com/fenixflow/fenix-packages.git#subdirectory=ff-cli

# Or install locally for development
cd ff-cli
uv pip install -e .
```

### Using uvx

Run without installation:

```bash
uvx --from git+https://gitlab.com/fenixflow/fenix-packages.git#subdirectory=ff-cli fenix --help
```

### Shell Completion

Enable auto-completion for your shell:

```bash
# Bash
fenix --install-completion bash

# Zsh
fenix --install-completion zsh

# Fish
fenix --install-completion fish
```

## Usage

### Basic Commands

```bash
# Show help
fenix --help

# Show version
fenix --version

# List installed plugins
fenix plugins list

# Get info about a plugin
fenix plugins info ff-agents
```

### Plugin Management

```bash
# Install a plugin from GitLab
fenix plugins install git+https://gitlab.com/fenixflow/fenix-agents.git

# Install from local directory
fenix plugins install ./path/to/plugin

# Install from package registry
fenix plugins install fenix-plugin-name

# Update a plugin
fenix plugins update ff-agents

# Remove a plugin
fenix plugins remove ff-agents
```

### Using Plugin Commands

Once a plugin is installed, its commands are available under its namespace:

```bash
# Show plugin help
fenix ff-agents --help

# Run plugin commands
fenix ff-agents status
fenix ff-agents run workflow-name
fenix ff-agents setup

# Another plugin example
fenix ff-storage --help
fenix ff-storage migrate
fenix ff-storage backup
```

## Creating Plugins

Plugins are Python packages that provide a Typer app via entry points.

### Plugin Structure

```
my-fenix-plugin/
├── pyproject.toml
├── README.md
└── src/
    └── my_plugin/
        ├── __init__.py
        └── cli.py
```

### Example Plugin Code

```python
# cli.py
import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="My Fenix plugin")

@app.command()
def status():
    """Show plugin status."""
    console.print("Plugin is working!")

@app.command()
def run(task: str):
    """Run a task."""
    console.print(f"Running task: {task}")

def plugin():
    """Entry point that returns the Typer app."""
    return app
```

### Plugin Registration

In `pyproject.toml`:

```toml
[project]
name = "my-fenix-plugin"
version = "0.1.0"
dependencies = [
    "typer>=0.16.0",
    "rich>=13.0.0",
]

[project.entry-points."fenix.plugins"]
ff-myplugin = "my_plugin.cli:plugin"
```

### Installing Your Plugin

```bash
# Install from local directory
fenix plugins install ./my-fenix-plugin

# Or install directly with pip/uv
uv pip install ./my-fenix-plugin

# The plugin is now available
fenix ff-myplugin --help
```

## Configuration

Configuration is stored in `~/.fenix/config.toml`:

```toml
[plugins]
ff-agents = { version = "0.1.0", source = "git+https://...", installed_at = "2025-01-01T00:00:00" }
ff-storage = { version = "0.2.0", source = "pypi", installed_at = "2025-01-02T00:00:00" }

[settings]
default_environment = "development"
gitlab_token = "..."
```

## For AI Agents

This CLI is designed to be used by both humans and AI agents. The consistent command structure makes it easy for agents to:

1. Discover available tools: `fenix plugins list`
2. Install required plugins: `fenix plugins install <source>`
3. Set up environments: `fenix ff-agents setup`
4. Run workflows: `fenix ff-agents run <workflow>`

## Development

### Running Tests

```bash
cd ff-cli
pytest tests/
```

### Code Quality

```bash
# Format code
black src/

# Lint
ruff check src/

# Type check
mypy src/
```

## Example Workflow

```bash
# 1. Install the CLI
uv pip install git+https://gitlab.com/fenixflow/fenix-packages.git#subdirectory=ff-cli

# 2. Install project plugins
fenix plugins install git+https://gitlab.com/fenixflow/fenix-agents.git
fenix plugins install git+https://gitlab.com/fenixflow/fenix-storage.git

# 3. Use the plugins
fenix ff-agents setup
fenix ff-agents status
fenix ff-storage init
fenix ff-storage migrate

# 4. List everything available
fenix plugins list
fenix --help
```

## License

Proprietary - Fenixflow