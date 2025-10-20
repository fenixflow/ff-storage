"""Setup command for authentication configuration."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..utils import check_all_auth

console = Console()


def check_auth(verbose: bool = False):
    """Check authentication status for GitHub and PyPI."""
    auth_status = check_all_auth()

    table = Table(title="Authentication Status")
    table.add_column("Service", style="cyan", no_wrap=True)
    table.add_column("Status", style="bold")
    table.add_column("Message", style="dim")

    for service, (is_ok, message) in auth_status.items():
        status_icon = "[green]✓[/green]" if is_ok else "[red]✗[/red]"
        status_text = "Configured" if is_ok else "Not configured"

        table.add_row(
            service.replace("_", " ").title(),
            f"{status_icon} {status_text}",
            message,
        )

    console.print(table)

    # Show setup instructions if any auth is missing
    missing_auth = [k for k, (ok, _) in auth_status.items() if not ok]

    if missing_auth:
        console.print("\n[yellow]⚠ Some authentication is not configured[/yellow]\n")

        if "github" in missing_auth:
            console.print(
                Panel(
                    "[bold]GitHub Setup:[/bold]\n\n"
                    "1. Generate SSH key:\n"
                    "   [cyan]ssh-keygen -t ed25519 -C 'your_email@example.com'[/cyan]\n\n"
                    "2. Add to GitHub:\n"
                    "   [cyan]cat ~/.ssh/id_ed25519.pub[/cyan]\n"
                    "   Copy and add at: https://github.com/settings/keys\n\n"
                    "3. Test connection:\n"
                    "   [cyan]ssh -T git@github.com[/cyan]",
                    title="GitHub Authentication",
                    border_style="yellow",
                )
            )

        if "pypi" in missing_auth or "test_pypi" in missing_auth:
            console.print(
                Panel(
                    "[bold]PyPI Setup:[/bold]\n\n"
                    "1. Generate API token at:\n"
                    "   Production: https://pypi.org/manage/account/token/\n"
                    "   Test: https://test.pypi.org/manage/account/token/\n\n"
                    "2. Set environment variable:\n"
                    "   [cyan]export PYPI_TOKEN='pypi-...'[/cyan]\n"
                    "   [cyan]export TEST_PYPI_TOKEN='pypi-...'[/cyan]\n\n"
                    "3. Add to shell profile (~/.bashrc or ~/.zshrc):\n"
                    "   To make permanent",
                    title="PyPI Authentication",
                    border_style="yellow",
                )
            )

        console.print(
            "\nFor detailed setup instructions, see:\n"
            "[cyan]docs/PUBLISHING_SETUP.md[/cyan]"
        )
    else:
        console.print("\n[green]✓ All authentication configured![/green]")