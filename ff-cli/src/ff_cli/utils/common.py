"""Common utilities shared across the CLI."""

import subprocess
from functools import lru_cache

from rich.console import Console

# Single shared console instance for the entire CLI
console = Console()


@lru_cache(maxsize=8)
def command_exists(cmd: str) -> bool:
    """Check if a command exists in the system PATH.

    Args:
        cmd: Command name to check (e.g., 'uv', 'docker')

    Returns:
        True if command exists, False otherwise
    """
    try:
        result = subprocess.run(["which", cmd], capture_output=True, text=True, timeout=2)
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def run_command(
    cmd: list[str],
    *,
    check: bool = False,
    capture: bool = True,
    timeout: int | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Unified subprocess runner with consistent error handling.

    Args:
        cmd: Command and arguments as list
        check: Raise exception on non-zero exit
        capture: Capture stdout/stderr
        timeout: Command timeout in seconds
        cwd: Working directory
        env: Environment variables

    Returns:
        CompletedProcess instance
    """
    try:
        return subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            check=check,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Command failed: {' '.join(cmd)}[/red]")
        console.print(f"[red]Exit code: {e.returncode}[/red]")
        if e.stderr:
            console.print(f"[red]Error: {e.stderr}[/red]")
        raise
    except subprocess.TimeoutExpired:
        console.print(f"[red]Command timed out: {' '.join(cmd)}[/red]")
        raise
    except FileNotFoundError:
        console.print(f"[red]Command not found: {cmd[0]}[/red]")
        raise


# Pre-check common commands at import time
HAS_UV = command_exists("uv")
HAS_DOCKER = command_exists("docker")
HAS_GIT = command_exists("git")


def get_git_config(key: str, default: str = "") -> str:
    """Get a git configuration value.

    Args:
        key: Git config key (e.g., 'user.name', 'user.email')
        default: Default value if not available

    Returns:
        Git config value or default
    """
    if not HAS_GIT:
        return default

    try:
        result = run_command(["git", "config", "--get", key], capture=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return default


def handle_error(exc: Exception, message: str | None = None) -> None:
    """Consistent error handling and display.

    Args:
        exc: Exception to handle
        message: Optional custom message
    """
    if message:
        console.print(f"[red]{message}[/red]")
    console.print(f"[red]Error: {exc}[/red]")


# Export all utilities
__all__ = [
    "console",
    "command_exists",
    "run_command",
    "get_git_config",
    "handle_error",
    "HAS_UV",
    "HAS_DOCKER",
    "HAS_GIT",
]
