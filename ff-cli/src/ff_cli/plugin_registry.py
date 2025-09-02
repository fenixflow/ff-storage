"""
Plugin registry management for Fenix CLI.

This module handles tracking installed plugins, their source paths,
and metadata to enable upgrades and removals.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


def get_registry_file() -> Path:
    """Get the path to the plugin registry file."""
    # Store in the ff_cli package directory
    registry_dir = Path(__file__).parent / ".plugin_data"
    registry_dir.mkdir(exist_ok=True)
    return registry_dir / "registry.json"


def load_registry() -> dict[str, Any]:
    """Load the plugin registry from disk."""
    registry_file = get_registry_file()
    if registry_file.exists():
        try:
            return json.loads(registry_file.read_text())
        except (OSError, json.JSONDecodeError) as e:
            console.print(f"[yellow]Warning: Could not load registry: {e}[/yellow]")
            return {}
    return {}


def save_registry(registry: dict[str, Any]) -> None:
    """Save the plugin registry to disk."""
    registry_file = get_registry_file()
    try:
        registry_file.write_text(json.dumps(registry, indent=2))
    except OSError as e:
        console.print(f"[red]Error saving registry: {e}[/red]")
        raise


def add_plugin_to_registry(
    name: str,
    source_path: str,
    plugin_module: str,
    entry_point: str,
    package_name: str = "",
    description: str = "",
) -> None:
    """Add a plugin to the registry."""
    registry = load_registry()
    registry[name] = {
        "source_path": str(Path(source_path).resolve()),
        "plugin_module": plugin_module,
        "entry_point": entry_point,
        "package_name": package_name or plugin_module,  # For pip uninstall
        "description": description,
        "install_date": datetime.now().isoformat(),
    }
    save_registry(registry)


def remove_plugin_from_registry(name: str) -> bool:
    """Remove a plugin from the registry."""
    registry = load_registry()
    if name in registry:
        del registry[name]
        save_registry(registry)
        return True
    return False


def get_plugin_info(name: str) -> dict[str, Any] | None:
    """Get information about an installed plugin."""
    registry = load_registry()
    return registry.get(name)


def is_plugin_installed(name: str) -> bool:
    """Check if a plugin is installed."""
    return name in load_registry()


# Note: File copying functions removed in favor of editable installation
# Plugins are now installed directly via pip/uv in editable mode


def list_installed_plugins() -> dict[str, dict[str, Any]]:
    """
    List all installed plugins with their information.

    Returns:
        Dictionary of plugin names to their info
    """
    registry = load_registry()
    result = {}

    for name, info in registry.items():
        # Check if source path still exists
        source_exists = Path(info["source_path"]).exists()

        result[name] = {
            **info,
            "source_exists": source_exists,
        }

    return result
