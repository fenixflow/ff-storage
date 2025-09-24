"""
Configuration management for the CLI with dynamic branding support.
"""

import os
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import tomli_w
import tomllib
from ff_logger import ConsoleLogger
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console

from ff_cli.branding import get_brand

console = Console()


@dataclass
class PluginConfig:
    """Configuration for an installed plugin."""

    version: str
    source: str
    installed_at: str = ""
    package_name: str = ""
    source_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class ServiceOverride:
    """Configuration for a service override."""

    source: str  # Path to the override file
    modified_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class FenixConfig:
    """Main configuration for CLI."""

    plugins: dict[str, PluginConfig] = field(default_factory=dict)
    services: dict[str, ServiceOverride] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for TOML serialization."""
        return {
            "plugins": {name: plugin.to_dict() for name, plugin in self.plugins.items()},
            "services": {name: service.to_dict() for name, service in self.services.items()},
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FenixConfig":
        """Create from dictionary."""
        plugins = {}
        if "plugins" in data:
            for name, plugin_data in data["plugins"].items():
                plugins[name] = PluginConfig(**plugin_data)

        services = {}
        if "services" in data:
            for name, service_data in data["services"].items():
                services[name] = ServiceOverride(**service_data)

        return cls(
            plugins=plugins,
            services=services,
            settings=data.get("settings", {}),
        )


class PluginConfigModel(BaseModel):
    """Plugin-specific configuration for pydantic."""

    name: str
    enabled: bool = True
    config: dict = Field(default_factory=dict)


class CLISettings(BaseSettings):
    """Main CLI configuration using Pydantic Settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Core settings (will be set from branding)
    app_name: str | None = None  # Will be set from brand
    debug: bool = False
    verbose: bool = False
    log_level: str = "INFO"
    log_format: str = "pretty"  # "json" or "pretty"

    # Editor settings
    editor_command: str = os.environ.get("EDITOR", "vi")

    # Database settings (for development)
    dev_db_password: SecretStr = SecretStr("postgres")
    dev_db_port: int = 5432
    dev_db_name: str = "postgres"
    dev_db_user: str = "postgres"

    # Infrastructure settings
    aws_region: str | None = None
    aws_profile: str | None = None
    environment: str = "local"  # local, dev, staging, prod

    # Plugin settings
    plugins_dir: Path | None = None  # Will be set from brand
    enabled_plugins: list[str] = Field(default_factory=list)
    auto_load_plugins: bool = True

    # Docker settings
    docker_network: str | None = None  # Will be set from brand
    docker_registry: str | None = None

    # Development settings
    dev_mode: bool = False
    auto_reload: bool = False

    def __init__(self, **data):
        """Initialize settings with brand configuration."""
        super().__init__(**data)

        # Apply brand settings if not explicitly set
        brand = get_brand()
        if self.app_name is None:
            self.app_name = brand.app_name
        if self.docker_network is None:
            self.docker_network = brand.docker_network
        if self.plugins_dir is None:
            self.plugins_dir = brand.config_dir / "plugins"

    @property
    def config_dir(self) -> Path:
        """Get the configuration directory."""
        return get_brand().config_dir

    @property
    def cache_dir(self) -> Path:
        """Get the cache directory."""
        return self.config_dir / "cache"

    @property
    def logs_dir(self) -> Path:
        """Get the logs directory."""
        return self.config_dir / "logs"

    @property
    def registry_file(self) -> Path:
        """Get the plugin registry file path."""
        return self.config_dir / ".plugin_data" / "registry.json"

    @property
    def services_dir(self) -> Path:
        """Get the services directory."""
        return self.config_dir / "services"

    @property
    def scripts_dir(self) -> Path:
        """Get the scripts directory."""
        return self.config_dir / "scripts"

    def ensure_dirs(self) -> None:
        """Ensure all required directories exist."""
        self.config_dir.mkdir(exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        self.services_dir.mkdir(parents=True, exist_ok=True)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        (self.services_dir / "plugins").mkdir(exist_ok=True)
        (self.scripts_dir / "plugins").mkdir(exist_ok=True)

    def get_db_url(self, host: str = "localhost") -> str:
        """Get PostgreSQL connection URL."""
        password = self.dev_db_password.get_secret_value()
        return f"postgresql://{self.dev_db_user}:{password}@{host}:{self.dev_db_port}/{self.dev_db_name}"

    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "prod"

    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment in ["local", "dev"] or self.dev_mode


# Initialize the default logger with application context
default_logger = ConsoleLogger(
    name="default_logger",
    level="INFO",
    context={"app_name": get_brand().app_name, "version": "0.1.0", "environment": "local"},
)


@lru_cache
def get_settings() -> CLISettings:
    """Get cached settings instance."""
    # Get environment-specific prefix from brand
    brand = get_brand()
    os.environ.setdefault("ENV_PREFIX", brand.cli_name.upper() + "_")

    settings = CLISettings()
    settings.ensure_dirs()

    # Update logger configuration based on settings
    default_logger.level = settings.log_level.upper()

    return settings


@lru_cache(maxsize=128)
def get_logger(scope: str) -> ConsoleLogger:
    """Get a scoped logger for a specific module or component.

    Args:
        scope: The name/scope for the logger (e.g., "plugins", "docker", "services")

    Returns:
        Scoped logger instance
    """
    brand = get_brand()
    return ConsoleLogger(
        name=scope,
        level=get_settings().log_level.upper(),
        context={
            "app_name": brand.app_name,
            "component": scope,
            "environment": get_settings().environment,
        },
    )


class ConfigManager:
    """Manages CLI configuration with branding support."""

    def __init__(self, config_dir: Path | None = None):
        """Initialize config manager.

        Args:
            config_dir: Optional custom config directory.
                       Defaults to brand config dir
        """
        brand = get_brand()
        if config_dir:
            self.config_dir = config_dir
        else:
            self.config_dir = brand.config_dir

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

    def add_plugin(
        self, name: str, version: str, source: str, package_name: str = "", source_path: str = ""
    ) -> None:
        """Add or update a plugin in the configuration.

        Args:
            name: Plugin name
            version: Plugin version
            source: Installation source (e.g., git URL, pypi)
            package_name: Package name for the plugin
            source_path: Source path for the plugin
        """
        from datetime import datetime

        self.config.plugins[name] = PluginConfig(
            version=version,
            source=source,
            installed_at=datetime.now().isoformat(),
            package_name=package_name,
            source_path=source_path,
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

    def add_service_override(self, name: str, source: str) -> None:
        """Add or update a service override in the configuration.

        Args:
            name: Service name
            source: Path to the override file
        """
        from datetime import datetime

        self.config.services[name] = ServiceOverride(
            source=source, modified_at=datetime.now().isoformat()
        )
        self.save_config()

    def remove_service_override(self, name: str) -> bool:
        """Remove a service override from the configuration.

        Args:
            name: Service name to remove

        Returns:
            True if service was removed, False if not found
        """
        if name in self.config.services:
            del self.config.services[name]
            self.save_config()
            return True
        return False

    def get_service_override(self, name: str) -> ServiceOverride | None:
        """Get configuration for a specific service override."""
        return self.config.services.get(name)

    def list_service_overrides(self) -> dict[str, ServiceOverride]:
        """List all service overrides in configuration."""
        return self.config.services
