"""Developer utility commands for the branded CLI."""

import socket
import subprocess

import typer
from rich.table import Table

from ..branding import get_brand
from ..utils.common import console

brand = get_brand()

app = typer.Typer(
    name="dev",
    help=f"Developer utilities for {brand.cli_display_name}",
    no_args_is_help=True,
)


@app.command()
def lint():
    """Run ruff linter with auto-fix."""
    console.print("[cyan]Running ruff check --fix ...[/cyan]")
    result = subprocess.run(["uvx", "ruff", "check", "--fix", "."])
    if result.returncode == 0:
        console.print("[green]Lint passed[/green]")
    else:
        console.print("[red]Lint found issues[/red]")
    raise typer.Exit(result.returncode)


@app.command("format")
def format_code():
    """Run ruff formatter."""
    console.print("[cyan]Running ruff format ...[/cyan]")
    result = subprocess.run(["uvx", "ruff", "format", "."])
    if result.returncode == 0:
        console.print("[green]Format complete[/green]")
    else:
        console.print("[red]Format failed[/red]")
    raise typer.Exit(result.returncode)


@app.command()
def test(
    coverage: bool = typer.Option(False, "--coverage", help="Enable coverage reporting"),
):
    """Run pytest via uv."""
    cmd = ["uv", "run", "pytest"]
    if coverage:
        cmd.append("--cov")

    console.print(f"[cyan]Running {' '.join(cmd)}...[/cyan]")
    result = subprocess.run(cmd)
    raise typer.Exit(result.returncode)


@app.command()
def ports():
    """Check common development ports for active listeners."""
    port_ranges = [
        range(3000, 3012),
        range(5000, 5051),
        [5432],
        [6379],
        range(8000, 8201),
        [27017],
    ]

    all_ports: list[int] = []
    for r in port_ranges:
        all_ports.extend(r)

    table = Table(title="Port Status")
    table.add_column("Port", style="cyan", justify="right")
    table.add_column("Status")
    table.add_column("Common Use", style="dim")

    known_services = {
        3000: "Frontend / Next.js",
        3001: "Frontend alt",
        5000: "Flask",
        5432: "PostgreSQL",
        6379: "Redis",
        8000: "FastAPI / Django",
        8080: "HTTP alt",
        8443: "HTTPS alt",
        27017: "MongoDB",
    }

    active_count = 0
    for port in all_ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.15)
            in_use = sock.connect_ex(("127.0.0.1", port)) == 0

        if in_use:
            status = "[green]LISTENING[/green]"
            active_count += 1
        else:
            status = "[dim]free[/dim]"

        service_hint = known_services.get(port, "")

        # Only show free ports if they are well-known, otherwise skip
        if in_use or service_hint:
            table.add_row(str(port), status, service_hint)

    console.print(table)
    console.print(f"\n[cyan]{active_count}[/cyan] active port(s) detected")
