"""Docker build management commands."""

import subprocess

import typer
from rich.table import Table

from ..branding import get_brand
from ..services import ServiceManager
from ..utils.common import HAS_DOCKER, command_exists, console

brand = get_brand()

app = typer.Typer(
    name="builds",
    help=f"Manage Docker image builds for {brand.cli_display_name}",
    no_args_is_help=True,
)


def _ensure_docker() -> None:
    """Abort if Docker is not available."""
    if not HAS_DOCKER:
        console.print("[red]Docker is not installed or not in PATH[/red]")
        raise typer.Exit(1)


@app.command("list")
def list_builds():
    """List services that have a build configuration."""
    _ensure_docker()

    try:
        manager = ServiceManager()
        services = manager.list_services()

        if not services:
            console.print("[yellow]No services found[/yellow]")
            return

        table = Table(title="Buildable Services")
        table.add_column("Service", style="cyan")
        table.add_column("Build Context", style="green")
        table.add_column("Dockerfile", style="dim")
        table.add_column("Source")

        found = False
        for name, source in services.items():
            definition = manager.get_service_definition(name)
            if not definition or not definition.build:
                continue

            found = True

            if isinstance(definition.build, str):
                context = definition.build
                dockerfile = "Dockerfile"
            else:
                context = definition.build.get("context", ".")
                dockerfile = definition.build.get("dockerfile", "Dockerfile")

            table.add_row(name, context, dockerfile, source)

        if not found:
            console.print("[yellow]No services with build configurations found[/yellow]")
            return

        console.print(table)
    except Exception as e:
        console.print(f"[red]Failed to list buildable services: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def build(
    name: str = typer.Argument(..., help="Service name to build"),
    platform: str | None = typer.Option(
        None, "--platform", help="Target platform (e.g. linux/amd64,linux/arm64)"
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="Build without cache"),
):
    """Build a Docker image for a service."""
    _ensure_docker()

    try:
        manager = ServiceManager()
        definition = manager.get_service_definition(name)

        if not definition:
            console.print(f"[red]Service '{name}' not found[/red]")
            raise typer.Exit(1)

        if not definition.build:
            console.print(f"[red]Service '{name}' has no build configuration[/red]")
            raise typer.Exit(1)

        if isinstance(definition.build, str):
            context = definition.build
            dockerfile = None
        else:
            context = definition.build.get("context", ".")
            dockerfile = definition.build.get("dockerfile")

        tag = f"{brand.cli_name}/{name}:latest"

        if platform:
            # Use docker buildx for multi-platform builds
            if not command_exists("docker"):
                console.print("[red]docker buildx is required for multi-platform builds[/red]")
                raise typer.Exit(1)

            console.print(f"[cyan]Building {tag} for platform {platform} from {context}...[/cyan]")
            cmd = ["docker", "buildx", "build", "--platform", platform, "-t", tag]
            if dockerfile:
                cmd.extend(["-f", dockerfile])
            if no_cache:
                cmd.append("--no-cache")
            cmd.append(context)

            result = subprocess.run(cmd, text=True)
            if result.returncode != 0:
                console.print(f"[red]Build failed for {name}[/red]")
                raise typer.Exit(1)
        else:
            console.print(f"[cyan]Building {tag} from {context}...[/cyan]")
            cmd = ["docker", "build", "-t", tag]
            if dockerfile:
                cmd.extend(["-f", dockerfile])
            if no_cache:
                cmd.append("--no-cache")
            cmd.append(context)

            result = subprocess.run(cmd, text=True)
            if result.returncode != 0:
                console.print(f"[red]Build failed for {name}[/red]")
                raise typer.Exit(1)

        console.print(f"[green]Successfully built {tag}[/green]")
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Failed to build {name}: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def push(
    name: str = typer.Argument(..., help="Service name whose image to push"),
    registry: str = typer.Option(
        "", "--registry", "-r", help="Registry to push to (e.g. ghcr.io/fenixflow)"
    ),
    tag: str | None = typer.Option(None, "--tag", "-t", help="Image tag (default: latest)"),
):
    """Push a built Docker image to a registry."""
    _ensure_docker()

    try:
        image_tag = tag or "latest"
        local_image = f"{brand.cli_name}/{name}:{image_tag}"

        if registry:
            remote_image = f"{registry}/{name}:{image_tag}"
        else:
            remote_image = local_image

        # Tag the image for the remote registry if needed
        if remote_image != local_image:
            console.print(f"[cyan]Tagging {local_image} as {remote_image}...[/cyan]")
            result = subprocess.run(
                ["docker", "tag", local_image, remote_image],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                console.print(f"[red]Failed to tag image: {result.stderr}[/red]")
                raise typer.Exit(1)

        console.print(f"[cyan]Pushing {remote_image}...[/cyan]")
        result = subprocess.run(
            ["docker", "push", remote_image],
            text=True,
        )
        if result.returncode != 0:
            console.print(f"[red]Failed to push {remote_image}[/red]")
            raise typer.Exit(1)

        console.print(f"[green]Successfully pushed {remote_image}[/green]")
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Failed to push {name}: {e}[/red]")
        raise typer.Exit(1) from e
