"""Plugin management commands for the branded CLI."""

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import tomllib
import typer
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from ff_cli import plugin_creator, plugin_registry
from ff_cli.branding import get_brand
from ff_cli.utils.common import HAS_UV, console, get_git_config

brand = get_brand()

app = typer.Typer(help=f"Manage {brand.cli_display_name} plugins")


@app.command("create")
def create_plugin(
    name: str = typer.Option(None, "--name", help="Plugin name (will prompt if not provided)"),
    path: Path = typer.Option(None, "--path", help="Directory to create plugin in"),
    no_examples: bool = typer.Option(False, "--no-examples", help="Skip example commands"),
    install: bool = typer.Option(
        True, "--install/--no-install", help="Install plugin after creation"
    ),
):
    """Create a new branded CLI plugin with interactive setup."""
    brand = get_brand()
    cli_name = brand.cli_name

    console.print(f"\n[bold cyan]🚀 {brand.cli_display_name} Plugin Creator[/bold cyan]\n")
    console.print(f"Let's create a new plugin for the {brand.cli_display_name}!")
    console.print("I'll guide you through the setup process.\n")

    # Get plugin name
    if not name:
        name = Prompt.ask(
            "[cyan]Plugin package name[/cyan] (e.g., 'my-awesome-plugin')", default="my-plugin"
        )

    # Validate and suggest display name
    display_name = name.lower().replace("_", "-")
    if not display_name.startswith("ff-"):
        display_name = f"ff-{display_name}"

    display_name = Prompt.ask(
        f"[cyan]CLI command namespace[/cyan] (e.g., '{cli_name} [bold]{display_name}[/bold] --help')",
        default=display_name,
    )

    # Get description
    description = Prompt.ask(
        "[cyan]Plugin description[/cyan]",
        default=f"A {brand.cli_display_name} plugin for {name}",
    )

    # Get author information from git config or use defaults
    default_author = get_git_config("user.name", "Your Name")
    default_email = get_git_config("user.email", "you@example.com")

    author_name = Prompt.ask("[cyan]Author name[/cyan]", default=default_author)
    author_email = Prompt.ask("[cyan]Author email[/cyan]", default=default_email)

    # Ask about examples
    if not no_examples:
        include_examples = Confirm.ask(
            "[cyan]Include example commands?[/cyan] (hello, status, config)", default=True
        )
    else:
        include_examples = False

    # Determine where to create the plugin
    if not path:
        default_path = Path.cwd()
        path_str = Prompt.ask("[cyan]Where to create the plugin?[/cyan]", default=str(default_path))
        path = Path(path_str)

    # Create full plugin path with _plugin suffix for the folder
    plugin_folder_name = f"{name}_plugin" if not name.endswith("_plugin") else name
    plugin_path = (path / plugin_folder_name).resolve()  # Always use absolute path

    # Check if plugin path already exists
    force_delete = False
    if plugin_path.exists():
        console.print(f"\n[yellow]⚠️ Directory already exists: {plugin_path}[/yellow]")
        if Confirm.ask("[cyan]Delete existing directory and continue?[/cyan]", default=False):
            force_delete = True
        else:
            console.print("[red]Plugin creation cancelled.[/red]")
            raise typer.Exit(0)

    # Show summary
    console.print("\n[bold]Plugin Configuration:[/bold]")
    summary_table = Table(show_header=False, box=None)
    summary_table.add_column("Property", style="dim")
    summary_table.add_column("Value", style="cyan")
    summary_table.add_row("Package Name", name)
    summary_table.add_row("CLI Namespace", f"{cli_name} {display_name}")
    summary_table.add_row("Description", description)
    summary_table.add_row("Author", f"{author_name} <{author_email}>")
    summary_table.add_row("Location", str(plugin_path))
    summary_table.add_row("Include Examples", "Yes" if include_examples else "No")
    if force_delete:
        summary_table.add_row("Force Delete", "Yes" if force_delete else "No")
    console.print(summary_table)

    if not Confirm.ask("\n[cyan]Create plugin with these settings?[/cyan]", default=True):
        console.print("[yellow]Plugin creation cancelled.[/yellow]")
        raise typer.Exit(0)

    # Create the plugin
    try:
        console.print("\n[cyan]Creating plugin structure...[/cyan]")

        # Delete existing directory if force_delete is True
        if force_delete and plugin_path.exists():
            console.print(f"[cyan]Deleting existing directory: {plugin_path}[/cyan]")
            shutil.rmtree(plugin_path)

        created_path = plugin_creator.create_plugin_structure(
            base_path=path,
            plugin_name=plugin_folder_name,  # This will be the folder name
            display_name=display_name,
            description=description,
            author_name=author_name,
            author_email=author_email,
            include_examples=include_examples,
        )
        console.print(f"[green]✅ Plugin created at: {created_path}[/green]")

        # Get module name for later use (based on original name, not folder name)
        module_name = plugin_creator.sanitize_plugin_name(name)

        # Install the plugin if requested
        if install:
            console.print("\n[cyan]Installing plugin...[/cyan]")
            try:
                # Find plugin info from the created structure
                # entry_point would be f"{module_name}.cli:plugin"

                # Add to registry
                plugin_registry.register_plugin(
                    name=display_name,
                    source_path=str(created_path),
                    package_name=module_name,
                    description=description,
                )

                # Also install in editable mode for development
                console.print("[cyan]Installing in editable mode for development...[/cyan]")
                if HAS_UV:
                    cmd = ["uv", "pip", "install", "-e", str(created_path)]
                else:
                    cmd = [sys.executable, "-m", "pip", "install", "-e", str(created_path)]

                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    console.print("[green]✅ Plugin installed successfully![/green]")
                else:
                    console.print(
                        f"[yellow]⚠️ Could not install in editable mode: {result.stderr}[/yellow]"
                    )
                    console.print(
                        "[dim]The plugin is registered but may need manual installation.[/dim]"
                    )

            except Exception as e:
                console.print(f"[yellow]⚠️ Could not auto-install: {e}[/yellow]")
                console.print(
                    f"[dim]Install manually with: [cyan]{cli_name} plugins install {created_path}[/cyan][/dim]"
                )

        # Show next steps
        console.print(
            Panel.fit(
                f"""[bold green]🎉 Plugin created successfully![/bold green]

[bold]Next steps:[/bold]
1. Navigate to your plugin: [cyan]cd {created_path}[/cyan]
2. Edit the CLI commands: [cyan]{created_path}/src/{module_name}/cli.py[/cyan]
3. Test your plugin: [cyan]{cli_name} {display_name} --help[/cyan]
4. Add more commands as needed!

[dim]Your plugin is ready for development![/dim]""",
                title="Success",
                border_style="green",
            )
        )

    except FileExistsError:
        console.print(f"[red]Error: Directory already exists at {plugin_path}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Error creating plugin: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("list")
def list_plugins():
    """List all installed plugins."""
    brand = get_brand()
    cli_name = brand.cli_name

    # Get plugins from registry
    installed = plugin_registry.list_installed_plugins()

    if not installed:
        console.print("[yellow]No plugins installed[/yellow]")
        console.print(f"\nInstall a plugin with: [cyan]{cli_name} plugins install <path>[/cyan]")
        return

    table = Table(title="Installed Plugins")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Source Path", style="blue")
    table.add_column("Status", style="green")
    table.add_column("Installed", style="dim")

    for name, info in installed.items():
        # Shorten source path for display
        source_path = info["source_path"]
        if len(source_path) > 50:
            parts = Path(source_path).parts
            source_path = f".../{'/'.join(parts[-3:])}" if len(parts) > 3 else source_path

        # Check status
        if info["source_exists"]:
            status = "✅ Active"
        else:
            status = "⚠️ Source missing"

        # Format install date
        install_date = info.get("install_date", "Unknown")
        if install_date != "Unknown":
            try:
                dt = datetime.fromisoformat(install_date)
                install_date = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                pass

        table.add_row(name, source_path, status, install_date)

    console.print(table)

    # Show upgrade hint if any sources are missing
    if any(not info["source_exists"] for info in installed.values()):
        console.print("\n[yellow]⚠️ Some plugins have missing source paths.[/yellow]")
        console.print(f"Reinstall them with: [cyan]{cli_name} plugins install <new-path>[/cyan]")


@app.command("info")
def plugin_info(name: str = typer.Argument(..., help="Plugin name")):
    """Show detailed information about a plugin."""
    brand = get_brand()
    cli_name = brand.cli_name

    info = plugin_registry.get_plugin_info(name)

    if not info:
        console.print(f"[red]Plugin '{name}' not found[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]Plugin: {name}[/bold cyan]")
    console.print(f"Source: {info['source_path']}")
    console.print(f"Module: {info['plugin_module']}")
    console.print(f"Entry Point: {info['entry_point']}")
    console.print(f"Installed: {info['install_date']}")

    # Check status
    source_exists = Path(info["source_path"]).exists()

    console.print("\n[bold]Status:[/bold]")
    console.print(f"  Source exists: {'✅' if source_exists else '❌'}")

    if source_exists:
        console.print("\n[bold]Commands:[/bold]")
        console.print(f"  Upgrade: [cyan]{cli_name} plugins upgrade {name}[/cyan]")
        console.print(f"  Remove: [cyan]{cli_name} plugins remove {name}[/cyan]")


@app.command("install")
def install_plugin(
    source: str = typer.Argument(..., help="Plugin source (local path or git URL)"),
    upgrade: bool = typer.Option(False, "--upgrade", "-U", help="Upgrade if already installed"),
):
    """Install a CLI plugin.

    Examples:
        <cli> plugins install ./local-plugin
        <cli> plugins install /absolute/path/to/plugin
    """
    brand = get_brand()
    cli_name = brand.cli_name

    source_path = Path(source).resolve()

    if not source_path.exists():
        console.print(f"[red]Error: Path {source_path} does not exist[/red]")
        raise typer.Exit(1)

    if not source_path.is_dir():
        console.print(f"[red]Error: {source_path} is not a directory[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Installing plugin from: {source_path}[/cyan]")

    try:
        # Find plugin information
        plugin_name, plugin_module, entry_point = _find_plugin_info(source_path)

        # Get package name from pyproject.toml if available
        package_name = _get_package_name(source_path) or plugin_module

        # Check if already installed
        if plugin_registry.is_plugin_installed(plugin_name) and not upgrade:
            console.print(f"[yellow]Plugin '{plugin_name}' is already installed[/yellow]")
            if Confirm.ask("[cyan]Upgrade?[/cyan]", default=True):
                upgrade = True
            else:
                console.print("[yellow]Installation cancelled.[/yellow]")
                raise typer.Exit(0)

        # Install plugin in editable mode using uv/pip
        console.print("Installing plugin in editable mode...")

        if HAS_UV:
            cmd = ["uv", "pip", "install", "-e", str(source_path), "--python", sys.executable]
            if upgrade:
                cmd.append("--force-reinstall")
        else:
            cmd = [sys.executable, "-m", "pip", "install", "-e", str(source_path)]
            if upgrade:
                cmd.append("--force-reinstall")

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]Failed to install plugin: {result.stderr}[/red]")
            raise typer.Exit(1)

        # Add to registry
        plugin_registry.register_plugin(
            name=plugin_name,
            source_path=str(source_path),
            package_name=package_name,
            description=_get_plugin_description(source_path),
        )

        console.print(f"[green]✅ Plugin '{plugin_name}' installed successfully![/green]")
        console.print(f"Source: {source_path}")
        console.print(f"\nTry: [cyan]{cli_name} {plugin_name} --help[/cyan]")

    except Exception as e:
        console.print(f"[red]Installation failed: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("upgrade")
def upgrade_plugin(
    name: str = typer.Argument(..., help="Plugin name to upgrade"),
):
    """Force upgrade a plugin from its original source."""
    brand = get_brand()
    cli_name = brand.cli_name

    info = plugin_registry.get_plugin_info(name)

    if not info:
        console.print(f"[red]Plugin '{name}' not installed[/red]")
        raise typer.Exit(1)

    source_path = Path(info["source_path"])

    if not source_path.exists():
        console.print(f"[red]❌ Original source {source_path} no longer exists[/red]")
        console.print(
            f"Please reinstall from new location: [cyan]{cli_name} plugins install <path>[/cyan]"
        )
        raise typer.Exit(1)

    console.print(f"[cyan]Upgrading '{name}' from {source_path}...[/cyan]")

    # Force reinstall
    install_plugin(str(source_path), upgrade=True)


@app.command("remove")
def remove_plugin(
    name: str = typer.Argument(..., help="Plugin name to remove"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Remove a branded CLI plugin."""

    if not plugin_registry.is_plugin_installed(name):
        console.print(f"[red]Plugin '{name}' not found[/red]")
        raise typer.Exit(1)

    if not yes:
        if not Confirm.ask(f"Remove plugin '{name}'?"):
            console.print("[yellow]Cancelled[/yellow]")
            raise typer.Exit(0)

    console.print(f"[cyan]Removing plugin: {name}[/cyan]")

    # Get plugin info for package name
    info = plugin_registry.get_plugin_info(name)
    if not info:
        console.print(f"[red]Plugin '{name}' not found in registry[/red]")
        raise typer.Exit(1)

    package_name = info.get("package_name", info.get("plugin_module", name))

    # Uninstall plugin using uv/pip

    if HAS_UV:
        cmd = ["uv", "pip", "uninstall", package_name, "--python", sys.executable]
    else:
        cmd = [sys.executable, "-m", "pip", "uninstall", "-y", package_name]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        console.print("✅ Plugin package uninstalled")
    else:
        console.print(f"[yellow]⚠️ Could not uninstall package: {result.stderr}[/yellow]")

    # Remove from registry
    if plugin_registry.unregister_plugin(name):
        console.print("✅ Plugin unregistered")

    console.print(f"[green]Plugin '{name}' removed successfully![/green]")


@app.command("update")
def update_plugin(
    name: str = typer.Argument(..., help="Plugin name to update"),
):
    """Alias for upgrade - update a plugin to the latest version."""
    upgrade_plugin(name)


def _find_plugin_info(source_path: Path) -> tuple[str, str, str]:
    """
    Find plugin information from source directory.

    Returns:
        tuple of (plugin_name, plugin_module, entry_point)
    """
    # First try to read from pyproject.toml
    pyproject_path = source_path / "pyproject.toml"
    if pyproject_path.exists():
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)

            # Look for entry points
            entry_points = data.get("project", {}).get("entry-points", {})
            brand = get_brand()
            groups = [brand.plugin_entry_point]
            if "fenix.plugins" not in groups:
                groups.append("fenix.plugins")

            for group in groups:
                group_plugins = entry_points.get(group, {})
                if group_plugins:
                    plugin_name = next(iter(group_plugins))
                    entry_point = group_plugins[plugin_name]
                    module_name = entry_point.split(":")[0].split(".")[0]
                    return plugin_name, module_name, entry_point

    # Fallback: look for common patterns
    # Check for directories that look like plugins
    for item in source_path.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            # Check if it has a cli.py with plugin() function
            cli_path = item / "cli.py"
            if cli_path.exists():
                # Derive plugin name from directory
                if item.name.endswith("_plugin"):
                    plugin_name = item.name.replace("_plugin", "").replace("_", "-")
                else:
                    plugin_name = item.name.replace("_", "-")

                # Ensure it starts with ff- for consistency
                if not plugin_name.startswith("ff-"):
                    plugin_name = f"ff-{plugin_name}"

                return plugin_name, item.name, f"{item.name}.cli:plugin"

    raise ValueError(f"Could not find plugin information in {source_path}")


def _get_plugin_description(source_path: Path) -> str:
    """Get plugin description from pyproject.toml if available."""
    pyproject_path = source_path / "pyproject.toml"
    if pyproject_path.exists():
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                return data.get("project", {}).get("description", "")
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return ""


def _get_package_name(source_path: Path) -> str | None:
    """Get package name from pyproject.toml."""
    pyproject_path = source_path / "pyproject.toml"
    if pyproject_path.exists():
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                return data.get("project", {}).get("name")
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return None
