"""Branding management commands for the CLI."""

import os
import shutil
from pathlib import Path

import typer
from rich.table import Table

from ff_cli.branding import (
    BrandConfig,
    clear_user_brand_config,
    get_brand,
    get_user_brand_path,
    reset_brand_cache,
    save_user_brand_config,
    set_brand,
    user_brand_exists,
)
from ff_cli.utils.common import console

app = typer.Typer(help="Configure CLI branding", no_args_is_help=True)


def _slugify(value: str) -> str:
    """Convert a CLI name into a slug suitable for config paths."""
    return value.strip().lower().replace(" ", "-").replace("_", "-")


def _print_brand(brand: BrandConfig, source: str) -> None:
    """Render branding details in a simple table."""
    table = Table(show_header=False, box=None)
    table.add_column("Field", style="dim")
    table.add_column("Value", style="cyan")

    table.add_row("CLI Name", brand.cli_name)
    table.add_row("Display Name", brand.cli_display_name)
    table.add_row("Description", brand.cli_description)
    table.add_row("Company", brand.company_name)
    table.add_row("Icon", brand.icon)
    table.add_row("Config dir", brand.config_dir_name)
    table.add_row("Plugin entry-point", brand.plugin_entry_point)
    table.add_row("Docker network", brand.docker_network)
    table.add_row("Container prefix", brand.container_prefix)
    table.add_row("Docker project", brand.docker_project)
    table.add_row("OrbStack domain", brand.orbstack_domain_suffix)
    table.add_row("Help header", brand.help_header)
    table.add_row("Source", source)

    console.print(table)


def _maybe_create_wrapper(cli_name: str) -> Path | None:
    """Create a wrapper script in ~/.local/bin if possible."""
    if os.name == "nt":
        console.print(
            "[yellow]Skipping wrapper creation: automatic scripts are not supported on Windows.[/yellow]"
        )
        return None

    slug = cli_name.strip()
    if not slug:
        return None

    if shutil.which(slug):
        console.print(
            f"[yellow]Command '{slug}' already exists on PATH. Wrapper not created.[/yellow]"
        )
        return None

    wrapper_dir = Path.home() / ".local" / "bin"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    wrapper_path = wrapper_dir / slug
    if wrapper_path.exists():
        console.print(
            f"[yellow]Wrapper {wrapper_path} already exists. Leaving it untouched.[/yellow]"
        )
        return None

    script = '#!/usr/bin/env bash\nfenix "$@"\n'
    wrapper_path.write_text(script)
    wrapper_path.chmod(0o755)

    if str(wrapper_dir) not in os.environ.get("PATH", ""):
        console.print(f"[yellow]Reminder: add {wrapper_dir} to your PATH to use '{slug}'.[/yellow]")

    console.print(f"[green]Created wrapper command at {wrapper_path}.[/green]")
    return wrapper_path


@app.command("show")
def show_brand() -> None:
    """Display the current branding configuration."""
    brand = get_brand()
    source = "User override" if user_brand_exists() else "Built-in"
    console.print("[bold]Current branding[/bold]")
    _print_brand(brand, source)
    console.print()
    console.print(
        f"Configuration file: {get_user_brand_path()}"
        if user_brand_exists()
        else "Run 'fenix branding configure' to customise branding."
    )


@app.command("configure")
def configure_brand() -> None:
    """Interactively configure branding values and persist them."""
    current = get_brand()

    console.print(
        "[bold]Branding configuration wizard[/bold]\n"
        "Press Enter to keep the current value shown in brackets."
    )

    raw_name = typer.prompt("CLI command name", default=current.cli_name)
    cli_name = _slugify(raw_name or current.cli_name) or current.cli_name

    title_default = (
        current.cli_display_name
        if current.cli_name == cli_name
        else f"{cli_name.replace('-', ' ').title()} CLI"
    )
    cli_display_name = typer.prompt("Display name", default=title_default)
    company_name = typer.prompt("Company", default=current.company_name)
    icon = typer.prompt("Icon", default=current.icon)

    cli_description = f"Unified command-line interface for the {cli_display_name}"
    version_prefix = cli_display_name
    config_dir_name = current.config_dir_name if current.cli_name == cli_name else f".{cli_name}"
    plugin_entry_point = f"{cli_name}.plugins"
    docker_network = f"{cli_name}-network"
    container_prefix = cli_name
    docker_project = cli_name
    orbstack_domain_suffix = f"{cli_name}.orb.local"
    help_header = f"Unified command-line interface for {cli_display_name}"

    new_brand = BrandConfig(
        cli_name=cli_name,
        cli_display_name=cli_display_name,
        cli_description=cli_description,
        icon=icon,
        version_prefix=version_prefix,
        company_name=company_name,
        config_dir_name=config_dir_name,
        plugin_entry_point=plugin_entry_point,
        docker_network=docker_network,
        container_prefix=container_prefix,
        docker_project=docker_project,
        orbstack_domain_suffix=orbstack_domain_suffix,
        help_header=help_header,
        help_examples=[],
    )

    save_user_brand_config(new_brand)
    reset_brand_cache()
    set_brand(new_brand)

    console.print("\n[green]Branding updated successfully.[/green]")
    _print_brand(new_brand, "User override")

    if os.name != "nt":
        create_wrapper = typer.confirm(
            f"Create a helper command '{cli_name}' in ~/.local/bin?", default=False
        )
        if create_wrapper:
            _maybe_create_wrapper(cli_name)
    else:
        console.print(
            "[dim]On Windows, create a .cmd wrapper manually to expose the new command name.[/dim]"
        )


@app.command("reset")
def reset_brand(yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation")) -> None:
    """Remove any saved branding overrides and revert to defaults."""
    if not user_brand_exists():
        console.print("[yellow]No saved branding override found.[/yellow]")
        return

    if not yes and not typer.confirm("Reset branding to built-in defaults?"):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    clear_user_brand_config()
    reset_brand_cache()
    get_brand()  # pragma: no cover - rehydrate cache
    console.print("[green]Branding reset to defaults.[/green]")


__all__ = ["app"]
