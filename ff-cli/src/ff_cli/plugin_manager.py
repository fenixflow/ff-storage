"""
Plugin manager for discovering and loading Fenix CLI plugins.
"""

from dataclasses import dataclass

import typer
from rich.console import Console
from rich.table import Table

console = Console()


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
        self.plugins: dict[str, Plugin] = {}
        self._discover_plugins()

    def _discover_plugins(self) -> None:
        """Discover installed plugins via entry points."""
        try:
            from importlib.metadata import entry_points

            eps = entry_points()
            if hasattr(eps, "select"):
                # Python 3.10+ with select method
                plugin_eps = eps.select(group="fenix.plugins")
            else:
                # Fallback for different implementations
                plugin_eps = eps.get("fenix.plugins", [])

            for ep in plugin_eps:
                try:
                    # Get plugin metadata from distribution
                    dist = ep.dist
                    description = ""
                    if dist:
                        metadata = dist.metadata
                        description = metadata.get("Summary", "") or metadata.get("Description", "")

                    plugin = Plugin(
                        name=ep.name,
                        version=dist.version if dist else "unknown",
                        description=description,
                        module_path=f"{ep.module}:{ep.attr}",
                        source="installed",
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
        table.add_column("Description", style="white")

        for plugin in self.plugins.values():
            table.add_row(
                plugin.name,
                plugin.version,
                (
                    plugin.description[:50] + "..."
                    if len(plugin.description) > 50
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
            if app and hasattr(app, "registered_commands"):
                console.print("\n[bold]Available Commands:[/bold]")
                for cmd in app.registered_commands:
                    if hasattr(cmd, "callback"):
                        help_text = cmd.callback.__doc__ or "No description"
                        console.print(f"  {cmd.name}: {help_text.strip()}")
        except Exception as e:
            console.print(f"\n[yellow]Could not load plugin commands: {e}[/yellow]")
