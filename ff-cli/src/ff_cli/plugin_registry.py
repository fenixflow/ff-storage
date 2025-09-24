"""Plugin registry management for tracking installed plugins."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from ff_cli.config import get_logger, get_settings

console = Console()
logger = get_logger("plugin_registry")


def get_registry_file() -> Path:
    """Get the plugin registry file path."""
    settings = get_settings()
    return settings.registry_file


def load_registry() -> dict[str, Any]:
    """Load the plugin registry from disk.

    Returns:
        Dictionary containing plugin registry data
    """
    registry_file = get_registry_file()

    if not registry_file.exists():
        # Return empty registry
        return {"plugins": {}, "version": "1.0"}

    try:
        with open(registry_file) as f:
            data = json.load(f)
            # Handle old format (flat structure)
            if "plugins" not in data:
                # Convert old format to new
                return {"plugins": data, "version": "1.0"}
            return data
    except Exception as e:
        logger.error(f"Failed to load registry: {e}")
        console.print(f"[yellow]Warning: Could not load plugin registry: {e}[/yellow]")
        return {"plugins": {}, "version": "1.0"}


def save_registry(registry: dict[str, Any]) -> bool:
    """Save the plugin registry to disk.

    Args:
        registry: Registry data to save

    Returns:
        True if successful
    """
    registry_file = get_registry_file()

    # Ensure directory exists
    registry_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(registry_file, "w") as f:
            json.dump(registry, f, indent=2, default=str)
        return True
    except Exception as e:
        logger.error(f"Failed to save registry: {e}")
        console.print(f"[red]Error: Could not save plugin registry: {e}[/red]")
        return False


def add_plugin_to_registry(
    name: str,
    source_path: str,
    plugin_module: str,
    entry_point: str,
    package_name: str = "",
    description: str = "",
) -> None:
    """Add a plugin to the registry (backward compatibility)."""
    register_plugin(
        name=name,
        source_path=source_path,
        package_name=package_name or plugin_module,
        description=description,
        plugin_module=plugin_module,
        entry_point=entry_point,
    )


def register_plugin(
    name: str,
    source_path: str,
    package_name: str | None = None,
    version: str = "unknown",
    description: str = "",
    plugin_module: str | None = None,
    entry_point: str | None = None,
) -> bool:
    """Register a plugin in the registry.

    Args:
        name: Plugin name (command name)
        source_path: Path to the plugin source
        package_name: Python package name
        version: Plugin version
        description: Plugin description
        plugin_module: Plugin module (for backward compatibility)
        entry_point: Entry point (for backward compatibility)

    Returns:
        True if successful
    """
    registry = load_registry()

    # Add or update plugin entry
    registry["plugins"][name] = {
        "source_path": str(Path(source_path).resolve()),
        "package_name": package_name or name,
        "plugin_module": plugin_module or name,
        "entry_point": entry_point or f"{name}.cli:plugin",
        "version": version,
        "description": description,
        "install_date": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    return save_registry(registry)


def remove_plugin_from_registry(name: str) -> bool:
    """Remove a plugin from the registry (backward compatibility)."""
    return unregister_plugin(name)


def unregister_plugin(name: str) -> bool:
    """Unregister a plugin from the registry.

    Args:
        name: Plugin name to remove

    Returns:
        True if plugin was removed
    """
    registry = load_registry()

    if name in registry["plugins"]:
        del registry["plugins"][name]
        save_registry(registry)
        logger.info(f"Unregistered plugin: {name}")
        return True

    return False


def get_plugin_info(name: str) -> dict[str, Any] | None:
    """Get information about a registered plugin.

    Args:
        name: Plugin name

    Returns:
        Plugin information or None if not found
    """
    registry = load_registry()
    return registry["plugins"].get(name)


def is_plugin_installed(name: str) -> bool:
    """Check if a plugin is installed."""
    registry = load_registry()
    return name in registry["plugins"]


def list_installed_plugins() -> dict[str, dict[str, Any]]:
    """List all installed plugins from the registry.

    Returns:
        Dictionary of plugin name to plugin info
    """
    registry = load_registry()
    plugins = registry.get("plugins", {})

    # Check source paths
    for _, info in plugins.items():
        source_path = info.get("source_path")
        if source_path:
            info["source_exists"] = Path(source_path).exists()
        else:
            info["source_exists"] = False

    return plugins


def update_plugin_info(
    name: str,
    version: str | None = None,
    description: str | None = None,
    source_path: str | None = None,
) -> bool:
    """Update plugin information in the registry.

    Args:
        name: Plugin name
        version: New version (optional)
        description: New description (optional)
        source_path: New source path (optional)

    Returns:
        True if successful
    """
    registry = load_registry()

    if name not in registry["plugins"]:
        logger.warning(f"Plugin {name} not found in registry")
        return False

    plugin_info = registry["plugins"][name]

    if version is not None:
        plugin_info["version"] = version
    if description is not None:
        plugin_info["description"] = description
    if source_path is not None:
        plugin_info["source_path"] = str(Path(source_path).resolve())

    plugin_info["updated_at"] = datetime.now().isoformat()

    return save_registry(registry)


def verify_registry() -> tuple[list[str], list[str]]:
    """Verify the plugin registry integrity.

    Returns:
        Tuple of (missing_plugins, invalid_paths)
    """
    registry = load_registry()
    missing_plugins = []
    invalid_paths = []

    for name, info in registry["plugins"].items():
        source_path = info.get("source_path")

        if source_path:
            path = Path(source_path)
            if not path.exists():
                invalid_paths.append(name)

        # Check if package is installed
        try:
            from importlib import metadata

            package_name = info.get("package_name", name)
            metadata.distribution(package_name)
        except metadata.PackageNotFoundError:
            missing_plugins.append(name)

    return missing_plugins, invalid_paths


def clean_registry() -> int:
    """Clean up invalid entries from the registry.

    Returns:
        Number of entries removed
    """
    registry = load_registry()

    missing_plugins, invalid_paths = verify_registry()
    to_remove = set(missing_plugins) | set(invalid_paths)

    for name in to_remove:
        if name in registry["plugins"]:
            logger.info(f"Removing invalid plugin entry: {name}")
            del registry["plugins"][name]

    if to_remove:
        save_registry(registry)

    return len(to_remove)


def export_registry(output_path: Path | None = None) -> str:
    """Export the registry to JSON format.

    Args:
        output_path: Optional path to save the export

    Returns:
        JSON string of registry data
    """
    registry = load_registry()
    json_str = json.dumps(registry, indent=2, default=str)

    if output_path:
        with open(output_path, "w") as f:
            f.write(json_str)
        logger.info(f"Exported registry to {output_path}")

    return json_str


def import_registry(input_path: Path) -> bool:
    """Import a registry from a JSON file.

    Args:
        input_path: Path to the JSON file

    Returns:
        True if successful
    """
    if not input_path.exists():
        console.print(f"[red]File not found: {input_path}[/red]")
        return False

    try:
        with open(input_path) as f:
            new_registry = json.load(f)

        # Handle old format
        if "plugins" not in new_registry:
            new_registry = {"plugins": new_registry, "version": "1.0"}

        # Validate structure
        if "plugins" not in new_registry:
            console.print("[red]Invalid registry format: missing 'plugins' key[/red]")
            return False

        # Merge with existing registry
        current_registry = load_registry()
        current_registry["plugins"].update(new_registry["plugins"])

        return save_registry(current_registry)

    except Exception as e:
        logger.error(f"Failed to import registry: {e}")
        console.print(f"[red]Failed to import registry: {e}[/red]")
        return False
