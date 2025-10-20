"""
Plugin to manage the self publishing of the packages for fenix

This plugin adds commands to the Fenix CLI under the 'ff-packages' namespace.
"""

import typer

from .commands import github, list_cmd, pypi, setup, sync

# Create the Typer app for this plugin
app = typer.Typer(
    help="Manage package publishing to GitHub and PyPI",
    no_args_is_help=True,
)

# Register commands
app.command(name="list")(list_cmd.list_packages)
app.command(name="check")(setup.check_auth)
app.command(name="github")(github.mirror_to_github)
app.command(name="pypi")(pypi.publish_package)
app.command(name="sync")(sync.sync_package)


def plugin():
    """Entry point for the plugin.

    This function is called by Fenix CLI to get the Typer app for this plugin.
    It's registered in pyproject.toml under [project.entry-points."fenix.plugins"].

    Returns:
        typer.Typer: The Typer app with all plugin commands
    """
    return app
