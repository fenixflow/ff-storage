"""
Plugin registry management for Fenix CLI.

This module handles tracking installed plugins, their source paths,
and metadata to enable upgrades and removals.
"""

import json
import shutil
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


def get_plugins_dir() -> Path:
    """Get the directory where plugins are installed."""
    plugins_dir = Path(__file__).parent / "installed_plugins"
    plugins_dir.mkdir(exist_ok=True)
    return plugins_dir


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
    description: str = "",
) -> None:
    """Add a plugin to the registry."""
    registry = load_registry()
    registry[name] = {
        "source_path": str(Path(source_path).resolve()),
        "plugin_module": plugin_module,
        "entry_point": entry_point,
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


def copy_plugin_files(source_path: Path, plugin_module: str, plugin_name: str) -> Path:
    """
    Copy plugin files from source to the plugins directory.

    Args:
        source_path: Path to the plugin source directory
        plugin_module: Name of the plugin module to copy
        plugin_name: Name to use for the installed plugin

    Returns:
        Path to the installed plugin directory
    """
    plugins_dir = get_plugins_dir()
    # Use the original module name, not the plugin name, to keep imports working
    target_dir = plugins_dir / plugin_module

    # Remove existing plugin directory if it exists
    if target_dir.exists():
        shutil.rmtree(target_dir)

    # Find the plugin module in the source
    source_module_path = source_path / plugin_module

    if not source_module_path.exists():
        # Try to find it in src/ or other common locations
        for possible_path in [
            source_path / "src" / plugin_module,
            source_path / "lib" / plugin_module,
        ]:
            if possible_path.exists():
                source_module_path = possible_path
                break

    if not source_module_path.exists():
        raise FileNotFoundError(f"Plugin module {plugin_module} not found in {source_path}")

    # Copy the plugin module
    shutil.copytree(source_module_path, target_dir)

    return target_dir


def remove_plugin_files(plugin_name: str) -> bool:
    """
    Remove plugin files from the plugins directory.

    Args:
        plugin_name: Name of the plugin to remove

    Returns:
        True if files were removed, False if not found
    """
    # Get the plugin module name from registry
    info = get_plugin_info(plugin_name)
    if not info:
        return False

    plugins_dir = get_plugins_dir()
    # Use the module name, not the plugin name
    plugin_dir = plugins_dir / info.get("plugin_module", plugin_name)

    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)
        return True
    return False


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

        # Check if plugin files exist (use module name, not plugin name)
        plugin_dir = get_plugins_dir() / info.get("plugin_module", name)
        files_exist = plugin_dir.exists()

        result[name] = {
            **info,
            "source_exists": source_exists,
            "files_exist": files_exist,
        }

    return result
