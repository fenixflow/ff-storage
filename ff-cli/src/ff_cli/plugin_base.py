"""Base protocol and interfaces for branded CLI plugins."""

from typing import Any, Protocol

from ff_cli.branding import get_brand


class StatusInfo(dict[str, Any]):
    """Status information returned by plugins."""

    name: str
    healthy: bool
    services: list[dict[str, Any]]
    message: str
    metrics: dict[str, Any] | None
    warnings: list[str] | None
    errors: list[str] | None


class StatusProtocol(Protocol):
    """Protocol for plugins that provide status information."""

    def get_status(self, verbose: bool = False) -> dict[str, Any]:
        """Get plugin status information.

        Args:
            verbose: Include detailed metrics and information

        Returns:
            Status dictionary with the following structure:
            {
                "name": "Plugin Name",
                "healthy": True/False,
                "services": [
                    {
                        "name": "Service Name",
                        "running": True/False,
                        "url": "http://...",  # Optional
                        "health": "healthy/unhealthy/unknown",  # Optional
                        "message": "Service-specific message",  # Optional
                    }
                ],
                "message": "Overall status message",
                "metrics": {...},  # Optional, shown in verbose mode
                "warnings": [...],  # Optional list of warning messages
                "errors": [...],    # Optional list of error messages
            }
        """
        ...


def has_status_support(app) -> bool:
    """Check if a Typer app has status support.

    Args:
        app: Typer application instance

    Returns:
        True if the app has a get_status method
    """
    return hasattr(app, "get_status") and callable(app.get_status)


def get_plugin_status(app, verbose: bool = False) -> dict[str, Any] | None:
    """Get status from a plugin if it supports the protocol.

    Args:
        app: Typer application instance
        verbose: Include detailed metrics

    Returns:
        Status dictionary or None if not supported
    """
    if has_status_support(app):
        try:
            return app.get_status(verbose=verbose)
        except Exception as e:
            return {
                "name": "Unknown Plugin",
                "healthy": False,
                "services": [],
                "message": "Failed to get status",
                "errors": [str(e)],
            }
    return None


def aggregate_health(statuses: list[dict[str, Any]]) -> str:
    """Aggregate health status from multiple sources.

    Args:
        statuses: List of status dictionaries

    Returns:
        Overall health: "HEALTHY", "PARTIAL", or "UNHEALTHY"
    """
    if not statuses:
        return "UNKNOWN"

    all_healthy = all(s.get("healthy", False) for s in statuses)
    any_healthy = any(s.get("healthy", False) for s in statuses)

    if all_healthy:
        return "HEALTHY"
    elif any_healthy:
        return "PARTIAL"
    else:
        return "UNHEALTHY"


def format_health_indicator(health: str) -> str:
    """Format health status with colored indicator.

    Args:
        health: Health status string

    Returns:
        Formatted health string with emoji/color
    """
    indicators = {
        "HEALTHY": "[green]✅ HEALTHY[/green]",
        "PARTIAL": "[yellow]⚠️  PARTIAL[/yellow]",
        "UNHEALTHY": "[red]🔴 UNHEALTHY[/red]",
        "UNKNOWN": "[dim]❓ UNKNOWN[/dim]",
    }
    return indicators.get(health.upper(), health)


def generate_recommendations(
    statuses: list[dict[str, Any]], docker_info: dict[str, Any]
) -> list[str]:
    """Generate actionable recommendations based on system status.

    Args:
        statuses: List of status dictionaries
        docker_info: Docker system information

    Returns:
        List of recommendation strings
    """
    brand = get_brand()
    cli_name = brand.cli_name
    recommendations: list[str] = []

    # Check Docker status
    if not docker_info.get("running", False):
        recommendations.append("Start Docker: Check if Docker Desktop or OrbStack is running")
        return recommendations  # No point in other recommendations if Docker isn't running

    # Check network status
    network = docker_info.get("network", {})
    if not network.get("exists"):
        recommendations.append(
            f"Network missing - will be created on next service start ({cli_name} services up <name>)"
        )

    # Check for services that are defined but not created
    for status in statuses:
        if status.get("name") == "Core Services":
            services = status.get("services", [])
            not_created = [s for s in services if not s.get("exists", False)]
            stopped = [s for s in services if s.get("exists") and not s.get("running")]

            # Recommend creating services that don't exist
            for service in not_created[:2]:  # Limit to first 2
                name = service.get("name")
                recommendations.append(f"Create {name}: {cli_name} services up {name}")

            # Recommend starting stopped services
            for service in stopped[:2]:  # Limit to first 2
                name = service.get("name")
                recommendations.append(f"Start {name}: {cli_name} services up {name}")

    # Check for unhealthy services
    for status in statuses:
        services = status.get("services", [])
        for service in services:
            if service.get("health") == "unhealthy":
                name = service.get("name")
                recommendations.append(f"Check {name} health: {cli_name} services logs {name}")

    # Check for plugin errors
    for status in statuses:
        if status.get("errors") and "Plugin" in status.get("name", ""):
            for error in status["errors"][:1]:  # Just first error
                if "connection" in error.lower():
                    recommendations.append(f"Check {status.get('name')} connection settings")
                elif "permission" in error.lower():
                    recommendations.append(f"Check {status.get('name')} permissions")
                else:
                    recommendations.append(f"{status.get('name')}: {error[:50]}...")

    return recommendations[:5]  # Limit to 5 most relevant recommendations
