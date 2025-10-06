"""Helpers for managing plugin service definitions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ff_cli.config import get_logger, get_settings

logger = get_logger("plugin_services")


@dataclass
class ServiceDefinition:
    """Representation of a plugin-provided service definition."""

    name: str
    path: Path


class ServiceManager:
    """Manage registration of plugin service definitions with the core CLI."""

    def __init__(self, plugin_name: str, plugin_dir: Path):
        settings = get_settings()
        self.plugin_name = plugin_name
        self.plugin_dir = plugin_dir
        self.services_dir = plugin_dir / "services"
        self.registry_dir = settings.services_dir / "plugins" / plugin_name

    # ------------------------------------------------------------------
    # Discovery helpers
    # ------------------------------------------------------------------
    def list_definitions(self) -> list[ServiceDefinition]:
        """Return all service definition files bundled with this plugin."""
        if not self.services_dir.exists():
            return []

        definitions: list[ServiceDefinition] = []
        for path in sorted(self.services_dir.glob("*.yaml")):
            definitions.append(ServiceDefinition(name=path.stem, path=path))
        return definitions

    def definitions_exist(self) -> bool:
        """Check whether the plugin ships any service definitions."""
        return self.services_dir.exists() and any(self.services_dir.glob("*.yaml"))

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------
    def register_all(self) -> list[str]:
        """Register every service definition with the main CLI."""
        definitions = self.list_definitions()
        if not definitions:
            return []

        self.registry_dir.mkdir(parents=True, exist_ok=True)

        registered: list[str] = []
        for definition in definitions:
            registered_name = self._registered_name(definition.name)
            target = self.registry_dir / f"{registered_name}.yaml"
            if target.exists():
                logger.debug("Service %s already registered", registered_name)
                continue
            try:
                target.symlink_to(definition.path.resolve())
                registered.append(registered_name)
            except FileExistsError:
                logger.debug("Service %s already registered", registered_name)

        return registered

    def unregister_all(self) -> list[str]:
        """Remove every registered service for this plugin."""
        if not self.registry_dir.exists():
            return []

        removed: list[str] = []
        for symlink in list(self.registry_dir.glob("*.yaml")):
            removed.append(symlink.stem)
            symlink.unlink(missing_ok=True)

        try:
            self.registry_dir.rmdir()
        except OSError:
            # Directory not empty - ignore
            pass

        return removed

    def list_registered(self) -> list[str]:
        """Return the names of registered services for this plugin."""
        if not self.registry_dir.exists():
            return []
        return sorted(path.stem for path in self.registry_dir.glob("*.yaml"))

    def registered_summary(self) -> Iterable[str]:
        """Yield formatted summary lines for registered services."""
        if not self.registry_dir.exists():
            return []
        for path in self.registry_dir.glob("*.yaml"):
            yield f"{path.stem} -> {path.resolve()}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _registered_name(self, name: str) -> str:
        return f"{self.plugin_name}_{name}"
