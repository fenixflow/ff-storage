"""
Plugin management commands for Fenix CLI.
"""

import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Confirm

from ff_cli.config import ConfigManager
from ff_cli.plugin_manager import PluginManager

console = Console()
app = typer.Typer(help="Manage Fenix CLI plugins")


@app.command("list")
def list_plugins():
    """List all installed plugins."""
    manager = PluginManager()
    manager.print_plugin_list()

    # Also show plugins tracked in config that might not be installed
    config_manager = ConfigManager()
    config_plugins = config_manager.list_plugins()

    if config_plugins:
        missing_plugins = []
        for name, plugin_config in config_plugins.items():
            if name not in manager.plugins:
                missing_plugins.append((name, plugin_config))

        if missing_plugins:
            console.print("\n[yellow]Plugins in config but not installed:[/yellow]")
            for name, config in missing_plugins:
                console.print(
                    f"  {name} ({config.version}) - run 'fenix plugins install {config.source}' to reinstall"
                )


@app.command("info")
def plugin_info(name: str = typer.Argument(..., help="Plugin name")):
    """Show detailed information about a plugin."""
    manager = PluginManager()
    manager.print_plugin_info(name)

    # Also show config info if available
    config_manager = ConfigManager()
    plugin_config = config_manager.get_plugin_config(name)
    if plugin_config:
        console.print("\n[bold]Configuration:[/bold]")
        console.print(f"  Source: {plugin_config.source}")
        console.print(f"  Installed: {plugin_config.installed_at}")


@app.command("install")
def install_plugin(
    source: str = typer.Argument(..., help="Plugin source (git URL, package name, or local path)"),
    upgrade: bool = typer.Option(False, "--upgrade", "-U", help="Upgrade if already installed"),
    editable: bool = typer.Option(False, "--editable", "-e", help="Install in editable mode"),
):
    """Install a Fenix CLI plugin.

    Examples:
        fenix plugins install git+https://gitlab.com/fenixflow/fenix-agents.git
        fenix plugins install ff-agents-cli
        fenix plugins install ./local-plugin
    """
    console.print(f"[cyan]Installing plugin from: {source}[/cyan]")

    # Determine if we're using uv or pip
    use_uv = subprocess.run(["which", "uv"], capture_output=True).returncode == 0

    if use_uv:
        cmd = ["uv", "pip", "install"]
    else:
        cmd = [sys.executable, "-m", "pip", "install"]

    if upgrade:
        cmd.append("--upgrade")

    if editable:
        cmd.append("-e")

    cmd.append(source)

    try:
        # Run the installation command
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            console.print("[red]Installation failed:[/red]")
            console.print(result.stderr)
            raise typer.Exit(1)

        console.print("[green]Plugin installed successfully![/green]")

        # Try to detect the installed plugin name and version
        # This is a bit tricky as we need to re-discover plugins
        # manager = PluginManager()  # Not used currently

        # Find the newly installed plugin
        # For now, we'll just save the source in config
        # In a real implementation, we'd parse the package name from the source
        plugin_name = _extract_plugin_name(source)
        if plugin_name:
            config_manager = ConfigManager()
            config_manager.add_plugin(
                name=plugin_name,
                version="latest",  # Would need to detect actual version
                source=source,
            )
            console.print(f"[green]Plugin '{plugin_name}' registered in config[/green]")

        console.print(
            "\n[yellow]Note: You may need to restart the CLI for the plugin to be available[/yellow]"
        )

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Installation failed: {e}[/red]")
        raise typer.Exit(1) from e
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("remove")
def remove_plugin(
    name: str = typer.Argument(..., help="Plugin name to remove"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Remove a Fenix CLI plugin."""

    # Check if plugin exists
    manager = PluginManager()
    plugin = manager.get_plugin(name)

    if not plugin and not yes:
        config_manager = ConfigManager()
        if name not in config_manager.list_plugins():
            console.print(f"[red]Plugin '{name}' not found[/red]")
            raise typer.Exit(1)

    if not yes:
        if not Confirm.ask(f"Remove plugin '{name}'?"):
            console.print("[yellow]Cancelled[/yellow]")
            raise typer.Exit(0)

    # Get the package name to uninstall
    # This might be different from the plugin name
    config_manager = ConfigManager()
    plugin_config = config_manager.get_plugin_config(name)

    if plugin_config:
        # Try to determine package name from source
        package_name = _extract_package_name(plugin_config.source)
    else:
        # Fallback to plugin name
        package_name = name

    console.print(f"[cyan]Removing plugin: {name}[/cyan]")

    # Determine if we're using uv or pip
    use_uv = subprocess.run(["which", "uv"], capture_output=True).returncode == 0

    if use_uv:
        cmd = ["uv", "pip", "uninstall", package_name, "-y"]
    else:
        cmd = [sys.executable, "-m", "pip", "uninstall", package_name, "-y"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            console.print(f"[yellow]Warning: Could not uninstall package: {result.stderr}[/yellow]")

        # Remove from config regardless
        if config_manager.remove_plugin(name):
            console.print(f"[green]Plugin '{name}' removed from configuration[/green]")

        console.print("[green]Plugin removed successfully![/green]")

    except Exception as e:
        console.print(f"[red]Error removing plugin: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("update")
def update_plugin(
    name: str = typer.Argument(..., help="Plugin name to update"),
):
    """Update a Fenix CLI plugin to the latest version."""

    config_manager = ConfigManager()
    plugin_config = config_manager.get_plugin_config(name)

    if not plugin_config:
        console.print(f"[red]Plugin '{name}' not found in configuration[/red]")
        console.print("[yellow]Try 'fenix plugins list' to see available plugins[/yellow]")
        raise typer.Exit(1)

    console.print(f"[cyan]Updating plugin '{name}' from: {plugin_config.source}[/cyan]")

    # Use install with upgrade flag
    install_plugin(source=plugin_config.source, upgrade=True, editable=False)


def _extract_plugin_name(source: str) -> str | None:
    """Try to extract plugin name from source.

    This is a simplified version - in production would need better parsing.
    """
    if source.startswith("git+"):
        # Extract from git URL
        parts = source.split("/")
        if parts:
            repo_name = parts[-1].replace(".git", "")
            # Convention: fenix plugins start with ff-
            if repo_name.startswith("ff-") or repo_name.startswith("fenix-"):
                return repo_name.replace("fenix-", "ff-")
    elif "/" in source or "\\" in source:
        # Local path
        path = Path(source)
        return path.name
    else:
        # Assume it's a package name
        return source

    return None


def _extract_package_name(source: str) -> str:
    """Try to extract the actual package name from source."""
    if source.startswith("git+"):
        # For git sources, we might need to guess the package name
        # This is simplified - would need to actually check the package
        parts = source.split("/")
        if parts:
            return parts[-1].replace(".git", "")
    elif "/" in source or "\\" in source:
        # Local path - would need to read pyproject.toml
        return Path(source).name
    else:
        # Direct package name
        return source

    return source
