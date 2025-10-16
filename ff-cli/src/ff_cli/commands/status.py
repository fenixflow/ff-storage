"""Unified status command for the branded CLI."""

import json
from typing import Any

import typer
from rich.table import Table

from ..branding import get_brand
from ..plugin_base import (
    aggregate_health,
    format_health_indicator,
    generate_recommendations,
    get_plugin_status,
)
from ..plugin_manager import PluginManager
from ..utils.common import console
from ..utils.docker import DockerManager

app = typer.Typer()


def get_docker_status() -> dict[str, Any]:
    """Get Docker and network status."""
    brand = get_brand()
    try:
        docker = DockerManager()
        docker_info = docker.get_docker_info()
        network_status = docker.get_network_status(brand.docker_network)

        return {
            "docker": docker_info,
            "network": network_status,
        }
    except Exception as e:
        return {
            "docker": {"running": False, "error": str(e)},
            "network": {"exists": False},
        }


def get_service_statuses() -> list[dict[str, Any]]:
    """Get status of all Docker services."""
    brand = get_brand()
    container_prefix = f"{brand.container_prefix}-"
    try:
        # Get service manager to access service definitions
        from ..services import ServiceManager

        service_manager = ServiceManager()

        # Get all defined services
        defined_services = service_manager.list_services()

        # Get Docker status for running containers
        docker = DockerManager()
        running_statuses = docker.get_all_brand_status()
        # adjust to brand-specific method once DockerManager updated

        # Create a map of running containers
        running_map = {}
        for status in running_statuses:
            if status.get("exists"):
                container_name = status.get("name", "")
                if status.get("service"):
                    service_name = status["service"]
                elif container_name.startswith(container_prefix):
                    service_name = container_name[len(container_prefix) :]
                else:
                    service_name = container_name
                running_map[service_name] = status

        # Build comprehensive service list
        service_list = []
        all_healthy = True
        critical_services = ["postgres"]  # Only critical services affect overall health

        # Process all defined services
        for service_name in sorted(defined_services.keys()):
            # Get service definition to get configured ports
            definition = service_manager.get_service_definition(service_name)

            # Check if container is running
            if service_name in running_map:
                # Service is running - use actual status
                status = running_map[service_name]
                running = status.get("running", False)
                health = status.get("health", "none")

                # Determine health status
                if not running:
                    health_status = "stopped"
                    # Only mark unhealthy if this is a critical service
                    if service_name in critical_services:
                        all_healthy = False
                elif health == "healthy":
                    health_status = "healthy"
                elif health == "unhealthy":
                    health_status = "unhealthy"
                    # Only mark unhealthy if this is a critical service
                    if service_name in critical_services:
                        all_healthy = False
                elif health == "starting":
                    health_status = "starting"
                    # Only mark unhealthy if this is a critical service
                    if service_name in critical_services:
                        all_healthy = False
                else:
                    health_status = "running"  # No healthcheck

                # Get actual ports
                ports = status.get("ports", {})
                port_list = []
                for container_port, host_port in ports.items():
                    port_list.append(f"{host_port}→{container_port}")

                container_status = status.get("status", "unknown")
                orbstack_domain = status.get("orbstack_domain", "")

                # Check for web URL
                url = ""
                if ports:
                    for container_port, host_port in ports.items():
                        if any(
                            p in container_port
                            for p in ["80/tcp", "8080/tcp", "3000/tcp", "8000/tcp"]
                        ):
                            url = f"http://localhost:{host_port}"
                            break
            else:
                # Service is defined but not running
                running = False
                health_status = "not_created"
                container_status = "Not created"
                # Only mark unhealthy if this is a critical service
                if service_name in critical_services:
                    all_healthy = False
                port_list = []
                url = ""

                # Get configured ports from definition
                if definition and definition.ports:
                    # Show configured ports (what will be used when started)
                    port_list = [f"{p} (configured)" for p in definition.ports]

                # Build OrbStack domain from service name
                orbstack_domain = f"{service_name}.{brand.orbstack_domain_suffix}"

            service_info = {
                "name": service_name,
                "running": running,
                "health": health_status,
                "status": container_status,
                "ports": port_list,
                "orbstack_domain": orbstack_domain,
                "exists": service_name in running_map,
                "url": url,
            }

            service_list.append(service_info)

        # Count running and stopped
        running_count = len([s for s in service_list if s["running"]])
        stopped_count = len([s for s in service_list if not s["exists"]])

        return [
            {
                "name": "Core Services",
                "healthy": all_healthy,
                "services": service_list,
                "message": f"{running_count} running, {stopped_count} stopped",
            }
        ]
    except Exception as e:
        return [
            {
                "name": "Core Services",
                "healthy": False,
                "services": [],
                "message": "Failed to get service status",
                "errors": [str(e)],
            }
        ]


def get_plugin_statuses(verbose: bool = False) -> list[dict[str, Any]]:
    """Get status from all plugins that support it."""
    statuses = []

    try:
        manager = PluginManager()
        for plugin_name, plugin in manager.plugins.items():
            try:
                plugin_app = plugin.load()
                if plugin_app:
                    status = get_plugin_status(plugin_app, verbose=verbose)
                    if status:
                        # Ensure plugin name is in status
                        if "name" not in status:
                            status["name"] = f"Plugin: {plugin_name}"
                        statuses.append(status)
            except Exception as e:
                # Add error status for failed plugin
                statuses.append(
                    {
                        "name": f"Plugin: {plugin_name}",
                        "healthy": False,
                        "services": [],
                        "message": "Failed to load plugin",
                        "errors": [str(e)],
                    }
                )
    except Exception:
        # Silently skip if plugin system fails
        pass

    return statuses


def display_core_services_table(services: list[dict[str, Any]], title: str, message: str):
    """Display core services in a formatted table."""
    if not services:
        return

    # Create table header
    brand = get_brand()
    console.print(f"\n[bold]{brand.icon} {title}[/bold] ({message})")
    console.print("─" * 80)

    # Create Rich table
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("SERVICE", style="cyan", width=12)
    table.add_column("STATUS", width=18)
    table.add_column("PORTS", width=25)
    table.add_column("OrbStack Domain", style="magenta")

    # Add service rows
    for service in services:
        # Format status
        if not service.get("exists", False):
            status_str = "○ Not created"
            status_style = "dim"
        elif service.get("running"):
            container_status = service.get("status", "Running")
            health = service.get("health", "")
            if health == "healthy":
                status_str = f"✅ {container_status}"
                status_style = "green"
            elif health == "unhealthy":
                status_str = "❌ Unhealthy"
                status_style = "red"
            elif health == "starting":
                status_str = "⟳ Starting"
                status_style = "yellow"
            else:
                status_str = f"✅ {container_status}"
                status_style = "green"
        else:
            status_str = "○ Stopped"
            status_style = "red"

        # Format ports
        ports = service.get("ports", [])
        if ports:
            # Show all ports for clarity
            if "(configured)" in ports[0]:
                port_str = ports[0] if len(ports) == 1 else f"{len(ports)} ports (configured)"
            else:
                port_str = ", ".join(ports[:2])
                if len(ports) > 2:
                    port_str += f" +{len(ports) - 2}"
        else:
            port_str = "-"

        # Format domain
        domain = service.get("orbstack_domain", "")
        if not domain or domain == "-":
            domain = "-"

        # Add row to table
        name = service.get("name", "Unknown")
        table.add_row(name, f"[{status_style}]{status_str}[/{status_style}]", port_str, domain)

    console.print(table)


@app.command()
def status(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    services_only: bool = typer.Option(False, "--services", help="Show only Docker services"),
    plugins_only: bool = typer.Option(False, "--plugins", help="Show only plugin statuses"),
):
    """Show unified status of core services and plugins."""
    # Gather all status information
    system_status = get_docker_status()
    service_statuses = [] if plugins_only else get_service_statuses()
    plugin_statuses = [] if services_only else get_plugin_statuses(verbose=verbose)

    # Combine all statuses
    all_statuses = service_statuses + plugin_statuses

    # Calculate overall health
    overall_health = aggregate_health(all_statuses)

    # Generate recommendations
    recommendations = generate_recommendations(all_statuses, system_status["docker"])

    if json_output:
        # Output as JSON
        output = {
            "system": system_status,
            "services": service_statuses,
            "plugins": plugin_statuses,
            "overall_health": overall_health,
            "recommendations": recommendations,
        }
        console.print(json.dumps(output, indent=2))
    else:
        # Display formatted output
        brand = get_brand()

        console.print(
            f"\n[bold cyan]{brand.icon} {brand.cli_display_name} System Status[/bold cyan]"
        )
        console.print("=" * 40)

        # Docker status
        docker_info = system_status["docker"]
        if docker_info.get("running"):
            version = docker_info.get("version", "unknown")
            if docker_info.get("orbstack"):
                console.print(f"🔮 OrbStack: [green]✅ Running[/green] v{version}")
            else:
                console.print(f"🐳 Docker: [green]✅ Running[/green] v{version}")
        else:
            console.print("🐳 Docker: [red]❌ Not running[/red]")
            error = docker_info.get("error", "")
            if error:
                console.print(f"   Error: {error}")

        # Network status
        network = system_status["network"]
        if network.get("exists"):
            connected = network.get("connected_containers", 0)
            console.print(
                f"🌐 Network: {brand.docker_network} [green]✅[/green] ({connected} connected)"
            )
        else:
            console.print(f"🌐 Network: {brand.docker_network} [red]❌ Not found[/red]")

        console.print()

        # Core services
        if service_statuses and not plugins_only:
            for status in service_statuses:
                if status.get("services"):
                    display_core_services_table(
                        status.get("services", []), "Core Services", status.get("message", "")
                    )

        # Plugin statuses
        if plugin_statuses and not services_only:
            console.print()
            for status in plugin_statuses:
                name = status.get("name", "Unknown Plugin")
                healthy = status.get("healthy", False)
                services = status.get("services", [])

                if services:
                    # Display plugin services in table format similar to core services
                    running_count = len([s for s in services if s.get("running", False)])
                    total_count = len(services)
                    message = f"{running_count}/{total_count} running"

                    console.print(f"\n[bold]{name}[/bold] ({message})")
                    console.print("─" * 60)

                    # Print plugin services in simplified format
                    for service in services:
                        service_name = service.get("name", "Unknown")
                        running = service.get("running", False)
                        url = service.get("url", "")
                        health = service.get("health", "")

                        if running:
                            if health == "healthy":
                                status_icon = "✅"
                            elif health == "unhealthy":
                                status_icon = "❌"
                            else:
                                status_icon = "✅"
                        else:
                            status_icon = "○"

                        if url:
                            console.print(f"  {status_icon} {service_name:<20} {url}")
                        else:
                            console.print(f"  {status_icon} {service_name}")
                else:
                    # No services, just show status message
                    health_icon = "✅" if healthy else "⚠️"
                    console.print(
                        f"\n[bold]{name}[/bold] ({health_icon} {'Healthy' if healthy else 'Issues'})"
                    )
                    console.print("─" * 60)
                    console.print(f"  {status.get('message', 'No services')}")

                # Show errors/warnings in verbose mode
                if verbose:
                    if status.get("errors"):
                        console.print("  [red]Errors:[/red]")
                        for error in status["errors"]:
                            console.print(f"    • {error}")
                    if status.get("warnings"):
                        console.print("  [yellow]Warnings:[/yellow]")
                        for warning in status["warnings"]:
                            console.print(f"    • {warning}")
                    if status.get("metrics"):
                        console.print("  [cyan]Metrics:[/cyan]")
                        for key, value in status["metrics"].items():
                            console.print(f"    • {key}: {value}")

        # Overall health
        console.print()
        console.print(f"[bold]System Health:[/bold] {format_health_indicator(overall_health)}")

        # Recommendations
        if recommendations and overall_health != "HEALTHY":
            console.print("─" * 40)
            console.print("[yellow]Recommendations:[/yellow]")
            for rec in recommendations:
                console.print(f"  • {rec}")


__all__ = ["status", "app"]
