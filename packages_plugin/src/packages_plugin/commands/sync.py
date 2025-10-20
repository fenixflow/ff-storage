"""Sync command for all-in-one publishing."""

import subprocess
from pathlib import Path

import typer
from rich.console import Console

from . import github, pypi
from ..utils import check_all_auth
from ..utils.constants import SUPPORTED_PACKAGES

console = Console()


def sync_package(
    package: str = typer.Argument(..., help="Package name to sync"),
    skip_tests: bool = typer.Option(False, "--skip-tests", help="Skip running tests"),
    skip_github: bool = typer.Option(False, "--skip-github", help="Skip GitHub mirror"),
    skip_pypi: bool = typer.Option(False, "--skip-pypi", help="Skip PyPI publishing"),
    test_pypi: bool = typer.Option(False, "--test-pypi", help="Use TestPyPI instead"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview actions without executing"),
):
    """Sync a package: test, build, mirror to GitHub, and publish to PyPI."""
    # Validate package
    if package not in SUPPORTED_PACKAGES:
        console.print(f"[red]Error: '{package}' is not a supported package[/red]")
        console.print(f"Supported packages: {', '.join(SUPPORTED_PACKAGES)}")
        raise typer.Exit(1)

    console.print(f"[bold cyan]Package Sync: {package}[/bold cyan]\n")

    # Check all authentication upfront
    console.print("[bold]Checking authentication...[/bold]")
    auth_status = check_all_auth()

    github_ok, github_msg = auth_status["github"]
    pypi_ok, pypi_msg = auth_status["pypi" if not test_pypi else "test_pypi"]

    if not skip_github and not github_ok:
        console.print(f"[red]✗ GitHub: {github_msg}[/red]")
    elif not skip_github:
        console.print(f"[green]✓ GitHub: {github_msg}[/green]")

    if not skip_pypi and not pypi_ok:
        console.print(f"[red]✗ PyPI: {pypi_msg}[/red]")
    elif not skip_pypi:
        console.print(f"[green]✓ PyPI: {pypi_msg}[/green]")

    # Stop if required auth is missing
    if (not skip_github and not github_ok) or (not skip_pypi and not pypi_ok):
        console.print("\n[red]Missing required authentication. Run:[/red]")
        console.print("[cyan]fenix ff-packages check[/cyan]")
        raise typer.Exit(1)

    # Step 1: Run tests
    if not skip_tests:
        console.print("\n" + "=" * 50)
        console.print("[bold]Step 1/4: Running Tests[/bold]")
        console.print("=" * 50)

        if dry_run:
            console.print("[yellow][DRY RUN] Would run: pytest tests/[/yellow]")
        else:
            package_path = Path.cwd() / package
            try:
                result = subprocess.run(
                    ["pytest", "tests/", "-v"],
                    cwd=package_path,
                    capture_output=False,
                )
                if result.returncode != 0:
                    console.print("[red]✗ Tests failed[/red]")
                    raise typer.Exit(1)
                console.print("[green]✓ Tests passed[/green]")
            except FileNotFoundError:
                console.print("[yellow]⚠ pytest not found, skipping tests[/yellow]")
    else:
        console.print("\n[dim]⊘ Skipping tests[/dim]")

    # Step 2: Build (always done for PyPI)
    if not skip_pypi:
        console.print("\n" + "=" * 50)
        console.print("[bold]Step 2/4: Building Package[/bold]")
        console.print("=" * 50)

        if dry_run:
            console.print("[yellow][DRY RUN] Would build package[/yellow]")
        else:
            # This is handled by the pypi command
            console.print("[dim]Will be built during PyPI publish step[/dim]")

    # Step 3: Mirror to GitHub
    if not skip_github:
        console.print("\n" + "=" * 50)
        console.print("[bold]Step 3/4: Mirroring to GitHub[/bold]")
        console.print("=" * 50)

        # Call github command
        github.mirror_to_github(package, dry_run=dry_run)
    else:
        console.print("\n[dim]⊘ Skipping GitHub mirror[/dim]")

    # Step 4: Publish to PyPI
    if not skip_pypi:
        console.print("\n" + "=" * 50)
        console.print(f"[bold]Step 4/4: Publishing to {'TestPyPI' if test_pypi else 'PyPI'}[/bold]")
        console.print("=" * 50)

        # Call pypi command
        pypi.publish_package(package, test=test_pypi, dry_run=dry_run, create_tag=True)
    else:
        console.print("\n[dim]⊘ Skipping PyPI publish[/dim]")

    # Summary
    console.print("\n" + "=" * 50)
    if dry_run:
        console.print("[yellow][DRY RUN] Sync preview completed[/yellow]")
    else:
        console.print("[green bold]✓ Package sync completed successfully![/green bold]")
    console.print("=" * 50)

    console.print(f"\nPackage: [cyan]{package}[/cyan]")
    if not skip_tests:
        console.print("[green]✓ Tests passed[/green]")
    if not skip_github and not dry_run:
        console.print(f"[green]✓ Mirrored to GitHub[/green]: https://github.com/fenixflow/{package}")
    if not skip_pypi and not dry_run:
        pypi_name = "TestPyPI" if test_pypi else "PyPI"
        console.print(f"[green]✓ Published to {pypi_name}[/green]")