"""GitHub mirroring commands."""


import typer
from rich.console import Console

from ..utils import check_git_status, check_github_auth, push_to_github
from ..utils.constants import REPO_ROOT, SUPPORTED_PACKAGES

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

    # Get package path
    package_path = REPO_ROOT / package
    if not package_path.exists():
        console.print(f"[red]Error: Package directory not found: {package_path}[/red]")
        raise typer.Exit(1)

    # Check GitHub authentication
    github_ok, github_msg = check_github_auth()
    if not github_ok:
        console.print("[red]✗ GitHub authentication not configured[/red]")
        console.print(f"  {github_msg}")
        console.print("\nRun [cyan]fenix ff-packages check[/cyan] for setup instructions")
        raise typer.Exit(1)

    console.print("[green]✓ GitHub authentication configured[/green]")

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
        console.print(f"  - Target branch: {current_branch}")
        console.print(f"  - Package: {package}")
        console.print("  - Source: origin/main (GitLab)")
        console.print("  - Method: Clean snapshot (git archive, no history)")
        console.print(f"  - Tags: Only {package}-v* tags")
        console.print("  - Effect: Force push replaces entire GitHub repo")
        return

    # Confirm push
    console.print(f"\nReady to mirror [cyan]{package}[/cyan] to GitHub")
    console.print("  Source: origin/main (committed code from GitLab)")
    console.print(f"  Target branch: {current_branch}")
    console.print("  Method: Clean snapshot (single commit, no history)")
    console.print(f"  Tags: Only {package}-v* tags will be pushed")
    console.print("  [yellow]⚠ This will REPLACE all content on GitHub[/yellow]")

    if not typer.confirm("\nProceed?"):
        console.print("Aborted")
        raise typer.Exit(0)

    # Push to GitHub (uses git subtree split to push only package directory)
    with console.status(f"Pushing {package} to GitHub..."):
        success, message = push_to_github(package, str(package_path), current_branch)

    if success:
        console.print(f"\n[green]✓ {message}[/green]")
        console.print(f"View at: https://github.com/fenixflow/{package}")
    else:
        console.print(f"\n[red]✗ {message}[/red]")
        raise typer.Exit(1)
