"""GitHub mirroring commands."""

from pathlib import Path

import typer
from rich.console import Console

from ..utils import check_git_status, check_github_auth, push_to_github
from ..utils.constants import SUPPORTED_PACKAGES

console = Console()


def mirror_to_github(
    package: str = typer.Argument(..., help="Package name to mirror"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
):
    """Mirror a package to GitHub."""
    # Validate package
    if package not in SUPPORTED_PACKAGES:
        console.print(f"[red]Error: '{package}' is not a supported package[/red]")
        console.print(f"Supported packages: {', '.join(SUPPORTED_PACKAGES)}")
        raise typer.Exit(1)

    console.print(f"[bold]Mirroring {package} to GitHub[/bold]\n")

    # Check GitHub authentication
    github_ok, github_msg = check_github_auth()
    if not github_ok:
        console.print(f"[red]✗ GitHub authentication not configured[/red]")
        console.print(f"  {github_msg}")
        console.print("\nRun [cyan]fenix ff-packages check[/cyan] for setup instructions")
        raise typer.Exit(1)

    console.print(f"[green]✓ GitHub authentication configured[/green]")

    # Check git status
    is_clean, current_branch, uncommitted = check_git_status()

    console.print(f"Current branch: [cyan]{current_branch}[/cyan]")

    if not is_clean:
        console.print("[yellow]⚠ You have uncommitted changes:[/yellow]")
        for file in uncommitted[:5]:  # Show first 5
            console.print(f"  {file}")
        if len(uncommitted) > 5:
            console.print(f"  ... and {len(uncommitted) - 5} more")

        if not dry_run:
            confirm = typer.confirm("\nContinue anyway?")
            if not confirm:
                console.print("Aborted")
                raise typer.Exit(0)

    if dry_run:
        console.print("\n[yellow][DRY RUN] Would push to GitHub:[/yellow]")
        console.print(f"  - Branch: {current_branch}")
        console.print(f"  - Package: {package}")
        console.print(f"  - Tags: All tags matching {package}-v*")
        return

    # Confirm push
    console.print(f"\nReady to push [cyan]{package}[/cyan] to GitHub")
    console.print(f"  Branch: {current_branch}")
    console.print("  All tags will also be pushed")

    if not typer.confirm("\nProceed?"):
        console.print("Aborted")
        raise typer.Exit(0)

    # Push to GitHub
    with console.status(f"Pushing {package} to GitHub..."):
        success, message = push_to_github(package, current_branch)

    if success:
        console.print(f"\n[green]✓ {message}[/green]")
        console.print(f"\nView at: https://github.com/fenixflow/{package}")
    else:
        console.print(f"\n[red]✗ {message}[/red]")
        raise typer.Exit(1)