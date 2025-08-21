#!/usr/bin/env python3
"""
Main entry point for the Fenix CLI.
"""

import sys

import typer
from rich.console import Console

from ff_cli import __version__
from ff_cli.commands import plugins as plugins_cmd
from ff_cli.plugin_manager import PluginManager

# Initialize console for rich output
console = Console()

# Create the main Typer app
app = typer.Typer(
    name="fenix",
    help="Fenix-wide CLI with plugin architecture for project-specific commands",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
)


def version_callback(value: bool):
    """Show version and exit."""
    if value:
        console.print(f"[bold cyan]Fenix CLI[/bold cyan] version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
):
    """
    Fenix CLI - Unified command-line interface for the Fenix ecosystem.

    This CLI provides a central entry point for all Fenix tools and project-specific
    commands through a plugin architecture. Each project can install its own plugin
    to add namespaced commands.

    Examples:
        fenix --help                    # Show this help
        fenix plugins list              # List installed plugins
        fenix ff-agents --help          # Show help for a plugin
        fenix ff-agents status          # Run a plugin command
    """
    pass


# Add the plugins command group
app.add_typer(plugins_cmd.app, name="plugins", help="Manage Fenix CLI plugins")


def load_plugins():
    """Load and register all installed plugins."""
    try:
        manager = PluginManager()
        manager.register_plugin_commands(app)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load plugins: {e}[/yellow]")


def run():
    """Main entry point for the CLI."""
    # Load plugins before running the app
    load_plugins()

    # Enable shell completion
    # Typer handles completion internally when --install-completion is used
    # Shell completion is automatically available via:
    #   fenix --install-completion  # Install completion for current shell
    #   fenix --show-completion     # Show completion script

    # Run the app
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    run()
