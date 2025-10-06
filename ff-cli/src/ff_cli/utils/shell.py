"""Shell command utilities."""

import os
import shutil
import subprocess
from pathlib import Path

from ff_cli.config import get_logger
from ff_cli.utils.common import console

logger = get_logger("shell")


def check_command_exists(command: str) -> bool:
    """Check if a command exists in the system PATH."""
    return shutil.which(command) is not None


def run_command(
    command: list[str] | str,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    capture_output: bool = True,
    timeout: int | None = None,
    shell: bool = False,
) -> subprocess.CompletedProcess:
    """Run a shell command with optional parameters.

    Args:
        command: Command to run (list or string)
        cwd: Working directory for the command
        env: Environment variables to set
        capture_output: Whether to capture stdout/stderr
        timeout: Command timeout in seconds
        shell: Whether to run through shell

    Returns:
        CompletedProcess instance with results
    """
    if isinstance(command, str) and not shell:
        command = command.split()

    # Merge environment variables with current environment
    if env:
        full_env = os.environ.copy()
        full_env.update(env)
    else:
        full_env = None

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=full_env,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
            shell=shell,
        )
        return result
    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out: {e}")
        raise
    except subprocess.SubprocessError as e:
        logger.error(f"Command failed: {e}")
        raise


def run_command_with_progress(
    command: list[str] | str,
    description: str,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    """Run a command with progress display.

    Args:
        command: Command to run
        description: Description to show during execution
        cwd: Working directory
        env: Environment variables

    Returns:
        True if successful, False otherwise
    """
    with console.status(f"[cyan]{description}[/cyan]"):
        try:
            result = run_command(
                command,
                cwd=cwd,
                env=env,
                capture_output=True,
            )
            if result.returncode == 0:
                console.print(f"[green]✅ {description}[/green]")
                return True
            else:
                console.print(f"[red]❌ {description} failed[/red]")
                if result.stderr:
                    console.print(f"[red]{result.stderr}[/red]")
                return False
        except Exception as e:
            console.print(f"[red]❌ {description} failed: {e}[/red]")
            return False


def get_command_output(
    command: list[str] | str,
    default: str = "",
    cwd: Path | str | None = None,
) -> str:
    """Get the output of a command, returning a default on failure.

    Args:
        command: Command to run
        default: Default value if command fails
        cwd: Working directory

    Returns:
        Command output or default value
    """
    try:
        result = run_command(command, cwd=cwd, capture_output=True)
        if result.returncode == 0:
            return result.stdout.strip()
        return default
    except Exception:
        return default


def run_interactive_command(
    command: list[str] | str,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
) -> int:
    """Run an interactive command that requires user input.

    Args:
        command: Command to run
        cwd: Working directory
        env: Environment variables

    Returns:
        Exit code of the command
    """
    if isinstance(command, str):
        command = command.split()

    # Merge environment variables
    if env:
        full_env = os.environ.copy()
        full_env.update(env)
    else:
        full_env = None

    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=full_env,
            stdin=None,  # Use parent's stdin
            stdout=None,  # Use parent's stdout
            stderr=None,  # Use parent's stderr
        )
        return process.wait()
    except Exception as e:
        logger.error(f"Failed to run interactive command: {e}")
        return 1


def find_executable(name: str, paths: list[Path] | None = None) -> Path | None:
    """Find an executable in system PATH or specified paths.

    Args:
        name: Name of the executable
        paths: Additional paths to search

    Returns:
        Path to executable or None if not found
    """
    # Check system PATH first
    system_path = shutil.which(name)
    if system_path:
        return Path(system_path)

    # Check additional paths
    if paths:
        for path in paths:
            if path.is_dir():
                for exe_path in path.iterdir():
                    if (
                        exe_path.name == name
                        and exe_path.is_file()
                        and os.access(exe_path, os.X_OK)
                    ):
                        return exe_path

    return None


def is_command_available(command: str) -> bool:
    """Check if a command is available and executable.

    Args:
        command: Command to check

    Returns:
        True if command is available
    """
    return check_command_exists(command)


def get_shell() -> str:
    """Get the user's default shell.

    Returns:
        Shell command (e.g., 'bash', 'zsh', 'fish')
    """
    # Try SHELL environment variable first
    shell_env = os.environ.get("SHELL", "").lower()
    if shell_env:
        return Path(shell_env).name

    # Fallback to common shells
    for shell in ["zsh", "bash", "fish", "sh"]:
        if check_command_exists(shell):
            return shell

    return "sh"  # Final fallback


def execute_in_shell(
    command: str,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[bool, str, str]:
    """Execute a command in the user's shell.

    Args:
        command: Command string to execute
        cwd: Working directory
        env: Environment variables

    Returns:
        Tuple of (success, stdout, stderr)
    """
    try:
        result = run_command(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            shell=True,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)
