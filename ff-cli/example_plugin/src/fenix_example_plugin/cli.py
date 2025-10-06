"""
Example CLI plugin for Fenix.

This demonstrates how to create a plugin that adds commands to the Fenix CLI.
"""

import typer
from rich.console import Console

console = Console()

# Create the Typer app for this plugin
app = typer.Typer(
    help="Example plugin demonstrating Fenix CLI plugin architecture",
    no_args_is_help=True,
)


@app.command()
def hello(name: str = typer.Argument("World", help="Name to greet")):
    """Say hello to someone."""
    console.print(f"[bold green]Hello, {name}![/bold green]")
    console.print("This is an example command from the ff-example plugin.")


@app.command()
def status():
    """Show example plugin status."""
    console.print("[bold cyan]Example Plugin Status[/bold cyan]")
    console.print("✅ Plugin is loaded and working")
    console.print("📦 Version: 0.1.0")
    console.print("🔧 This is a demonstration plugin")


@app.command()
def config(
    get: str = typer.Option(None, "--get", help="Get a configuration value"),
    set_key: str = typer.Option(None, "--set", help="Set a configuration key"),
    value: str = typer.Option(None, "--value", help="Configuration value to set"),
):
    """Manage example plugin configuration."""
    if get:
        console.print(f"[cyan]Getting config value for: {get}[/cyan]")
        # In a real plugin, this would read from actual config
        console.print("Value: example_value")
    elif set_key and value:
        console.print(f"[cyan]Setting {set_key} = {value}[/cyan]")
        # In a real plugin, this would save to actual config
        console.print("[green]Configuration updated[/green]")
    else:
        console.print("[yellow]Use --get KEY or --set KEY --value VALUE[/yellow]")


@app.command()
def run(
    task: str = typer.Argument(..., help="Task to run"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Run an example task."""
    console.print(f"[cyan]Running task: {task}[/cyan]")

    if verbose:
        console.print("[dim]Verbose mode enabled[/dim]")
        console.print("[dim]Step 1: Initializing...[/dim]")
        console.print("[dim]Step 2: Processing...[/dim]")
        console.print("[dim]Step 3: Completing...[/dim]")

    console.print(f"[green]✅ Task '{task}' completed successfully![/green]")


def plugin():
    """Entry point for the plugin.

    This function is called by Fenix CLI to get the Typer app for this plugin.
    It's registered in pyproject.toml under [project.entry-points."fenix.plugins"].

    Returns:
        typer.Typer: The Typer app with all plugin commands
    """
    return app
