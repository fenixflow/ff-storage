"""New joiner bootstrapping command for the branded CLI."""

import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.table import Table

from ..branding import get_brand
from ..utils.common import console
from ..utils.docker import DockerManager

brand = get_brand()

app = typer.Typer(
    name="setup",
    help=f"Bootstrap your environment for {brand.cli_display_name}",
    invoke_without_command=True,
)


def _get_version(cmd: list[str]) -> str | None:
    """Run a command and return its stripped stdout, or None on failure."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def _check_python() -> tuple[bool, str]:
    """Check Python >= 3.10 is available."""
    major, minor = sys.version_info.major, sys.version_info.minor
    version = f"{major}.{minor}.{sys.version_info.micro}"
    ok = major >= 3 and minor >= 10
    return ok, version


def _check_tool(name: str) -> tuple[bool, str]:
    """Check if a tool is available via shutil.which and get its version."""
    path = shutil.which(name)
    if not path:
        return False, "not found"

    version_flags = {
        "uv": ["uv", "--version"],
        "git": ["git", "--version"],
        "docker": ["docker", "--version"],
        "node": ["node", "--version"],
    }
    cmd = version_flags.get(name, [name, "--version"])
    version = _get_version(cmd) or "installed"
    return True, version


def _check_orbstack() -> tuple[bool, str]:
    """Check if OrbStack is running."""
    orbstack_socket = Path.home() / ".orbstack" / "run" / "docker.sock"
    if orbstack_socket.exists():
        return True, "running"
    return False, "not detected"


def _check_network() -> tuple[bool, str]:
    """Check if the brand Docker network exists."""
    try:
        docker = DockerManager()
        if docker.network_exists(brand.docker_network):
            return True, brand.docker_network
        return False, f"{brand.docker_network} missing"
    except Exception:
        return False, "docker unavailable"


def _check_config_dir() -> tuple[bool, str]:
    """Check if the brand config directory exists."""
    config_dir = brand.config_dir
    if config_dir.exists():
        return True, str(config_dir).replace(str(Path.home()), "~")
    return False, f"~/{brand.config_dir_name} missing"


@app.callback(invoke_without_command=True)
def setup(
    ctx: typer.Context,
    fix: bool = typer.Option(False, "--fix", help="Create missing directories and network"),
):
    """Check required software and environment for new joiners."""
    if ctx.invoked_subcommand is not None:
        return

    console.print(
        f"\n[bold cyan]{brand.icon} {brand.cli_display_name} Environment Setup[/bold cyan]"
    )
    console.print("=" * 50)

    checks: list[tuple[str, bool, str, bool]] = []  # (name, ok, detail, required)

    # Python
    py_ok, py_ver = _check_python()
    checks.append(("Python (3.10+)", py_ok, py_ver, True))

    # uv
    uv_ok, uv_ver = _check_tool("uv")
    checks.append(("uv", uv_ok, uv_ver, True))

    # git
    git_ok, git_ver = _check_tool("git")
    checks.append(("git", git_ok, git_ver, True))

    # docker
    docker_ok, docker_ver = _check_tool("docker")
    checks.append(("Docker", docker_ok, docker_ver, True))

    # node (optional)
    node_ok, node_ver = _check_tool("node")
    checks.append(("Node.js", node_ok, node_ver, False))

    # OrbStack
    orb_ok, orb_detail = _check_orbstack()
    checks.append(("OrbStack", orb_ok, orb_detail, False))

    # Docker network
    net_ok, net_detail = _check_network()
    checks.append(("Docker network", net_ok, net_detail, True))

    # Config directory
    dir_ok, dir_detail = _check_config_dir()
    checks.append(("Config directory", dir_ok, dir_detail, True))

    # Apply fixes if requested
    fix_actions: list[str] = []
    if fix:
        # Create config directory
        if not dir_ok:
            brand.config_dir.mkdir(parents=True, exist_ok=True)
            fix_actions.append(f"Created {brand.config_dir}")
            dir_ok = True
            dir_detail = str(brand.config_dir).replace(str(Path.home()), "~")
            # Update the check
            checks = [
                (n, o, d, r) if n != "Config directory" else (n, dir_ok, dir_detail, r)
                for n, o, d, r in checks
            ]

        # Create Docker network
        if not net_ok and docker_ok:
            try:
                docker = DockerManager()
                if docker.create_network(brand.docker_network):
                    fix_actions.append(f"Created network {brand.docker_network}")
                    net_ok = True
                    net_detail = brand.docker_network
                    checks = [
                        (n, o, d, r) if n != "Docker network" else (n, net_ok, net_detail, r)
                        for n, o, d, r in checks
                    ]
            except Exception as e:
                fix_actions.append(f"Failed to create network: {e}")

    # Display results
    table = Table(show_header=True, header_style="bold")
    table.add_column("Component", style="cyan", width=20)
    table.add_column("Status", width=6, justify="center")
    table.add_column("Details", style="dim")
    table.add_column("Required", width=8, justify="center")

    all_required_ok = True
    for name, ok, detail, required in checks:
        icon = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
        req_label = "yes" if required else "[dim]no[/dim]"
        table.add_row(name, icon, detail, req_label)
        if required and not ok:
            all_required_ok = False

    console.print(table)

    # Fix actions
    if fix_actions:
        console.print("\n[bold]Actions taken:[/bold]")
        for action in fix_actions:
            console.print(f"  [green]+[/green] {action}")

    # Summary
    console.print("\n" + "-" * 50)
    if all_required_ok:
        console.print("[bold green]All required checks passed[/bold green]")
    else:
        console.print("[bold red]Some required checks failed[/bold red]")
        if not fix:
            console.print(
                f"Run [cyan]{brand.cli_name} setup --fix[/cyan] to create missing directories and network"
            )
