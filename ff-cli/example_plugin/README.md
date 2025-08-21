# Fenix Example Plugin

This is an example plugin demonstrating how to create plugins for the Fenix CLI.

## Structure

A Fenix CLI plugin is a standard Python package that:
1. Provides a Typer app with commands
2. Registers itself via entry points in pyproject.toml
3. Gets loaded automatically when installed

## Key Files

- `pyproject.toml`: Defines the entry point for the plugin
- `cli.py`: Contains the Typer app and commands
- `plugin()` function: Returns the Typer app to Fenix CLI

## Creating Your Own Plugin

1. Copy this example structure
2. Rename the package and update pyproject.toml
3. Add your commands to the Typer app
4. Register the entry point:
   ```toml
   [project.entry-points."fenix.plugins"]
   your-plugin-name = "your_package.cli:plugin"
   ```

## Installation

Install directly from source:
```bash
fenix plugins install ./path/to/plugin
```

Or from git:
```bash
fenix plugins install git+https://gitlab.com/your/plugin.git
```

## Usage

Once installed, your commands are available under the plugin namespace:
```bash
fenix your-plugin-name --help
fenix your-plugin-name your-command
```