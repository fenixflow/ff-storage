"""PyPI publishing commands."""

from pathlib import Path

import typer
from rich.console import Console

from ..utils import (
    build_package,
    check_package,
    check_pypi_auth,
    check_pypi_version,
    create_git_tag,
    get_package_info,
    publish_to_pypi,
    push_git_tag,
)
from ..utils.constants import SUPPORTED_PACKAGES

console = Console()


def publish_package(
    package: str = typer.Argument(..., help="Package name to publish"),
    test: bool = typer.Option(False, "--test", help="Publish to TestPyPI instead"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Build and check only, don't publish"),
    create_tag: bool = typer.Option(True, "--tag/--no-tag", help="Create git tag after publishing"),
):
    """Publish a package to PyPI."""
    # Validate package
    if package not in SUPPORTED_PACKAGES:
        console.print(f"[red]Error: '{package}' is not a supported package[/red]")
        console.print(f"Supported packages: {', '.join(SUPPORTED_PACKAGES)}")
        raise typer.Exit(1)

    pypi_name = "TestPyPI" if test else "PyPI"
    console.print(f"[bold]Publishing {package} to {pypi_name}[/bold]\n")

    # Check PyPI authentication
    pypi_ok, pypi_msg = check_pypi_auth(test_pypi=test)
    if not pypi_ok:
        console.print(f"[red]✗ {pypi_name} authentication not configured[/red]")
        console.print(f"  {pypi_msg}")
        console.print("\nRun [cyan]fenix ff-packages check[/cyan] for setup instructions")
        raise typer.Exit(1)

    console.print(f"[green]✓ {pypi_name} authentication configured[/green]")

    # Get package path
    package_path = Path.cwd() / package
    if not package_path.exists():
        console.print(f"[red]Error: Package directory not found: {package_path}[/red]")
        raise typer.Exit(1)

    # Get package info
    try:
        info = get_package_info(package_path)
        pkg_name = info["name"]
        version = info["version"]
    except Exception as e:
        console.print(f"[red]Error reading package info: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"Package: [cyan]{pkg_name}[/cyan]")
    console.print(f"Version: [cyan]{version}[/cyan]")

    # Check if version exists on PyPI
    exists, check_msg = check_pypi_version(pkg_name, version, test_pypi=test)
    if exists:
        console.print(f"\n[yellow]⚠ {check_msg}[/yellow]")
        if not dry_run:
            if not typer.confirm("Version exists. Continue anyway?"):
                console.print("Aborted")
                raise typer.Exit(0)
    else:
        console.print(f"[dim]{check_msg}[/dim]")

    # Build package
    console.print("\n[bold]Building package...[/bold]")
    with console.status("Building..."):
        build_ok, build_msg = build_package(package_path)

    if not build_ok:
        console.print(f"[red]✗ {build_msg}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✓ {build_msg}[/green]")

    # Check package with twine
    with console.status("Checking package..."):
        check_ok, check_msg = check_package(package_path)

    if not check_ok:
        console.print(f"[red]✗ {check_msg}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✓ {check_msg}[/green]")

    # Show what would be uploaded
    dist_files = list((package_path / "dist").glob("*"))
    console.print("\n[bold]Build artifacts:[/bold]")
    for file in dist_files:
        console.print(f"  {file.name}")

    if dry_run:
        console.print(f"\n[yellow][DRY RUN] Would upload to {pypi_name}[/yellow]")
        console.print(f"Package: {pkg_name} v{version}")
        return

    # Confirm upload
    console.print(f"\nReady to publish [cyan]{pkg_name} v{version}[/cyan] to {pypi_name}")
    if not typer.confirm("Proceed with upload?"):
        console.print("Aborted")
        raise typer.Exit(0)

    # Upload to PyPI
    console.print(f"\n[bold]Publishing to {pypi_name}...[/bold]")
    with console.status("Uploading..."):
        upload_ok, upload_msg = publish_to_pypi(package_path, test_pypi=test)

    if not upload_ok:
        console.print(f"[red]✗ {upload_msg}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✓ {upload_msg}[/green]")

    # Show package URL
    if test:
        pkg_url = f"https://test.pypi.org/project/{pkg_name}/{version}/"
    else:
        pkg_url = f"https://pypi.org/project/{pkg_name}/{version}/"

    console.print(f"\nPackage URL: [link={pkg_url}]{pkg_url}[/link]")

    # Create git tag
    if create_tag:
        console.print("\n[bold]Creating git tag...[/bold]")
        tag_ok, tag_msg = create_git_tag(package, version)

        if tag_ok:
            console.print(f"[green]✓ {tag_msg}[/green]")

            # Ask to push tag
            if typer.confirm("Push tag to origin?"):
                tag_name = f"{package}-v{version}"
                push_ok, push_msg = push_git_tag(tag_name, "origin")

                if push_ok:
                    console.print(f"[green]✓ {push_msg}[/green]")
                else:
                    console.print(f"[yellow]⚠ {push_msg}[/yellow]")
        else:
            console.print(f"[yellow]⚠ {tag_msg}[/yellow]")

    console.print(f"\n[green bold]✓ Successfully published {pkg_name} v{version} to {pypi_name}![/green bold]")