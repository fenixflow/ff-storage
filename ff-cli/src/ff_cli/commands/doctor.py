"""Doctor command for diagnosing CLI and plugin issues."""

import json
import sys
from pathlib import Path
from typing import Any

import typer
from rich.table import Table

from ff_cli import __version__, plugin_registry
from ff_cli.branding import get_brand
from ff_cli.plugin_manager import PluginManager
from ff_cli.utils.common import HAS_UV, console
from ff_cli.utils.docker import DockerManager

app = typer.Typer()


def check_docker() -> tuple[bool, str, list[str]]:
    """Check Docker/OrbStack installation and status.

    Returns:
        Tuple of (is_healthy, status_message, recommendations)
    """
    recommendations = []
    try:
        docker = DockerManager()
        info = docker.get_docker_info()

        if not info.get("running"):
            return (
                False,
                "Docker not running",
                ["Start Docker Desktop or OrbStack", "Run: open -a Docker or open -a OrbStack"],
            )

        version = info.get("version", "unknown")
        if info.get("orbstack"):
            status = f"OrbStack v{version}"
        else:
            status = f"Docker v{version}"

        return True, status, recommendations
    except Exception as e:
        return (
            False,
            f"Docker error: {e}",
            [
                "Install Docker Desktop from https://docker.com",
                "Or install OrbStack from https://orbstack.dev (recommended for macOS)",
            ],
        )


def check_network() -> tuple[bool, str, list[str]]:
    """Check if the branded Docker network exists.

    Returns:
        Tuple of (is_healthy, status_message, recommendations)
    """
    brand = get_brand()
    recommendations = []

    try:
        docker = DockerManager()
        network = docker.get_network_status(brand.docker_network)

        if not network.get("exists"):
            return (
                False,
                f"Network '{brand.docker_network}' not found",
                [
                    f"Create network: docker network create {brand.docker_network}",
                    f"Or run: {brand.cli_name} services init",
                ],
            )

        containers = network.get("connected_containers", 0)
        return True, f"Network '{brand.docker_network}' ({containers} containers)", recommendations
    except Exception as e:
        return (
            False,
            f"Network check failed: {e}",
            ["Ensure Docker is running", f"Try: {brand.cli_name} services init"],
        )


def check_cli_installation() -> tuple[bool, str, list[str]]:
    """Check CLI installation and configuration.

    Returns:
        Tuple of (is_healthy, status_message, recommendations)
    """
    brand = get_brand()
    recommendations = []

    # Check version
    status_parts = [f"v{__version__}"]

    # Check config directory
    config_dir = Path.home() / f".{brand.cli_name}"
    if not config_dir.exists():
        recommendations.append(f"Config directory missing, run: {brand.cli_name} services init")

    # Check if running in editable mode (development)
    try:
        import ff_cli

        cli_path = Path(ff_cli.__file__).parent
        if "site-packages" not in str(cli_path):
            status_parts.append("(editable)")
    except Exception:
        pass

    # Check for UV
    if HAS_UV:
        status_parts.append("uv✓")
    else:
        recommendations.append("Install uv for faster operations: pip install uv")

    is_healthy = len(recommendations) == 0
    return is_healthy, " ".join(status_parts), recommendations


def check_plugins() -> tuple[bool, list[dict[str, Any]], list[str]]:
    """Check all registered plugins for issues.

    Returns:
        Tuple of (all_healthy, plugin_statuses, recommendations)
    """
    brand = get_brand()
    recommendations = []
    plugin_statuses = []
    all_healthy = True

    # Get registered plugins
    registered = plugin_registry.list_installed_plugins()

    # Get loaded plugins
    try:
        manager = PluginManager()
        loaded_plugins = set(manager.plugins.keys())
    except Exception as e:
        loaded_plugins = set()
        recommendations.append(f"Plugin system error: {e}")
        all_healthy = False

    for name, info in registered.items():
        status = {"name": name, "source": info.get("source_path", "unknown"), "issues": []}

        # Check source path
        source_path = info.get("source_path")
        if source_path:
            if not Path(source_path).exists():
                status["issues"].append("Source path missing")
                recommendations.append(f"Reinstall {name}: {brand.cli_name} plugins remove {name}")
                all_healthy = False
        else:
            status["issues"].append("No source path")
            all_healthy = False

        # Check if loaded
        if name not in loaded_plugins:
            status["issues"].append("Failed to load")

            # Try to diagnose why
            try:
                package_name = info.get("package_name", name)
                from importlib import metadata

                metadata.distribution(package_name)
                # Package exists but didn't load via entry points
                status["issues"].append("Entry point issue")
                recommendations.append(
                    f"Reinstall {name}: {brand.cli_name} plugins install {source_path}"
                )
            except metadata.PackageNotFoundError:
                status["issues"].append("Package not installed")
                if source_path and Path(source_path).exists():
                    recommendations.append(
                        f"Install {name}: {brand.cli_name} plugins install {source_path}"
                    )
                else:
                    recommendations.append(f"Remove {name}: {brand.cli_name} plugins remove {name}")
            all_healthy = False
        else:
            # Plugin loaded, try to get its status
            try:
                plugin = manager.get_plugin(name)
                if plugin:
                    plugin_app = plugin.load()
                    if plugin_app:
                        # Successfully loaded
                        status["issues"] = []  # Clear any issues
                    else:
                        status["issues"].append("Empty plugin")
                        all_healthy = False
            except Exception as e:
                status["issues"].append(f"Load error: {e}")
                recommendations.append(f"Check {name} plugin code for errors")
                all_healthy = False

        plugin_statuses.append(status)

    # Check for loaded plugins not in registry
    if loaded_plugins:
        for name in loaded_plugins:
            if name not in registered:
                plugin_statuses.append(
                    {"name": name, "source": "unknown", "issues": ["Not in registry"]}
                )
                recommendations.append(f"Register {name} or remove from Python environment")

    return all_healthy, plugin_statuses, recommendations


def check_python_environment() -> tuple[bool, str, list[str]]:
    """Check Python environment and dependencies.

    Returns:
        Tuple of (is_healthy, status_message, recommendations)
    """
    recommendations = []

    # Get Python version
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    status_parts = [f"Python {python_version}"]

    # Check Python version requirement
    is_healthy = True

    # Check virtual environment
    if hasattr(sys, "prefix") and sys.prefix != sys.base_prefix:
        venv_name = Path(sys.prefix).name
        status_parts.append(f"(venv: {venv_name})")

    return is_healthy, " ".join(status_parts), recommendations


def _needs_registry_cleanup(plugin_statuses: list[dict[str, Any]]) -> bool:
    """Determine if plugin registry cleanup is warranted."""

    cleanup_triggers = ("Source path missing", "Package not installed", "No source path")

    for status in plugin_statuses:
        issues = status.get("issues", []) or []
        for issue in issues:
            if isinstance(issue, str) and any(trigger in issue for trigger in cleanup_triggers):
                return True

    return False


def run_auto_fixes(fix_network: bool = False, clean_registry: bool = False) -> list[str]:
    """Run automatic fixes for common issues.

    Args:
        fix_network: Create missing Docker network
        clean_registry: Remove invalid plugin entries

    Returns:
        List of actions taken
    """
    brand = get_brand()
    actions = []

    if fix_network:
        try:
            docker = DockerManager()
            network = docker.get_network_status(brand.docker_network)
            if not network.get("exists"):
                created = docker.create_network(brand.docker_network)
                if created:
                    actions.append(f"Created Docker network: {brand.docker_network}")
                else:
                    actions.append(f"Failed to create network: {brand.docker_network}")
        except Exception as e:
            actions.append(f"Network fix failed: {e}")

    if clean_registry:
        try:
            removed = plugin_registry.clean_registry()
            if removed > 0:
                actions.append(f"Removed {removed} invalid plugin entries")
            else:
                actions.append("No invalid plugin entries found")
        except Exception as e:
            actions.append(f"Registry cleanup failed: {e}")

    return actions


@app.command()
def doctor(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
    auto_fix: bool = typer.Option(False, "--fix", help="Attempt to fix issues automatically"),
):
    """Run diagnostic checks on the CLI installation and plugins.

    Checks:
    - Docker/OrbStack status
    - Network configuration
    - CLI installation
    - Plugin health
    - Python environment
    """
    brand = get_brand()

    # Run all checks
    checks = {
        "docker": check_docker(),
        "network": check_network(),
        "cli": check_cli_installation(),
        "python": check_python_environment(),
    }

    plugins_healthy, plugin_statuses, plugin_recs = check_plugins()

    # Aggregate health
    all_healthy = all(check[0] for check in checks.values()) and plugins_healthy

    # Collect all recommendations
    all_recommendations = []
    for check_result in checks.values():
        all_recommendations.extend(check_result[2])
    all_recommendations.extend(plugin_recs)

    # Run auto-fixes if requested
    fix_actions = []
    if auto_fix:
        # Determine what to fix based on check results
        fix_network = not checks["network"][0]
        clean_registry = not plugins_healthy and _needs_registry_cleanup(plugin_statuses)
        fix_actions = run_auto_fixes(fix_network=fix_network, clean_registry=clean_registry)

        # Re-run checks after fixes
        if fix_actions:
            checks["network"] = check_network()
            plugins_healthy, plugin_statuses, plugin_recs = check_plugins()
            all_healthy = all(check[0] for check in checks.values()) and plugins_healthy
            all_recommendations = []
            for check_result in checks.values():
                all_recommendations.extend(check_result[2])
            all_recommendations.extend(plugin_recs)

    if json_output:
        # Output as JSON
        output = {
            "healthy": all_healthy,
            "checks": {
                name: {"healthy": result[0], "status": result[1], "recommendations": result[2]}
                for name, result in checks.items()
            },
            "plugins": {
                "healthy": plugins_healthy,
                "statuses": plugin_statuses,
                "recommendations": plugin_recs,
            },
            "recommendations": all_recommendations,
            "cli_version": __version__,
        }
        if fix_actions:
            output["fixes_applied"] = fix_actions
        console.print(json.dumps(output, indent=2))
    else:
        # Display formatted output
        console.print(f"\n[bold cyan]{brand.icon} {brand.cli_display_name} Doctor[/bold cyan]")
        console.print("=" * 50)

        # System checks table
        table = Table(show_header=True, header_style="bold", box=None)
        table.add_column("Component", style="cyan", width=15)
        table.add_column("Status", width=10)
        table.add_column("Details", style="dim")

        # Add rows for each check
        for name, (healthy, status, _) in checks.items():
            if name == "docker":
                component = "🐳 Docker"
            elif name == "network":
                component = "🌐 Network"
            elif name == "cli":
                component = f"{brand.icon} CLI"
            elif name == "python":
                component = "🐍 Python"
            else:
                component = name.title()

            status_icon = "✅" if healthy else "❌"
            table.add_row(component, status_icon, status)

        console.print(table)

        # Plugins section
        if plugin_statuses:
            console.print(f"\n[bold]Plugins ({len(plugin_statuses)}):[/bold]")
            for status in plugin_statuses:
                name = status["name"]
                issues = status.get("issues", [])
                if issues:
                    issue_str = ", ".join(issues)
                    console.print(f"  ❌ {name}: [red]{issue_str}[/red]")
                else:
                    console.print(f"  ✅ {name}")

                if verbose:
                    source = status.get("source", "unknown")
                    if source != "unknown" and len(source) > 50:
                        parts = Path(source).parts
                        source = f".../{'/'.join(parts[-2:])}" if len(parts) > 2 else source
                    console.print(f"     Source: {source}")

        # Overall health
        console.print("\n" + "─" * 50)
        if all_healthy:
            console.print("[bold green]✅ All systems operational[/bold green]")
        else:
            console.print("[bold yellow]⚠️ Some issues detected[/bold yellow]")

        # Auto-fix actions
        if fix_actions:
            console.print("\n[bold]Auto-fix actions taken:[/bold]")
            for action in fix_actions:
                console.print(f"  • {action}")

        # Recommendations
        if all_recommendations and not all_healthy:
            console.print("\n[bold]Recommendations:[/bold]")
            for rec in all_recommendations[:5]:  # Limit to 5 most important
                console.print(f"  • {rec}")
            if len(all_recommendations) > 5:
                console.print(f"  ... and {len(all_recommendations) - 5} more")
                if not verbose:
                    console.print("  Run with --verbose to see all")

            if not auto_fix:
                console.print(
                    f"\nRun [cyan]{brand.cli_name} doctor --fix[/cyan] to attempt automatic fixes"
                )

        # Show verbose recommendations
        if verbose and len(all_recommendations) > 5:
            console.print("\n[dim]All recommendations:[/dim]")
            for rec in all_recommendations[5:]:
                console.print(f"  • {rec}")


__all__ = ["doctor", "app"]
