"""Plugin script management commands for the branded CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer
from rich.table import Table

from ff_cli import plugin_registry
from ff_cli.branding import get_brand
from ff_cli.config import get_logger
from ff_cli.plugin_helpers import ScriptManager
from ff_cli.utils.common import console

brand = get_brand()
app = typer.Typer(
    name="scripts",
    help=f"{brand.icon} Manage plugin scripts",
    no_args_is_help=True,
    rich_help_panel="Core Commands",
)
logger = get_logger("scripts")


def _collect_managers(plugin: str | None = None) -> list[tuple[str, ScriptManager]]:
    """Return script managers for installed plugins."""
    installed = plugin_registry.list_installed_plugins()
    managers: list[tuple[str, ScriptManager]] = []

    if plugin and plugin not in installed:
        console.print(f"[red]❌ Plugin '{plugin}' is not installed[/red]")
        raise typer.Exit(1) from None

    for name, info in sorted(installed.items()):
        if plugin and name != plugin:
            continue
        source_path = Path(info.get("source_path", "")).resolve()
        scripts_dir = source_path / "scripts"
        if scripts_dir.exists() and any(scripts_dir.glob("*.yaml")):
            managers.append((name, ScriptManager(name, scripts_dir)))
        else:
            logger.debug("Plugin %s has no scripts directory at %s", name, scripts_dir)
    return managers


@app.command("list")
def list_scripts(
    plugin: str | None = typer.Option(None, "--plugin", "-p", help="Filter by plugin"),
):
    """List available scripts across plugins."""
    managers = _collect_managers(plugin)
    if not managers:
        console.print(f"{brand.icon} [yellow]No scripts defined by installed plugins.[/yellow]")
        return

    table = Table(title=f"{brand.icon} Plugin Scripts", show_header=True, header_style="bold cyan")
    table.add_column("Plugin", style="cyan")
    table.add_column("Script", style="yellow")
    table.add_column("State", style="green")
    table.add_column("PID", style="dim")
    table.add_column("Command", style="magenta")
    table.add_column("Description", style="dim")

    for plugin_name, manager in managers:
        statuses = {status.name: status for status in manager.status()}
        for definition in manager.list_definitions():
            status = statuses.get(definition.name)
            running = status.running if status else False
            pid = status.pid if status else None
            state = "✅ running" if running else "⏹️  stopped"
            table.add_row(
                plugin_name,
                definition.name,
                state,
                str(pid or "-"),
                definition.raw_command,
                definition.description,
            )

    console.print(table)


@app.command("status")
def scripts_status(
    plugin: str | None = typer.Option(None, "--plugin", "-p", help="Filter by plugin"),
    name: str | None = typer.Option(None, "--name", "-n", help="Script name to inspect"),
):
    """Show status for plugin scripts."""
    managers = _collect_managers(plugin)
    if not managers:
        console.print(f"{brand.icon} [yellow]No scripts defined by installed plugins.[/yellow]")
        return

    table = Table(title=f"{brand.icon} Script Status", show_header=True, header_style="bold cyan")
    table.add_column("Plugin", style="cyan")
    table.add_column("Script", style="yellow")
    table.add_column("State", style="green")
    table.add_column("PID", style="dim")
    table.add_column("Command", style="magenta")

    for plugin_name, manager in managers:
        statuses = manager.status(name)
        for status in statuses:
            state = "running" if status.running else "stopped"
            table.add_row(
                plugin_name,
                status.name,
                state,
                str(status.pid or "-"),
                status.command,
            )

    console.print(table)


@app.command("run")
def run_script(
    plugin: str = typer.Argument(..., help="Plugin providing the script"),
    script: str = typer.Argument(..., help="Script name"),
    attach: bool = typer.Option(False, "--attach", help="Run attached (foreground)"),
):
    """Run a script from a plugin."""
    managers = _collect_managers(plugin)
    if not managers:
        console.print(f"[red]❌ Script '{script}' not found for plugin '{plugin}'[/red]")
        raise typer.Exit(1) from None

    manager = managers[0][1]
    try:
        pid = manager.run(script, detach=not attach)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Script '{script}' exited with status {exc.returncode}[/red]")
        raise typer.Exit(exc.returncode) from exc

    if attach:
        console.print(f"[green]✅ Script '{script}' completed successfully[/green]")
    else:
        console.print(f"[green]✅ Started '{script}' in background (pid {pid})[/green]")


@app.command("stop")
def stop_script(
    plugin: str = typer.Argument(..., help="Plugin providing the script"),
    script: str = typer.Argument(..., help="Script name"),
    force: bool = typer.Option(False, "--force", help="Force terminate"),
):
    """Stop a running script."""
    managers = _collect_managers(plugin)
    if not managers:
        console.print(f"[red]❌ Script '{script}' not found for plugin '{plugin}'[/red]")
        raise typer.Exit(1) from None

    manager = managers[0][1]
    if manager.stop(script, force=force):
        console.print(f"[green]✅ Stopped script '{script}'[/green]")
    else:
        console.print(f"[yellow]⚠️  Script '{script}' is not running[/yellow]")


@app.command("edit")
def edit_script(
    plugin: str = typer.Argument(..., help="Plugin providing the script"),
    script: str = typer.Argument(..., help="Script name"),
):
    """Open a script definition in the configured editor."""
    managers = _collect_managers(plugin)
    if not managers:
        console.print(f"[red]❌ Script '{script}' not found for plugin '{plugin}'[/red]")
        raise typer.Exit(1) from None

    manager = managers[0][1]
    try:
        path = manager.edit(script)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None

    console.print(f"[green]Opened {path}[/green]")


__all__ = ["app"]
