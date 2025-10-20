"""List command for showing publishable packages."""

import typer
from rich.console import Console
from rich.table import Table

from ..utils.constants import GITHUB_REPOS, SUPPORTED_PACKAGES

console = Console()


def list_packages():
    """List all publishable packages."""
    table = Table(title="Publishable Packages")
    table.add_column("Package", style="cyan", no_wrap=True)
    table.add_column("GitHub Repository", style="green")
    table.add_column("Status", style="yellow")

    for package in SUPPORTED_PACKAGES:
        github_repo = GITHUB_REPOS.get(package, "Not configured")
        status = "✓ Ready" if package in GITHUB_REPOS else "⚠ Not configured"

        table.add_row(package, github_repo, status)

    console.print(table)
    console.print(f"\nTotal packages: {len(SUPPORTED_PACKAGES)}")
    console.print("\nUse [cyan]fenix ff-packages github <package>[/cyan] to mirror to GitHub")
    console.print("Use [cyan]fenix ff-packages pypi <package>[/cyan] to publish to PyPI")