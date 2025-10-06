#!/usr/bin/env python3
"""Main entry point for the branded CLI."""

import sys

import typer

from ff_cli import __version__
from ff_cli.branding import get_brand
from ff_cli.commands import branding as branding_cmd
from ff_cli.commands import doctor as doctor_cmd
from ff_cli.commands import plugins as plugins_cmd
from ff_cli.commands import scripts as scripts_cmd
from ff_cli.commands import services as services_cmd
from ff_cli.commands import status as status_cmd
from ff_cli.plugin_manager import PluginManager
from ff_cli.utils.common import console

# Get brand configuration
brand = get_brand()

# Create the main Typer app with branding
app = typer.Typer(
    name=brand.cli_name,
    help=f"{brand.icon} {brand.cli_description}",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def version_callback(value: bool):
    """Show version and exit."""
    if value:
        brand = get_brand()
        console.print(
            f"[bold cyan]{brand.icon} {brand.cli_display_name}[/bold cyan] version {__version__}"
        )
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
    Main CLI callback - handles global options.

    The actual help text is dynamically generated based on branding.
    """
    pass


# Add command groups
app.add_typer(
    plugins_cmd.app,
    name="plugins",
    help=f"{brand.icon} Manage {brand.cli_display_name} plugins",
)
app.add_typer(
    services_cmd.app,
    name="services",
    help=f"{brand.icon} Manage Docker services",
)
app.add_typer(
    scripts_cmd.app,
    name="scripts",
    help=f"{brand.icon} Manage plugin scripts",
)
app.add_typer(
    branding_cmd.app,
    name="branding",
    help=f"{brand.icon} Configure CLI branding",
)

# Add top-level status command
app.command(name="status")(status_cmd.status)

# Add top-level doctor command
app.command(name="doctor")(doctor_cmd.doctor)


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
