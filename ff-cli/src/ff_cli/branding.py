"""
Dynamic branding configuration for the CLI.

This module provides the ability to rebrand the CLI for different
clients/projects without maintaining separate codebases.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import toml


@dataclass
class BrandConfig:
    """Configuration for CLI branding."""

    # Core branding
    cli_name: str = "fenix"
    cli_display_name: str = "Fenix CLI"
    cli_description: str = "Unified command-line interface"
    icon: str = "🐦‍🔥 "

    # Version and metadata
    version_prefix: str = "Fenix CLI"
    company_name: str = "Fenixflow"

    # Configuration paths
    config_dir_name: str = ".fenix"

    # Plugin system
    plugin_entry_point: str = "fenix.plugins"

    # Docker/network names
    docker_network: str = "fenix-network"
    container_prefix: str = "fenix"
    docker_project: str = "fenix"
    orbstack_domain_suffix: str = "fenix.orb.local"

    # Help and documentation
    help_header: str = "Unified command-line interface for team operations"
    help_examples: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Backfill dynamic defaults after initialization."""
        if not self.container_prefix:
            self.container_prefix = self.cli_name
        if not self.docker_project:
            self.docker_project = self.cli_name
        if not self.help_examples:
            self.help_examples = [
                f"{self.cli_name} --help                    # Show help",
                f"{self.cli_name} status                    # Show system status",
                f"{self.cli_name} services up postgres      # Start PostgreSQL",
                f"{self.cli_name} plugins list              # List installed plugins",
            ]

    @property
    def config_dir(self) -> Path:
        """Get the configuration directory path."""
        return Path.home() / self.config_dir_name

    @property
    def app_name(self) -> str:
        """Get the application name for logging."""
        return f"{self.cli_name}-cli"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "cli_name": self.cli_name,
            "cli_display_name": self.cli_display_name,
            "cli_description": self.cli_description,
            "icon": self.icon,
            "version_prefix": self.version_prefix,
            "company_name": self.company_name,
            "config_dir_name": self.config_dir_name,
            "plugin_entry_point": self.plugin_entry_point,
            "docker_network": self.docker_network,
            "container_prefix": self.container_prefix,
            "docker_project": self.docker_project,
            "orbstack_domain_suffix": self.orbstack_domain_suffix,
            "help_header": self.help_header,
            "help_examples": self.help_examples,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BrandConfig":
        """Create from dictionary."""
        return cls(**data)

    @classmethod
    def from_toml(cls, path: Path) -> "BrandConfig":
        """Load from TOML file."""
        with open(path) as f:
            data = toml.load(f)
        return cls.from_dict(data.get("brand", {}))

    def save_toml(self, path: Path) -> None:
        """Save to TOML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            toml.dump({"brand": self.to_dict()}, f)


# Predefined brand configurations
BRANDS = {
    "fenix": BrandConfig(
        cli_name="fenix",
        cli_display_name="Fenix CLI",
        cli_description="Unified command-line interface for the Fenix ecosystem",
        icon="🐦‍🔥",
        version_prefix="Fenix CLI",
        company_name="Fenixflow",
        config_dir_name=".fenix",
        plugin_entry_point="fenix.plugins",
        docker_network="fenix-network",
        container_prefix="fenix",
        docker_project="fenix",
        orbstack_domain_suffix="fenix.orb.local",
        help_header="Unified command-line interface for the Fenix ecosystem",
    ),
}


# Global brand configuration instance
_current_brand: BrandConfig | None = None

# User override storage (brand agnostic)
USER_STATE_DIR = Path.home() / ".ff-cli"
USER_BRAND_PATH = USER_STATE_DIR / "branding.toml"


def _detect_brand_from_executable() -> BrandConfig:
    """Detect brand based on the command/entry point used."""
    import sys

    if sys.argv:
        command_path = sys.argv[0]
        command_name = Path(command_path).name
        if command_name in BRANDS:
            return BRANDS[command_name]
    return BRANDS["fenix"]


def get_user_brand_path() -> Path:
    """Return the path to the user override brand file."""
    return USER_BRAND_PATH


def user_brand_exists(path: Path | None = None) -> bool:
    """Check whether a persisted brand override exists."""
    return (path or USER_BRAND_PATH).exists()


def load_user_brand_config(path: Path | None = None) -> BrandConfig | None:
    """Load a persisted brand override if available."""
    brand_file = path or USER_BRAND_PATH
    if not brand_file.exists():
        return None
    try:
        return BrandConfig.from_toml(brand_file)
    except Exception:
        return None


def save_user_brand_config(config: BrandConfig, path: Path | None = None) -> None:
    """Persist a brand override to disk."""
    brand_file = path or USER_BRAND_PATH
    brand_file.parent.mkdir(parents=True, exist_ok=True)
    config.save_toml(brand_file)


def clear_user_brand_config(path: Path | None = None) -> None:
    """Remove the persisted brand override if present."""
    brand_file = path or USER_BRAND_PATH
    if brand_file.exists():
        brand_file.unlink()


def reset_brand_cache() -> None:
    """Reset the cached brand so it is re-evaluated on next access."""
    global _current_brand
    _current_brand = None


def get_brand() -> BrandConfig:
    """Get the current brand configuration."""
    global _current_brand

    if _current_brand is None:
        override = load_user_brand_config()
        if override:
            _current_brand = override
        else:
            _current_brand = _detect_brand_from_executable()

    return _current_brand


def set_brand(brand: BrandConfig | str) -> None:
    """Set the current brand configuration."""
    global _current_brand

    if isinstance(brand, str):
        if brand not in BRANDS:
            raise ValueError(f"Unknown brand: {brand}")
        _current_brand = BRANDS[brand]
    else:
        _current_brand = brand


def apply_brand_from_file(path: Path) -> BrandConfig:
    """Apply brand configuration from a file."""
    brand = BrandConfig.from_toml(path)
    set_brand(brand)
    return brand
