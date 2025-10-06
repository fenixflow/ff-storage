"""
Pydantic models for service configuration.
"""

import os
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from ff_cli.branding import get_brand


class HealthCheck(BaseModel):
    """Docker healthcheck configuration."""

    test: list[str]
    interval: str = "30s"
    timeout: str = "10s"
    retries: int = 3
    start_period: str | None = None


class ServiceDefinition(BaseModel):
    """Service definition from YAML file."""

    name: str
    image: str
    ports: list[str] | None = None
    environment: dict[str, str] | None = None
    volumes: list[str] | None = None
    command: str | list[str] | None = None
    healthcheck: HealthCheck | None = None
    restart: str = "unless-stopped"
    build: str | dict[str, Any] | None = None
    depends_on: list[str] | None = None
    networks: list[str] | None = None
    labels: dict[str, str] | None = None

    @field_validator("ports", mode="before")
    @classmethod
    def normalize_ports(cls, v):
        """Normalize port specifications to strings."""
        if v is None:
            return None
        normalized = []
        for port in v:
            if isinstance(port, int):
                normalized.append(f"{port}:{port}")
            elif isinstance(port, str) and ":" not in port:
                normalized.append(f"{port}:{port}")
            else:
                normalized.append(str(port))
        return normalized

    @field_validator("environment", mode="before")
    @classmethod
    def expand_environment(cls, v):
        """Expand environment variables in values."""
        if v is None:
            return None

        expanded = {}
        for key, value in v.items():
            if isinstance(value, str):
                # Expand ${VAR_NAME:-default} patterns
                pattern = r"\$\{([^:}]+)(?::-([^}]*))?\}"

                def replacer(match):
                    var_name = match.group(1)
                    default_value = match.group(2) or ""
                    return os.environ.get(var_name, default_value)

                expanded[key] = re.sub(pattern, replacer, value)
            else:
                expanded[key] = value
        return expanded


class ServiceConfig(BaseModel):
    """Complete service configuration with smart defaults."""

    name: str
    container_name: str | None = None
    image: str
    ports: list[str] | None = None
    environment: dict[str, str] | None = None
    volumes: list[str] | None = None
    command: str | list[str] | None = None
    healthcheck: HealthCheck | None = None
    restart: str = "unless-stopped"
    build: str | dict[str, Any] | None = None
    depends_on: list[str] | None = None
    networks: list[str] = Field(default_factory=lambda: [get_brand().docker_network])
    labels: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def set_defaults(self):
        """Set smart defaults for container configuration."""
        # Auto-generate container name if not provided
        brand = get_brand()

        if not self.container_name:
            self.container_name = f"{brand.container_prefix}-{self.name}"

        # Add OrbStack labels
        orbstack_labels = {
            "com.docker.compose.project": brand.docker_project,
            "com.docker.compose.service": self.name,
            "dev.orbstack.domains": f"{self.name}.{brand.orbstack_domain_suffix}",
            "ff.brand": brand.cli_name,
        }
        self.labels.update(orbstack_labels)

        # Ensure the brand network is present
        if brand.docker_network not in self.networks:
            self.networks.append(brand.docker_network)

        # Auto-add standard database volumes if not specified
        if not self.volumes and self.name in ["postgres", "mysql", "redis", "rabbitmq", "minio"]:
            data_path = self._get_default_data_path()
            if data_path:
                self.volumes = [f"{brand.container_prefix}-{self.name}-data:{data_path}"]

        return self

    def _get_default_data_path(self) -> str | None:
        """Get default data path for known services."""
        paths = {
            "postgres": "/var/lib/postgresql/data",
            "mysql": "/var/lib/mysql",
            "redis": "/data",
            "rabbitmq": "/var/lib/rabbitmq",
            "minio": "/data",
        }
        return paths.get(self.name)

    @classmethod
    def from_definition(cls, definition: ServiceDefinition) -> "ServiceConfig":
        """Create ServiceConfig from ServiceDefinition with defaults."""
        brand = get_brand()

        return cls(
            name=definition.name,
            image=definition.image,
            ports=definition.ports,
            environment=definition.environment,
            volumes=definition.volumes,
            command=definition.command,
            healthcheck=definition.healthcheck,
            restart=definition.restart,
            build=definition.build,
            depends_on=definition.depends_on,
            networks=definition.networks or [brand.docker_network],
            labels=definition.labels or {},
        )

    def to_docker_params(self) -> dict[str, Any]:
        """Convert to parameters for Docker API."""
        params = {
            "name": self.container_name,
            "image": self.image,
            "labels": self.labels,
            "restart_policy": {"Name": self.restart},
            "network_mode": self.networks[0] if self.networks else None,
        }

        # Add ports
        if self.ports:
            ports = {}
            port_bindings = {}
            for port_spec in self.ports:
                if ":" in port_spec:
                    host_port, container_port = port_spec.split(":")
                    ports[f"{container_port}/tcp"] = {}
                    port_bindings[f"{container_port}/tcp"] = [{"HostPort": host_port}]
                else:
                    ports[f"{port_spec}/tcp"] = {}
                    port_bindings[f"{port_spec}/tcp"] = [{"HostPort": port_spec}]
            params["ports"] = ports
            params["host_config"] = {"PortBindings": port_bindings}

        # Add environment
        if self.environment:
            params["environment"] = [f"{k}={v}" for k, v in self.environment.items()]

        # Add volumes
        if self.volumes:
            volumes = []
            binds = []
            for volume_spec in self.volumes:
                if ":" in volume_spec:
                    source, target = volume_spec.split(":", 1)
                    volumes.append(target)
                    binds.append(f"{source}:{target}")
                else:
                    volumes.append(volume_spec)
            params["volumes"] = volumes
            if "host_config" not in params:
                params["host_config"] = {}
            params["host_config"]["Binds"] = binds

        # Add command
        if self.command:
            if isinstance(self.command, str):
                params["command"] = self.command.split()
            else:
                params["command"] = self.command

        # Add healthcheck
        if self.healthcheck:
            params["healthcheck"] = {
                "Test": self.healthcheck.test,
                "Interval": self._parse_duration(self.healthcheck.interval),
                "Timeout": self._parse_duration(self.healthcheck.timeout),
                "Retries": self.healthcheck.retries,
            }
            if self.healthcheck.start_period:
                params["healthcheck"]["StartPeriod"] = self._parse_duration(
                    self.healthcheck.start_period
                )

        return params

    @staticmethod
    def _parse_duration(duration: str) -> int:
        """Parse duration string to nanoseconds."""
        # Simple parser for duration strings like "10s", "5m", "1h"
        import re

        match = re.match(r"(\d+)([smh])", duration)
        if not match:
            return 30 * 1_000_000_000  # Default to 30s

        value = int(match.group(1))
        unit = match.group(2)

        multipliers = {
            "s": 1_000_000_000,  # seconds to nanoseconds
            "m": 60 * 1_000_000_000,  # minutes to nanoseconds
            "h": 3600 * 1_000_000_000,  # hours to nanoseconds
        }

        return value * multipliers.get(unit, 1_000_000_000)
