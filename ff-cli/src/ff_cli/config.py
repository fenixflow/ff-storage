"""
Configuration management for Fenix CLI.
"""

import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import tomli_w
from rich.console import Console

console = Console()


@dataclass
class PluginConfig:
    """Configuration for an installed plugin."""

    version: str
    source: str
    installed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class FenixConfig:
    """Main configuration for Fenix CLI."""

    plugins: dict[str, PluginConfig] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for TOML serialization."""
        return {
            "plugins": {name: plugin.to_dict() for name, plugin in self.plugins.items()},
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FenixConfig":
        """Create from dictionary."""
        plugins = {}
        if "plugins" in data:
            for name, plugin_data in data["plugins"].items():
                plugins[name] = PluginConfig(**plugin_data)

        return cls(plugins=plugins, settings=data.get("settings", {}))


class ConfigManager:
    """Manages Fenix CLI configuration."""

    def __init__(self, config_dir: Path | None = None):
        """Initialize config manager.

        Args:
            config_dir: Optional custom config directory.
                       Defaults to ~/.fenix
        """
        if config_dir:
            self.config_dir = config_dir
        else:
            self.config_dir = Path.home() / ".fenix"

        self.config_file = self.config_dir / "config.toml"
        self._ensure_config_dir()
        self.config = self._load_config()

    def _ensure_config_dir(self) -> None:
        """Ensure the config directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> FenixConfig:
        """Load configuration from file."""
        if not self.config_file.exists():
            # Return default config if file doesn't exist
            return FenixConfig()

        try:
            with open(self.config_file, "rb") as f:
                data = tomllib.load(f)
            return FenixConfig.from_dict(data)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load config: {e}[/yellow]")
            console.print("[yellow]Using default configuration[/yellow]")
            return FenixConfig()

    def save_config(self) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_file, "wb") as f:
                tomli_w.dump(self.config.to_dict(), f)
        except Exception as e:
            console.print(f"[red]Error saving config: {e}[/red]")
            raise

    def add_plugin(self, name: str, version: str, source: str) -> None:
        """Add or update a plugin in the configuration.

        Args:
            name: Plugin name
            version: Plugin version
            source: Installation source (e.g., git URL, pypi)
        """
        from datetime import datetime

        self.config.plugins[name] = PluginConfig(
            version=version, source=source, installed_at=datetime.now().isoformat()
        )
        self.save_config()

    def remove_plugin(self, name: str) -> bool:
        """Remove a plugin from the configuration.

        Args:
            name: Plugin name to remove

        Returns:
            True if plugin was removed, False if not found
        """
        if name in self.config.plugins:
            del self.config.plugins[name]
            self.save_config()
            return True
        return False

    def get_plugin_config(self, name: str) -> PluginConfig | None:
        """Get configuration for a specific plugin."""
        return self.config.plugins.get(name)

    def list_plugins(self) -> dict[str, PluginConfig]:
        """List all plugins in configuration."""
        return self.config.plugins

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a configuration setting.

        Args:
            key: Setting key (supports dot notation for nested values)
            default: Default value if key not found
        """
        keys = key.split(".")
        value = self.config.settings

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set_setting(self, key: str, value: Any) -> None:
        """Set a configuration setting.

        Args:
            key: Setting key (supports dot notation for nested values)
            value: Value to set
        """
        keys = key.split(".")
        settings = self.config.settings

        # Navigate to the parent of the target key
        for k in keys[:-1]:
            if k not in settings:
                settings[k] = {}
            settings = settings[k]

        # Set the value
        settings[keys[-1]] = value
        self.save_config()

    def get_config_path(self) -> Path:
        """Get the configuration file path."""
        return self.config_file
