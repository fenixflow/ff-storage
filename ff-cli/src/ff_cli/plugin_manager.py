"""Plugin manager for discovering and loading branded CLI plugins."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from rich.table import Table

from . import plugin_registry
from .branding import get_brand
from .plugin_base import get_plugin_status, has_status_support
from .utils.common import console


@dataclass
class Plugin:
    """Represents a loaded plugin."""

    name: str
    version: str
    description: str
    module_path: str
    app: typer.Typer | None = None
    source: str = "unknown"

    def load(self) -> typer.Typer:
        """Load the plugin's Typer app."""
        if self.app is None:
            try:
                # Import the module and get the plugin function
                module_parts = self.module_path.rsplit(":", 1)
                if len(module_parts) == 2:
                    module_name, func_name = module_parts
                    module = __import__(module_name, fromlist=[func_name])
                    plugin_func = getattr(module, func_name)
                    self.app = plugin_func()
                else:
                    raise ValueError(f"Invalid module path: {self.module_path}")
            except Exception as e:
                console.print(f"[red]Error loading plugin {self.name}: {e}[/red]")
                raise
        return self.app


class PluginManager:
    """Manages plugin discovery, loading, and registration."""

    def __init__(self):
        self.brand = get_brand()
        self.plugins: dict[str, Plugin] = {}
        self._discover_plugins()

    def _discover_plugins(self) -> None:
        """Discover installed plugins via entry points."""
        self._discover_entry_point_plugins()

    def _discover_entry_point_plugins(self) -> None:
        """Discover plugins via entry points."""
        try:
            from importlib.metadata import entry_points

            eps = entry_points()
            groups = {self.brand.plugin_entry_point}
            if self.brand.plugin_entry_point != "fenix.plugins":
                groups.add("fenix.plugins")

            plugin_eps = []
            if hasattr(eps, "select"):
                for group in groups:
                    try:
                        plugin_eps.extend(list(eps.select(group=group)))
                    except Exception as exc:  # pragma: no cover - defensive
                        console.print(
                            f"[yellow]Warning: Could not query entry point group {group}: {exc}[/yellow]"
                        )
            else:
                for group in groups:
                    plugin_eps.extend(eps.get(group, []))

            for ep in plugin_eps:
                try:
                    # Get plugin metadata from distribution
                    dist = ep.dist
                    description = ""
                    if dist:
                        metadata = dist.metadata
                        description = metadata.get("Summary", "") or metadata.get("Description", "")

                    # Check if this plugin is in our registry for source tracking
                    registry_info = plugin_registry.get_plugin_info(ep.name)
                    source = (
                        registry_info.get("source_path", "installed")
                        if registry_info
                        else "installed"
                    )

                    plugin = Plugin(
                        name=ep.name,
                        version=dist.version if dist else "unknown",
                        description=description
                        or (registry_info.get("description", "") if registry_info else ""),
                        module_path=f"{ep.module}:{ep.attr}",
                        source=source,
                    )
                    self.plugins[ep.name] = plugin
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not load plugin {ep.name}: {e}[/yellow]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not discover plugins: {e}[/yellow]")

    def get_plugin(self, name: str) -> Plugin | None:
        """Get a plugin by name."""
        return self.plugins.get(name)

    def list_plugins(self) -> list[Plugin]:
        """List all discovered plugins."""
        return list(self.plugins.values())

    def load_plugin(self, name: str) -> typer.Typer | None:
        """Load a specific plugin's Typer app."""
        plugin = self.get_plugin(name)
        if plugin:
            return plugin.load()
        return None

    def register_plugin_commands(self, main_app: typer.Typer) -> None:
        """Register all plugin commands as sub-commands of the main app."""
        for plugin_name, plugin in self.plugins.items():
            try:
                plugin_app = plugin.load()
                if plugin_app:
                    # Add the plugin as a sub-command with its name as the command
                    main_app.add_typer(
                        plugin_app,
                        name=plugin_name,
                        help=plugin.description or f"{plugin_name} plugin commands",
                    )
            except Exception as e:
                console.print(f"[red]Failed to register plugin {plugin_name}: {e}[/red]")

    def print_plugin_list(self) -> None:
        """Print a formatted list of plugins."""
        if not self.plugins:
            console.print("[yellow]No plugins installed[/yellow]")
            return

        table = Table(title="Installed Plugins")
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Version", style="green")
        table.add_column("Source", style="blue")
        table.add_column("Description", style="white")

        for plugin in self.plugins.values():
            # Shorten source path if it's a file path
            source = plugin.source
            if source.startswith("/"):
                # Show just the last two directories
                parts = Path(source).parts
                if len(parts) > 2:
                    source = f".../{parts[-2]}/{parts[-1]}"

            table.add_row(
                plugin.name,
                plugin.version,
                source,
                (
                    plugin.description[:40] + "..."
                    if len(plugin.description) > 40
                    else plugin.description
                ),
            )

        console.print(table)

    def print_plugin_info(self, name: str) -> None:
        """Print detailed information about a plugin."""
        plugin = self.get_plugin(name)
        if not plugin:
            console.print(f"[red]Plugin '{name}' not found[/red]")
            return

        console.print(f"\n[bold cyan]Plugin: {plugin.name}[/bold cyan]")
        console.print(f"Version: {plugin.version}")
        console.print(f"Description: {plugin.description}")
        console.print(f"Module: {plugin.module_path}")
        console.print(f"Source: {plugin.source}")

        # Try to load and show available commands
        try:
            app = plugin.load()
            if app:
                # Check for status support
                if has_status_support(app):
                    console.print("[green]✓ Status support enabled[/green]")

                if hasattr(app, "registered_commands"):
                    console.print("\n[bold]Available Commands:[/bold]")
                    for cmd in app.registered_commands:
                        if hasattr(cmd, "callback"):
                            help_text = cmd.callback.__doc__ or "No description"
                            console.print(f"  {cmd.name}: {help_text.strip()}")
        except Exception as e:
            console.print(f"\n[yellow]Could not load plugin commands: {e}[/yellow]")

    def get_plugin_status(self, name: str, verbose: bool = False) -> dict[str, Any] | None:
        """Get status from a specific plugin.

        Args:
            name: Plugin name
            verbose: Include detailed metrics

        Returns:
            Status dictionary or None if not supported
        """
        plugin = self.get_plugin(name)
        if not plugin:
            return None

        try:
            app = plugin.load()
            if app:
                return get_plugin_status(app, verbose=verbose)
        except Exception as e:
            return {
                "name": plugin.name,
                "healthy": False,
                "services": [],
                "message": f"Failed to get status: {e}",
                "errors": [str(e)],
            }
        return None

    def get_all_plugin_statuses(self, verbose: bool = False) -> dict[str, dict[str, Any]]:
        """Get status from all plugins that support it.

        Args:
            verbose: Include detailed metrics

        Returns:
            Dictionary mapping plugin names to their status
        """
        statuses = {}
        for name, _plugin in self.plugins.items():
            status = self.get_plugin_status(name, verbose=verbose)
            if status:
                statuses[name] = status
        return statuses
