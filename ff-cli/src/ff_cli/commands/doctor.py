"""Doctor command for comprehensive CLI and environment diagnostics."""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import typer
from rich.table import Table

from ff_cli import __version__, plugin_registry
from ff_cli.branding import get_brand
from ff_cli.plugin_manager import PluginManager
from ff_cli.utils.common import HAS_DOCKER, HAS_GIT, HAS_UV, command_exists, console
from ff_cli.utils.docker import DockerManager

app = typer.Typer()

# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

STATUS_OK = "OK"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"


def _status_icon(status: str) -> str:
    """Return a coloured icon for a check status."""
    if status == STATUS_OK:
        return "[green]OK[/green]"
    elif status == STATUS_WARN:
        return "[yellow]WARN[/yellow]"
    return "[red]FAIL[/red]"


# ---------------------------------------------------------------------------
# Individual diagnostic checks (each returns dict with standard shape)
# ---------------------------------------------------------------------------


def _result(
    name: str,
    status: str,
    detail: str = "",
    recommendations: list[str] | None = None,
    fixable: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "detail": detail,
        "recommendations": recommendations or [],
        "fixable": fixable,
    }


# 1 - Python version
def check_python_version() -> dict[str, Any]:
    ver = sys.version_info
    detail = f"{ver.major}.{ver.minor}.{ver.micro}"
    if ver >= (3, 10):
        return _result("Python version", STATUS_OK, detail)
    return _result(
        "Python version",
        STATUS_FAIL,
        detail,
        ["Python >= 3.10 is required. Please upgrade."],
    )


# 2 - uv availability
def check_uv() -> dict[str, Any]:
    if HAS_UV:
        return _result("uv", STATUS_OK, "available")
    return _result(
        "uv",
        STATUS_WARN,
        "not found",
        ["Install uv for faster operations: pip install uv"],
    )


# 3 - Git availability
def check_git() -> dict[str, Any]:
    if HAS_GIT:
        try:
            result = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
            ver = result.stdout.strip().replace("git version ", "")
            return _result("Git", STATUS_OK, ver)
        except Exception:
            pass
        return _result("Git", STATUS_OK, "available")
    return _result(
        "Git",
        STATUS_FAIL,
        "not found",
        ["Install Git: https://git-scm.com/downloads"],
    )


# 4 - Docker daemon status + version
def check_docker_daemon() -> dict[str, Any]:
    if not HAS_DOCKER:
        return _result(
            "Docker",
            STATUS_FAIL,
            "not installed",
            [
                "Install Docker Desktop: https://docker.com",
                "Or OrbStack (recommended for macOS): https://orbstack.dev",
            ],
        )
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return _result("Docker", STATUS_OK, f"v{result.stdout.strip()}")
        return _result(
            "Docker",
            STATUS_FAIL,
            "daemon not running",
            ["Start Docker Desktop or OrbStack"],
        )
    except Exception as e:
        return _result("Docker", STATUS_FAIL, str(e), ["Ensure Docker daemon is running"])


# 5 - OrbStack detection
def check_orbstack() -> dict[str, Any]:
    orbstack_socket = Path.home() / ".orbstack" / "run" / "docker.sock"
    if orbstack_socket.exists():
        return _result("OrbStack", STATUS_OK, "detected (socket)")

    docker_ctx = os.environ.get("DOCKER_CONTEXT", "")
    if "orbstack" in docker_ctx.lower():
        return _result("OrbStack", STATUS_OK, f"detected (DOCKER_CONTEXT={docker_ctx})")

    try:
        result = subprocess.run(
            ["docker", "context", "show"], capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0 and "orbstack" in result.stdout.strip().lower():
            return _result("OrbStack", STATUS_OK, "detected (docker context)")
    except Exception:
        pass

    return _result("OrbStack", STATUS_WARN, "not detected", ["OrbStack is recommended for macOS"])


# 6 - Config file exists and is valid TOML
def check_config_file() -> dict[str, Any]:
    brand = get_brand()
    config_path = brand.config_dir / "config.toml"

    if not config_path.exists():
        return _result(
            "Config file",
            STATUS_WARN,
            f"{config_path} missing",
            [f"Run: {brand.cli_name} services init"],
            fixable=True,
        )

    try:
        import tomllib

        with open(config_path, "rb") as f:
            tomllib.load(f)
        return _result("Config file", STATUS_OK, str(config_path))
    except Exception as e:
        return _result(
            "Config file",
            STATUS_FAIL,
            f"invalid TOML: {e}",
            [f"Fix or regenerate: {config_path}"],
        )


# 7 - Brand config directory
def check_config_directory() -> dict[str, Any]:
    brand = get_brand()
    config_dir = brand.config_dir

    if config_dir.exists() and config_dir.is_dir():
        return _result("Config directory", STATUS_OK, str(config_dir))

    return _result(
        "Config directory",
        STATUS_FAIL,
        f"{config_dir} missing",
        [f"Run: {brand.cli_name} services init"],
        fixable=True,
    )


# 8 - Docker network
def check_docker_network() -> dict[str, Any]:
    brand = get_brand()

    if not HAS_DOCKER:
        return _result(
            "Docker network",
            STATUS_FAIL,
            "Docker not available",
            ["Install Docker first"],
        )

    try:
        docker = DockerManager()
        network = docker.get_network_status(brand.docker_network)

        if not network.get("exists"):
            return _result(
                "Docker network",
                STATUS_FAIL,
                f"'{brand.docker_network}' not found",
                [f"Create: docker network create {brand.docker_network}"],
                fixable=True,
            )

        containers = network.get("connected_containers", 0)
        return _result(
            "Docker network",
            STATUS_OK,
            f"'{brand.docker_network}' ({containers} containers)",
        )
    except Exception as e:
        return _result(
            "Docker network",
            STATUS_FAIL,
            f"check failed: {e}",
            ["Ensure Docker is running"],
        )


# 9 - Service port conflicts
def check_port_conflicts() -> dict[str, Any]:
    try:
        from ff_cli.services import ServiceManager

        manager = ServiceManager()
        services = manager.list_services()
    except Exception:
        return _result("Port conflicts", STATUS_WARN, "could not load services")

    conflicts: list[str] = []
    for name in services:
        try:
            definition = manager.get_service_definition(name)
            if not definition or not definition.ports:
                continue
            for port_spec in definition.ports:
                host_part = port_spec.split(":")[0].split("/")[0]
                try:
                    host_port = int(host_part)
                except ValueError:
                    continue
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(0.2)
                    if sock.connect_ex(("127.0.0.1", host_port)) == 0:
                        conflicts.append(f"{name}:{port_spec}")
        except Exception:
            continue

    if conflicts:
        return _result(
            "Port conflicts",
            STATUS_WARN,
            f"{len(conflicts)} conflict(s): {', '.join(conflicts)}",
            [f"Check or stop the process using port(s): {', '.join(conflicts)}"],
        )

    return _result("Port conflicts", STATUS_OK, "no conflicts detected")


# 10 - Plugin registry integrity
def check_plugin_registry() -> dict[str, Any]:
    try:
        missing, invalid = plugin_registry.verify_registry()
        issues: list[str] = []
        recs: list[str] = []
        brand = get_brand()

        if missing:
            issues.append(f"{len(missing)} missing package(s)")
            for p in missing:
                recs.append(f"Reinstall plugin: {brand.cli_name} plugins install <path-to-{p}>")
        if invalid:
            issues.append(f"{len(invalid)} invalid path(s)")
            for p in invalid:
                recs.append(f"Remove stale entry: {brand.cli_name} plugins remove {p}")

        if issues:
            return _result(
                "Plugin registry",
                STATUS_WARN,
                "; ".join(issues),
                recs,
            )

        registered = plugin_registry.list_installed_plugins()
        return _result(
            "Plugin registry",
            STATUS_OK,
            f"{len(registered)} plugin(s) registered",
        )
    except Exception as e:
        return _result("Plugin registry", STATUS_FAIL, str(e))


# 11 - Orphaned plugin state directories
def check_orphaned_plugin_dirs() -> dict[str, Any]:
    brand = get_brand()
    plugin_data_dir = brand.config_dir / ".plugin_data"
    plugins_dir = brand.config_dir / "plugins"

    try:
        registered = set(plugin_registry.list_installed_plugins().keys())
    except Exception:
        registered = set()

    orphans: list[str] = []

    for check_dir in [plugin_data_dir, plugins_dir]:
        if not check_dir.exists():
            continue
        for item in check_dir.iterdir():
            if item.is_dir() and item.name not in registered and item.name != "plugins":
                # Skip internal dirs like registry.json's parent
                if item.name in ("registry.json",):
                    continue
                orphans.append(item.name)

    if orphans:
        return _result(
            "Orphaned plugin dirs",
            STATUS_WARN,
            f"{len(orphans)} orphaned: {', '.join(orphans[:5])}",
            ["Consider removing orphaned directories manually"],
        )

    return _result("Orphaned plugin dirs", STATUS_OK, "none found")


# 12 - CLI installation
def check_cli_installation() -> dict[str, Any]:
    status_parts = [f"v{__version__}"]

    try:
        import ff_cli

        cli_path = Path(ff_cli.__file__).parent
        if "site-packages" not in str(cli_path):
            status_parts.append("(editable)")
    except Exception:
        pass

    if HAS_UV:
        status_parts.append("uv")

    return _result("CLI installation", STATUS_OK, " ".join(status_parts))


# 13 - Python environment (venv)
def check_python_environment() -> dict[str, Any]:
    parts: list[str] = []
    if hasattr(sys, "prefix") and sys.prefix != sys.base_prefix:
        venv_name = Path(sys.prefix).name
        parts.append(f"venv: {venv_name}")
    else:
        parts.append("no venv")

    return _result("Python environment", STATUS_OK, ", ".join(parts))


# 14 - Plugin load check
def check_plugin_loading() -> dict[str, Any]:
    brand = get_brand()
    registered = plugin_registry.list_installed_plugins()

    if not registered:
        return _result("Plugin loading", STATUS_OK, "no plugins registered")

    try:
        manager = PluginManager()
        loaded = set(manager.plugins.keys())
    except Exception as e:
        return _result(
            "Plugin loading",
            STATUS_FAIL,
            f"plugin system error: {e}",
        )

    failed = [n for n in registered if n not in loaded]
    if failed:
        return _result(
            "Plugin loading",
            STATUS_WARN,
            f"{len(failed)} failed to load: {', '.join(failed)}",
            [f"Reinstall: {brand.cli_name} plugins install <path>" for _ in failed[:3]],
        )

    return _result("Plugin loading", STATUS_OK, f"{len(loaded)} loaded")


# 15-21 are lighter-weight informational checks


def check_docker_version_compat() -> dict[str, Any]:
    """Check Docker version is reasonably modern."""
    if not HAS_DOCKER:
        return _result("Docker version", STATUS_FAIL, "N/A")
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            ver_str = result.stdout.strip()
            major = int(ver_str.split(".")[0])
            if major >= 20:
                return _result("Docker version", STATUS_OK, f"v{ver_str}")
            return _result(
                "Docker version",
                STATUS_WARN,
                f"v{ver_str} (outdated)",
                ["Consider upgrading Docker to v20+"],
            )
    except Exception:
        pass
    return _result("Docker version", STATUS_WARN, "could not determine")


def check_docker_compose() -> dict[str, Any]:
    """Check if docker compose (v2) is available."""
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            ver = result.stdout.strip()
            return _result("Docker Compose", STATUS_OK, ver)
    except Exception:
        pass
    return _result(
        "Docker Compose",
        STATUS_WARN,
        "not available",
        ["Docker Compose v2 is recommended"],
    )


def check_disk_space() -> dict[str, Any]:
    """Basic disk space check for Docker storage."""
    try:
        import shutil

        total, used, free = shutil.disk_usage("/")
        free_gb = free / (1024**3)
        if free_gb < 5:
            return _result(
                "Disk space",
                STATUS_WARN,
                f"{free_gb:.1f} GB free",
                ["Low disk space may cause Docker build failures"],
            )
        return _result("Disk space", STATUS_OK, f"{free_gb:.1f} GB free")
    except Exception:
        return _result("Disk space", STATUS_WARN, "could not check")


def check_shell_environment() -> dict[str, Any]:
    """Check shell and PATH sanity."""
    shell = os.environ.get("SHELL", "unknown")
    path_dirs = os.environ.get("PATH", "").split(":")
    return _result("Shell", STATUS_OK, f"{Path(shell).name} ({len(path_dirs)} PATH entries)")


def check_docker_buildx() -> dict[str, Any]:
    """Check if docker buildx is available for multi-platform builds."""
    try:
        result = subprocess.run(
            ["docker", "buildx", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            ver = result.stdout.strip()
            return _result("Docker Buildx", STATUS_OK, ver)
    except Exception:
        pass
    return _result(
        "Docker Buildx",
        STATUS_WARN,
        "not available",
        ["Docker Buildx is needed for multi-platform builds"],
    )


def check_terraform() -> dict[str, Any]:
    """Check if terraform is installed."""
    if command_exists("terraform"):
        try:
            result = subprocess.run(
                ["terraform", "version", "-json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                ver = data.get("terraform_version", "unknown")
                return _result("Terraform", STATUS_OK, f"v{ver}")
        except Exception:
            pass
        return _result("Terraform", STATUS_OK, "available")

    return _result(
        "Terraform",
        STATUS_WARN,
        "not installed",
        ["Install from: https://developer.hashicorp.com/terraform/install"],
    )


def check_config_toml_valid() -> dict[str, Any]:
    """Deep-validate config.toml structure."""
    brand = get_brand()
    config_path = brand.config_dir / "config.toml"

    if not config_path.exists():
        return _result("Config TOML validity", STATUS_WARN, "file does not exist")

    try:
        import tomllib

        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        keys_found = list(data.keys())
        return _result(
            "Config TOML validity",
            STATUS_OK,
            f"sections: {', '.join(keys_found) if keys_found else '(empty)'}",
        )
    except Exception as e:
        return _result("Config TOML validity", STATUS_FAIL, f"parse error: {e}")


# ---------------------------------------------------------------------------
# Collect all checks
# ---------------------------------------------------------------------------

ALL_CHECKS = [
    check_python_version,  # 1
    check_uv,  # 2
    check_git,  # 3
    check_docker_daemon,  # 4
    check_orbstack,  # 5
    check_config_file,  # 6
    check_config_directory,  # 7
    check_docker_network,  # 8
    check_port_conflicts,  # 9
    check_plugin_registry,  # 10
    check_orphaned_plugin_dirs,  # 11
    check_cli_installation,  # 12
    check_python_environment,  # 13
    check_plugin_loading,  # 14
    check_docker_version_compat,  # 15
    check_docker_compose,  # 16
    check_disk_space,  # 17
    check_shell_environment,  # 18
    check_docker_buildx,  # 19
    check_terraform,  # 20
    check_config_toml_valid,  # 21
]


# ---------------------------------------------------------------------------
# Auto-fix logic
# ---------------------------------------------------------------------------


def run_auto_fixes(results: list[dict[str, Any]]) -> list[str]:
    """Attempt to fix issues that are marked as fixable.

    Currently supports:
    - Create config directory
    - Create Docker network
    - Create default config file
    """
    brand = get_brand()
    actions: list[str] = []

    # Build a lookup for quick access
    by_name = {r["name"]: r for r in results}

    # Fix: config directory
    config_dir_result = by_name.get("Config directory", {})
    if config_dir_result.get("status") != STATUS_OK:
        try:
            brand.config_dir.mkdir(parents=True, exist_ok=True)
            actions.append(f"Created config directory: {brand.config_dir}")
        except Exception as e:
            actions.append(f"Failed to create config directory: {e}")

    # Fix: config file
    config_file_result = by_name.get("Config file", {})
    if config_file_result.get("status") != STATUS_OK:
        config_path = brand.config_dir / "config.toml"
        if not config_path.exists():
            try:
                brand.config_dir.mkdir(parents=True, exist_ok=True)
                config_path.write_text(
                    "# Fenix CLI configuration\n\n[plugins]\n\n[services]\n\n[settings]\n"
                )
                actions.append(f"Created default config file: {config_path}")
            except Exception as e:
                actions.append(f"Failed to create config file: {e}")

    # Fix: Docker network
    network_result = by_name.get("Docker network", {})
    if network_result.get("status") != STATUS_OK and HAS_DOCKER:
        try:
            docker = DockerManager()
            created = docker.create_network(brand.docker_network)
            if created:
                actions.append(f"Created Docker network: {brand.docker_network}")
            else:
                actions.append(f"Failed to create Docker network: {brand.docker_network}")
        except Exception as e:
            actions.append(f"Network fix failed: {e}")

    return actions


# ---------------------------------------------------------------------------
# Main doctor command
# ---------------------------------------------------------------------------


@app.command()
def doctor(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
    auto_fix: bool = typer.Option(False, "--fix", help="Attempt to fix issues automatically"),
):
    """Run comprehensive diagnostic checks (21-point inspection).

    Checks Python, Docker, Git, networking, configuration, plugins,
    disk space, and toolchain availability. Use --fix to auto-repair
    common issues.
    """
    brand = get_brand()

    # Run all checks
    results: list[dict[str, Any]] = []
    for check_fn in ALL_CHECKS:
        try:
            results.append(check_fn())
        except Exception as e:
            results.append(_result(check_fn.__name__, STATUS_FAIL, f"check error: {e}"))

    # Run auto-fixes if requested
    fix_actions: list[str] = []
    if auto_fix:
        fix_actions = run_auto_fixes(results)

        # Re-run checks after fixes to reflect current state
        if fix_actions:
            results = []
            for check_fn in ALL_CHECKS:
                try:
                    results.append(check_fn())
                except Exception as e:
                    results.append(_result(check_fn.__name__, STATUS_FAIL, f"check error: {e}"))

    # Aggregate
    all_healthy = all(r["status"] == STATUS_OK for r in results)
    all_recommendations: list[str] = []
    for r in results:
        all_recommendations.extend(r.get("recommendations", []))

    fail_count = sum(1 for r in results if r["status"] == STATUS_FAIL)
    warn_count = sum(1 for r in results if r["status"] == STATUS_WARN)
    ok_count = sum(1 for r in results if r["status"] == STATUS_OK)

    if json_output:
        output: dict[str, Any] = {
            "healthy": all_healthy,
            "summary": {"ok": ok_count, "warn": warn_count, "fail": fail_count},
            "checks": results,
            "recommendations": all_recommendations,
            "cli_version": __version__,
        }
        if fix_actions:
            output["fixes_applied"] = fix_actions
        console.print(json.dumps(output, indent=2))
        return

    # Rich table display
    console.print(f"\n[bold cyan]{brand.icon} {brand.cli_display_name} Doctor[/bold cyan]")
    console.print("=" * 60)

    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Check", style="cyan", width=25)
    table.add_column("Status", width=8)
    table.add_column("Details", style="dim")

    for idx, r in enumerate(results, 1):
        table.add_row(
            str(idx),
            r["name"],
            _status_icon(r["status"]),
            r.get("detail", ""),
        )

    console.print(table)

    # Summary line
    console.print("\n" + "-" * 60)
    summary_parts = [f"[green]{ok_count} OK[/green]"]
    if warn_count:
        summary_parts.append(f"[yellow]{warn_count} WARN[/yellow]")
    if fail_count:
        summary_parts.append(f"[red]{fail_count} FAIL[/red]")
    console.print(f"  {' / '.join(summary_parts)}  ({len(results)} checks)")

    if all_healthy:
        console.print("\n[bold green]All systems operational[/bold green]")
    elif fail_count:
        console.print("\n[bold red]Issues detected that require attention[/bold red]")
    else:
        console.print("\n[bold yellow]Some warnings detected[/bold yellow]")

    # Auto-fix actions
    if fix_actions:
        console.print("\n[bold]Auto-fix actions taken:[/bold]")
        for action in fix_actions:
            console.print(f"  + {action}")

    # Recommendations
    if all_recommendations and not all_healthy:
        console.print("\n[bold]Recommendations:[/bold]")
        limit = 10 if verbose else 5
        for rec in all_recommendations[:limit]:
            console.print(f"  - {rec}")
        if len(all_recommendations) > limit:
            remaining = len(all_recommendations) - limit
            console.print(f"  ... and {remaining} more")
            if not verbose:
                console.print("  Run with --verbose to see all")

        if not auto_fix:
            console.print(
                f"\nRun [cyan]{brand.cli_name} doctor --fix[/cyan] to attempt automatic fixes"
            )

    # Verbose: show all recommendations
    if verbose and len(all_recommendations) > 10:
        console.print("\n[dim]All recommendations:[/dim]")
        for rec in all_recommendations[10:]:
            console.print(f"  - {rec}")


__all__ = ["doctor", "app"]
