"""Service management commands for the branded CLI."""

import subprocess
from pathlib import Path

import typer
from rich.table import Table

from ..branding import get_brand
from ..services import ServiceManager
from ..utils.common import console
from ..utils.docker import DockerManager

brand = get_brand()

app = typer.Typer(
    name="services",
    help=f"Manage Docker services for {brand.cli_display_name}",
    no_args_is_help=True,
)


@app.command()
def init():
    """Initialize the brand-specific configuration directory and network."""
    try:
        manager = ServiceManager()
        manager.initialize()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("list")
def list_services():
    """List all available service definitions."""
    try:
        manager = ServiceManager()
        services = manager.list_services()

        if not services:
            console.print("[yellow]No services found[/yellow]")
            console.print("Add service definitions to:")
            console.print(f"  - {manager.user_services_path}")
            console.print(f"  - {manager.repo_services_path}")
            return

        table = Table(title="Available Services")
        table.add_column("Service", style="cyan")
        table.add_column("Source", style="green")
        table.add_column("Path")

        source_labels = {
            "user": "✓ user",
            "default": "default",
            "plugin": "plugin",
        }

        for name, source in services.items():
            path = manager.which_service(name)
            display_path = path.replace(str(Path.home()), "~") if path else ""
            table.add_row(
                name,
                source_labels.get(source, source),
                display_path,
            )

        console.print(table)
    except Exception as e:
        console.print(f"[red]Failed to list services: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def up(
    service: str | None = typer.Argument(None, help="Service name to start"),
    all: bool = typer.Option(False, "--all", help="Start all services"),
    build: bool = typer.Option(False, "--build", help="Build images before starting"),
):
    """Start service(s)."""
    try:
        manager = ServiceManager()

        if all:
            manager.up_all(build=build)
        elif service:
            manager.up_service(service, build=build)
        else:
            console.print("[yellow]Specify a service name or use --all[/yellow]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Failed to start: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def down(
    service: str | None = typer.Argument(None, help="Service name to stop"),
    all: bool = typer.Option(False, "--all", help="Stop all services"),
    volumes: bool = typer.Option(
        False,
        "--volumes",
        help="Retained for compatibility; volumes remain intact",
    ),
):
    """Stop and remove service(s)."""
    try:
        manager = ServiceManager()

        if all:
            manager.down_all(volumes=volumes)
        elif service:
            manager.down_service(service, volumes=volumes)
        else:
            console.print("[yellow]Specify a service name or use --all[/yellow]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Failed to stop: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def restart(
    service: str = typer.Argument(..., help="Service name to restart"),
):
    """Restart a service."""
    try:
        manager = ServiceManager()
        manager.restart_service(service)
    except Exception as e:
        console.print(f"[red]Failed to restart {service}: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def ps():
    """Show status of all Fenix containers."""
    try:
        manager = ServiceManager()
        manager.ps()
    except Exception as e:
        console.print(f"[red]Failed to show status: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def logs(
    service: str = typer.Argument(..., help="Service name"),
    follow: bool = typer.Option(False, "-f", "--follow", help="Follow log output"),
    tail: int = typer.Option(100, "-n", "--tail", help="Number of lines to show"),
):
    """View service logs."""
    try:
        manager = ServiceManager()
        manager.logs(service, tail=tail, follow=follow)
    except Exception as e:
        console.print(f"[red]Failed to get logs for {service}: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("exec")
def execute(
    service: str = typer.Argument(..., help="Service name"),
    command: list[str] = typer.Argument(..., help="Command to execute"),
):
    """Execute a command in a service container."""
    try:
        manager = ServiceManager()
        manager.exec(service, command)
    except Exception as e:
        console.print(f"[red]Failed to execute command in {service}: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def build(
    service: str = typer.Argument(..., help="Service name to build"),
):
    """Build a service image from Dockerfile."""
    try:
        manager = ServiceManager()
        manager.build(service)
    except Exception as e:
        console.print(f"[red]Failed to build {service}: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def edit(
    service: str = typer.Argument(..., help="Service name to edit"),
):
    """Open service definition in editor."""
    try:
        manager = ServiceManager()
        manager.edit_service(service)
    except Exception as e:
        console.print(f"[red]Failed to edit {service}: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def new(
    name: str = typer.Argument(..., help="New service name"),
    template: str | None = typer.Option(None, "--template", help="Base on existing service"),
):
    """Create a new service definition."""
    try:
        manager = ServiceManager()
        path = manager.create_service(name, template=template)
        brand = get_brand()
        console.print(f"[green]Created service definition: {path}[/green]")
        console.print(f"Edit with: {brand.cli_name} services edit {name}")
    except Exception as e:
        console.print(f"[red]Failed to create {name}: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def which(
    service: str = typer.Argument(..., help="Service name"),
):
    """Show which configuration file is being used."""
    try:
        manager = ServiceManager()
        path = manager.which_service(service)
        if path:
            console.print(f"[cyan]{service}[/cyan] uses: {path}")
        else:
            console.print(f"[red]Service {service} not found[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Failed to show configuration for {service}: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def copy(
    source: str = typer.Argument(..., help="Source service name"),
    target: str = typer.Argument(..., help="Target service name"),
):
    """Copy a service definition to a new name."""
    try:
        manager = ServiceManager()
        path = manager.copy_service(source, target)
        brand = get_brand()
        console.print(f"[green]Copied {source} to {target}[/green]")
        console.print(f"[green]Created: {path}[/green]")
        console.print(f"Edit with: {brand.cli_name} services edit {target}")
    except Exception as e:
        console.print(f"[red]Failed to copy: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def cleanup():
    """Clean up unused Docker resources."""
    try:
        manager = ServiceManager()
        manager.cleanup()
    except Exception as e:
        console.print(f"[red]Failed to cleanup: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def prune():
    """Remove containers with brand labels that don't match any known service definition."""
    try:
        manager = ServiceManager()
        docker = DockerManager()
        brand = get_brand()

        known_services = set(manager.list_services().keys())
        brand_containers = docker.get_all_brand_status()

        if not brand_containers:
            console.print("[yellow]No brand containers found[/yellow]")
            return

        orphans: list[dict] = []
        for container in brand_containers:
            labels = container.get("labels", {})
            service_name = labels.get("com.docker.compose.service", "")
            container_name = container.get("name", "")

            # Derive service name from container name if label is missing
            if not service_name and container_name:
                prefix = f"{brand.container_prefix}-"
                if container_name.startswith(prefix):
                    service_name = container_name[len(prefix) :]

            if service_name not in known_services:
                orphans.append(container)

        if not orphans:
            console.print("[green]No orphaned containers found[/green]")
            return

        console.print(f"[cyan]Found {len(orphans)} orphaned container(s)[/cyan]")
        removed = 0
        for container in orphans:
            name = container.get("name", "unknown")
            console.print(f"  Removing [yellow]{name}[/yellow]...")
            if docker.remove_container(name, force=True):
                removed += 1
                console.print(f"  [green]Removed {name}[/green]")
            else:
                console.print(f"  [red]Failed to remove {name}[/red]")

        console.print(f"[green]Pruned {removed}/{len(orphans)} orphaned containers[/green]")
    except Exception as e:
        console.print(f"[red]Failed to prune: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def reset(
    service: str = typer.Argument(..., help="Service name to reset"),
    nuke: bool = typer.Option(False, "--nuke", help="Also remove associated volumes"),
):
    """Stop a service container, remove its image, and re-pull it."""
    try:
        manager = ServiceManager()
        docker = DockerManager()
        brand = get_brand()

        definition = manager.get_service_definition(service)
        if not definition:
            console.print(f"[red]Service {service} not found[/red]")
            raise typer.Exit(1)

        container_name = f"{brand.container_prefix}-{service}"
        image = definition.image

        # Stop the container if it exists
        if docker.container_exists(container_name):
            console.print(f"[cyan]Stopping {container_name}...[/cyan]")
            docker.stop_container(container_name)
            docker.remove_container(container_name, force=True)
            console.print(f"[green]Removed container {container_name}[/green]")

        # Remove associated volumes if --nuke
        if nuke and definition.volumes:
            for volume_spec in definition.volumes:
                if ":" in volume_spec:
                    volume_name = volume_spec.split(":")[0]
                    if not volume_name.startswith("/"):
                        console.print(f"[cyan]Removing volume {volume_name}...[/cyan]")
                        result = subprocess.run(
                            ["docker", "volume", "rm", "-f", volume_name],
                            capture_output=True,
                            text=True,
                        )
                        if result.returncode == 0:
                            console.print(f"[green]Removed volume {volume_name}[/green]")
                        else:
                            console.print(f"[yellow]Could not remove volume {volume_name}[/yellow]")

        # Remove the image
        console.print(f"[cyan]Removing image {image}...[/cyan]")
        result = subprocess.run(
            ["docker", "rmi", "-f", image],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print(f"[green]Removed image {image}[/green]")
        else:
            console.print(
                f"[yellow]Could not remove image {image} (may not exist locally)[/yellow]"
            )

        # Re-pull the image
        if docker.pull_image(image):
            console.print(f"[green]Successfully reset {service}[/green]")
        else:
            console.print(f"[red]Failed to pull image {image}[/red]")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Failed to reset {service}: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def remove(
    service: str = typer.Argument(..., help="Service name to remove"),
):
    """Delete the user service definition YAML file."""
    try:
        manager = ServiceManager()
        user_file = manager.user_services_path / f"{service}.yaml"

        if not user_file.exists():
            console.print(f"[red]No user service definition found for {service}[/red]")
            console.print(f"[dim]Expected at: {user_file}[/dim]")
            raise typer.Exit(1)

        user_file.unlink()
        console.print(f"[green]Removed service definition: {user_file}[/green]")
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Failed to remove {service}: {e}[/red]")
        raise typer.Exit(1) from e
