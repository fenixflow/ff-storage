"""Terraform command wrappers."""

import subprocess
from pathlib import Path

import typer

from ..branding import get_brand
from ..utils.common import command_exists, console

brand = get_brand()

app = typer.Typer(
    name="tf",
    help=f"Terraform operations for {brand.cli_display_name}",
    no_args_is_help=True,
)


def _ensure_terraform() -> None:
    """Abort if terraform is not available."""
    if not command_exists("terraform"):
        console.print("[red]Terraform is not installed or not in PATH[/red]")
        console.print("Install from: https://developer.hashicorp.com/terraform/install")
        raise typer.Exit(1)


def _resolve_path(path: str) -> Path:
    """Resolve and validate a terraform directory path."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        console.print(f"[red]Directory not found: {resolved}[/red]")
        raise typer.Exit(1)
    return resolved


@app.command()
def init(
    path: str = typer.Argument(..., help="Path to Terraform directory"),
):
    """Run terraform init in the given directory."""
    _ensure_terraform()
    work_dir = _resolve_path(path)

    console.print(f"[cyan]Running terraform init in {work_dir}...[/cyan]")
    result = subprocess.run(
        ["terraform", "init"],
        cwd=str(work_dir),
        text=True,
    )
    if result.returncode != 0:
        console.print("[red]terraform init failed[/red]")
        raise typer.Exit(1)

    console.print("[green]terraform init completed successfully[/green]")


@app.command()
def plan(
    path: str = typer.Argument(..., help="Path to Terraform directory"),
    var_file: str | None = typer.Option(None, "--var-file", help="Path to a .tfvars variable file"),
):
    """Run terraform plan in the given directory."""
    _ensure_terraform()
    work_dir = _resolve_path(path)

    cmd = ["terraform", "plan"]
    if var_file:
        cmd.extend(["-var-file", var_file])

    console.print(f"[cyan]Running terraform plan in {work_dir}...[/cyan]")
    result = subprocess.run(
        cmd,
        cwd=str(work_dir),
        text=True,
    )
    if result.returncode != 0:
        console.print("[red]terraform plan failed[/red]")
        raise typer.Exit(1)

    console.print("[green]terraform plan completed successfully[/green]")


@app.command()
def apply(
    path: str = typer.Argument(..., help="Path to Terraform directory"),
    var_file: str | None = typer.Option(None, "--var-file", help="Path to a .tfvars variable file"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Skip interactive approval"),
):
    """Run terraform apply in the given directory."""
    _ensure_terraform()
    work_dir = _resolve_path(path)

    cmd = ["terraform", "apply"]
    if var_file:
        cmd.extend(["-var-file", var_file])
    if auto_approve:
        cmd.append("-auto-approve")

    console.print(f"[cyan]Running terraform apply in {work_dir}...[/cyan]")
    result = subprocess.run(
        cmd,
        cwd=str(work_dir),
        text=True,
    )
    if result.returncode != 0:
        console.print("[red]terraform apply failed[/red]")
        raise typer.Exit(1)

    console.print("[green]terraform apply completed successfully[/green]")


@app.command()
def destroy(
    path: str = typer.Argument(..., help="Path to Terraform directory"),
    auto_approve: bool = typer.Option(
        False, "--auto-approve", help="Skip interactive confirmation"
    ),
):
    """Run terraform destroy in the given directory."""
    _ensure_terraform()
    work_dir = _resolve_path(path)

    if not auto_approve:
        confirm = typer.confirm(f"Are you sure you want to destroy resources in {work_dir}?")
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            raise typer.Exit(0)

    cmd = ["terraform", "destroy"]
    if auto_approve:
        cmd.append("-auto-approve")

    console.print(f"[cyan]Running terraform destroy in {work_dir}...[/cyan]")
    result = subprocess.run(
        cmd,
        cwd=str(work_dir),
        text=True,
    )
    if result.returncode != 0:
        console.print("[red]terraform destroy failed[/red]")
        raise typer.Exit(1)

    console.print("[green]terraform destroy completed successfully[/green]")
