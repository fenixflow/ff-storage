"""
Service manager for orchestrating Docker services.
"""

import os
import subprocess
from pathlib import Path

import yaml
from rich.table import Table

from ..branding import get_brand
from ..config import ConfigManager, get_settings
from ..utils.common import console
from ..utils.docker import DockerManager
from .models import ServiceConfig, ServiceDefinition


class ServiceManager:
    """Manages service lifecycle and configuration."""

    def __init__(self, config_manager: ConfigManager | None = None):
        """Initialize service manager."""
        self.brand = get_brand()
        self.docker = DockerManager()
        self.config_manager = config_manager or ConfigManager()
        self.repo_services_path = (
            Path(__file__).parent.parent.parent.parent / "services" / "defaults"
        )
        self.user_services_path = self.config_manager.config_dir / "services"
        self.plugin_services_path = self.user_services_path / "plugins"

    def initialize(self) -> None:
        """Initialize Fenix directory structure."""
        # Ensure user directories via settings helper (keeps brand alignment)
        settings = get_settings()
        settings.ensure_dirs()
        self.user_services_path.mkdir(parents=True, exist_ok=True)

        # Create network if it doesn't exist
        self.docker.create_network(self.brand.docker_network)

        console.print(
            f"[green]✓[/green] Initialized ~/{self.brand.config_dir_name} directory structure"
        )
        console.print(f"[green]✓[/green] Created {self.brand.docker_network} network")

    def get_service_definition(self, name: str) -> ServiceDefinition | None:
        """Get service definition, checking user overrides first."""
        # Check user overrides first
        user_file = self.user_services_path / f"{name}.yaml"
        if user_file.exists():
            return self._load_yaml(user_file)

        # Check plugin registrations
        plugin_file = self._get_plugin_service_file(name)
        if plugin_file:
            return self._load_yaml(plugin_file)

        # Check repo defaults
        repo_file = self.repo_services_path / f"{name}.yaml"
        if repo_file.exists():
            return self._load_yaml(repo_file)

        return None

    def _load_yaml(self, path: Path) -> ServiceDefinition | None:
        """Load service definition from YAML file."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
                return ServiceDefinition(**data)
        except Exception as e:
            console.print(f"[red]Error loading {path}: {e}[/red]")
            return None

    def _get_plugin_service_file(self, name: str) -> Path | None:
        """Locate a registered plugin service definition."""
        if not self.plugin_services_path.exists():
            return None

        for plugin_dir in self.plugin_services_path.iterdir():
            if not plugin_dir.is_dir():
                continue
            candidate = plugin_dir / f"{name}.yaml"
            if candidate.exists():
                return candidate
        return None

    def list_services(self) -> dict[str, str]:
        """List all available services with their sources."""
        services = {}

        # Get repo defaults
        if self.repo_services_path.exists():
            for yaml_file in self.repo_services_path.glob("*.yaml"):
                name = yaml_file.stem
                services[name] = "default"

        # Get user overrides
        if self.user_services_path.exists():
            for yaml_file in self.user_services_path.glob("*.yaml"):
                name = yaml_file.stem
                services[name] = "user"

        # Get plugin-provided services
        if self.plugin_services_path.exists():
            for plugin_dir in self.plugin_services_path.iterdir():
                if not plugin_dir.is_dir():
                    continue
                for yaml_file in plugin_dir.glob("*.yaml"):
                    name = yaml_file.stem
                    services[name] = "plugin"

        return services

    def which_service(self, name: str) -> str | None:
        """Show which configuration file is being used for a service."""
        user_file = self.user_services_path / f"{name}.yaml"
        if user_file.exists():
            return str(user_file)

        plugin_file = self._get_plugin_service_file(name)
        if plugin_file:
            return str(plugin_file)

        repo_file = self.repo_services_path / f"{name}.yaml"
        if repo_file.exists():
            return str(repo_file)

        return None

    def create_service(self, name: str, template: str | None = None) -> Path:
        """Create a new service definition."""
        service_file = self.user_services_path / f"{name}.yaml"

        if service_file.exists():
            raise ValueError(f"Service {name} already exists at {service_file}")

        if template:
            # Copy from template
            template_def = self.get_service_definition(template)
            if not template_def:
                raise ValueError(f"Template service {template} not found")

            # Modify for new service
            template_def.name = name
            data = template_def.model_dump(exclude_none=True)
        else:
            # Create minimal template
            data = {
                "name": name,
                "image": "alpine:latest",
                "command": "sleep infinity",
                "restart": "unless-stopped",
            }

        with open(service_file, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        return service_file

    def copy_service(self, source: str, target: str) -> Path:
        """Copy a service definition to a new name."""
        source_def = self.get_service_definition(source)
        if not source_def:
            raise ValueError(f"Source service {source} not found")

        return self.create_service(target, template=source)

    def edit_service(self, name: str) -> None:
        """Open service definition in editor."""
        # Ensure user override exists
        user_file = self.user_services_path / f"{name}.yaml"
        if not user_file.exists():
            # Copy from default if exists
            repo_file = self.repo_services_path / f"{name}.yaml"
            plugin_file = self._get_plugin_service_file(name)
            if repo_file.exists():
                import shutil

                shutil.copy(repo_file, user_file)
                console.print(f"[yellow]Copied default to {user_file}[/yellow]")
            elif plugin_file and Path(plugin_file).exists():
                import shutil

                shutil.copy(plugin_file, user_file)
                console.print(f"[yellow]Copied plugin definition to {user_file}[/yellow]")
            else:
                raise ValueError(f"Service {name} not found")

        # Open in editor (prefer Zed, fallback to $EDITOR, then nano)
        editors = [
            "zed",
            os.environ.get("EDITOR", ""),
            "code",
            "vim",
            "nano",
        ]

        for editor in editors:
            if editor and subprocess.run(["which", editor], capture_output=True).returncode == 0:
                subprocess.run([editor, str(user_file)])
                break
        else:
            console.print(f"[yellow]No editor found. Edit manually: {user_file}[/yellow]")

    def up_service(self, name: str, build: bool = False) -> None:
        """Start a service."""
        # Get service definition
        definition = self.get_service_definition(name)
        if not definition:
            raise ValueError(f"Service {name} not found")

        # Convert to config with defaults
        config = ServiceConfig.from_definition(definition)

        # Ensure network exists
        self.docker.create_network(self.brand.docker_network)

        # Check for port conflicts
        if config.ports:
            conflicts = self.docker.check_port_conflicts(config.ports)
            for port_spec, in_use in conflicts:
                if in_use:
                    console.print(f"[yellow]Warning: Port {port_spec} is already in use[/yellow]")

        # Build image if needed
        if build and config.build:
            console.print(f"[cyan]Building image for {name}...[/cyan]")
            if isinstance(config.build, str):
                build_path = config.build
                dockerfile = None
            else:
                build_path = config.build.get("context", ".")
                dockerfile = config.build.get("dockerfile")

            tag = f"{self.brand.cli_name}/{name}:latest"
            image_id, logs = self.docker.build_image(build_path, tag, dockerfile)
            config.image = tag
            console.print(f"[green]Built image: {tag} ({image_id[:12]})[/green]")
        else:
            # Pull image if needed
            self.docker.pull_image(config.image)

        # Create volumes if specified
        if config.volumes:
            for volume_spec in config.volumes:
                if ":" in volume_spec:
                    volume_name = volume_spec.split(":")[0]
                    if not volume_name.startswith("/"):  # Named volume, not bind mount
                        self.docker.create_volume(volume_name)

        # Check if container exists
        if self.docker.container_exists(config.container_name):
            # Start existing container
            if self.docker.start_container(config.container_name):
                console.print(f"[green]Started existing container: {config.container_name}[/green]")
        else:
            # Create and start new container via docker CLI
            self.docker.run_container_from_config(config)
            console.print(f"[green]Created and started container: {config.container_name}[/green]")

            # Connect to additional networks if specified
            if len(config.networks) > 1:
                for network_name in config.networks[1:]:
                    if not self.docker.network_exists(network_name):
                        self.docker.create_network(network_name)
                    self.docker.connect_container_to_network(config.container_name, network_name)

    def down_service(self, name: str, volumes: bool = False) -> None:
        """Stop and remove a service."""
        definition = self.get_service_definition(name)
        config = ServiceConfig.from_definition(definition) if definition else None

        container_name = (
            config.container_name
            if config and config.container_name
            else f"{self.brand.container_prefix}-{name}"
        )

        if not self.docker.container_exists(container_name):
            console.print(f"[yellow]Container {container_name} not found[/yellow]")
            return

        console.print(f"[cyan]Stopping {name}...[/cyan]")
        stopped = self.docker.stop_container(container_name)

        removed = False
        if stopped:
            removed = self.docker.remove_container(container_name)
        if not removed:
            removed = self.docker.remove_container(container_name, force=True)

        if removed:
            console.print(f"[green]✅ {name} stopped and removed[/green]")
        else:
            console.print(f"[red]Failed to remove {name}[/red]")

        if volumes:
            console.print(
                f"[yellow]Volume retention is enforced; persistent data for {name} was left intact.[/yellow]"
            )

    def restart_service(self, name: str) -> None:
        """Restart a service."""
        container_name = f"{self.brand.container_prefix}-{name}"

        if self.docker.container_exists(container_name):
            self.docker.restart_container(container_name)
        else:
            console.print(f"[yellow]Container {container_name} not found, starting it...[/yellow]")
            self.up_service(name)

    def up_all(self, build: bool = False) -> None:
        """Start all services."""
        services = self.list_services()

        console.print(f"[cyan]Starting {len(services)} services...[/cyan]")
        for name in services:
            try:
                self.up_service(name, build=build)
            except Exception as e:
                console.print(f"[red]Failed to start {name}: {e}[/red]")

    def down_all(self, volumes: bool = False) -> None:
        """Stop all services."""
        containers = self.docker.list_brand_containers()

        console.print(f"[cyan]Stopping {len(containers)} containers...[/cyan]")
        for container in containers:
            try:
                service_name = container.get("labels", {}).get(
                    "com.docker.compose.service", container.get("service")
                )
                if not service_name and container.get("name"):
                    prefix = f"{self.brand.container_prefix}-"
                    if container["name"].startswith(prefix):
                        service_name = container["name"][len(prefix) :]
                if service_name:
                    self.down_service(service_name, volumes=volumes)
                else:
                    console.print(
                        f"[yellow]Skipping container {container.get('name')} - service name unknown[/yellow]"
                    )
            except Exception as e:
                console.print(f"[red]Failed to stop {container.get('name')}: {e}[/red]")

    def ps(self) -> None:
        """Show status of all Fenix containers."""
        statuses = self.docker.get_all_brand_status()

        if not statuses:
            console.print("[yellow]No Fenix containers found[/yellow]")
            return

        table = Table(title="Fenix Services")
        table.add_column("Service", style="cyan")
        table.add_column("Container", style="blue")
        table.add_column("Status", style="green")
        table.add_column("Health")
        table.add_column("Ports")
        table.add_column("OrbiStack Domain", style="magenta")

        for status in statuses:
            if not status.get("exists"):
                continue

            # Format status
            running = status.get("running", False)
            container_status = status.get("status", "unknown")
            if running:
                status_str = f"[green]✓ {container_status}[/green]"
            else:
                status_str = f"[red]✗ {container_status}[/red]"

            # Format health
            health = status.get("health", "none")
            if health == "healthy":
                health_str = "[green]✓ healthy[/green]"
            elif health == "unhealthy":
                health_str = "[red]✗ unhealthy[/red]"
            elif health == "starting":
                health_str = "[yellow]⟳ starting[/yellow]"
            else:
                health_str = "[dim]n/a[/dim]"

            # Format ports
            ports = status.get("ports", {})
            port_list = []
            for container_port, host_port in ports.items():
                port_list.append(f"{host_port}→{container_port}")
            ports_str = ", ".join(port_list) if port_list else "-"

            # Get OrbiStack domain
            domain = status.get("orbstack_domain", "-")

            # Get service name from container name
            container_name = status.get("name", "")
            service_name = status.get("service")
            if not service_name and container_name:
                prefix = f"{self.brand.container_prefix}-"
                service_name = (
                    container_name[len(prefix) :]
                    if container_name.startswith(prefix)
                    else container_name
                )

            table.add_row(
                service_name,
                container_name,
                status_str,
                health_str,
                ports_str,
                domain,
            )

        console.print(table)

    def logs(self, name: str, tail: int = 100, follow: bool = False) -> None:
        """Show logs for a service."""
        container_name = f"{self.brand.container_prefix}-{name}"

        try:
            for line in self.docker.get_container_logs(container_name, tail=tail, follow=follow):
                console.print(line)
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopped following logs[/yellow]")
        except Exception as e:
            console.print(f"[red]Error getting logs: {e}[/red]")

    def exec(self, name: str, command: list[str]) -> None:
        """Execute a command in a service container."""
        container_name = f"{self.brand.container_prefix}-{name}"

        try:
            # Check if it's an interactive command
            if command and command[0] in ["bash", "sh", "/bin/bash", "/bin/sh"]:
                # Use subprocess for interactive shells
                subprocess.run(["docker", "exec", "-it", container_name] + command)
            else:
                # Use Docker API for non-interactive commands
                output = self.docker.exec_in_container(container_name, command)
                console.print(output)
        except Exception as e:
            console.print(f"[red]Error executing command: {e}[/red]")

    def build(self, name: str) -> None:
        """Build a service image."""
        definition = self.get_service_definition(name)
        if not definition:
            raise ValueError(f"Service {name} not found")

        if not definition.build:
            raise ValueError(f"Service {name} has no build configuration")

        config = ServiceConfig.from_definition(definition)

        if isinstance(config.build, str):
            build_path = config.build
            dockerfile = None
        else:
            build_path = config.build.get("context", ".")
            dockerfile = config.build.get("dockerfile")

        tag = f"{self.brand.cli_name}/{name}:latest"
        console.print(f"[cyan]Building {tag} from {build_path}...[/cyan]")

        image_id, logs = self.docker.build_image(build_path, tag, dockerfile)

        # Print build logs
        for log in logs:
            if log:
                console.print(log)

        console.print(f"[green]Successfully built {tag} ({image_id[:12]})[/green]")

    def cleanup(self) -> None:
        """Clean up unused Docker resources."""
        console.print("[cyan]Cleaning up unused Fenix resources...[/cyan]")
        results = self.docker.cleanup_unused()

        console.print(f"[green]Removed {results['containers_removed']} containers[/green]")
        console.print(f"[green]Removed {results['volumes_removed']} volumes[/green]")
        console.print(f"[green]Removed {results['networks_removed']} networks[/green]")
        console.print(
            f"[green]Space reclaimed: {results['space_reclaimed'] / 1024 / 1024:.2f} MB[/green]"
        )
