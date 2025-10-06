"""Editor utilities for opening files in the user's preferred editor."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ff_cli.config import get_logger, get_settings
from ff_cli.utils.common import console

logger = get_logger("editor")


def get_editor() -> str:
    """Get the user's preferred editor.

    Returns:
        Editor command to use
    """
    settings = get_settings()

    # Check settings first
    if settings.editor_command:
        return settings.editor_command

    # Check environment variables
    for env_var in ["VISUAL", "EDITOR"]:
        editor = os.environ.get(env_var)
        if editor:
            return editor

    # Fallback to common editors
    common_editors = [
        "code",  # VS Code
        "vim",
        "vi",
        "nano",
        "emacs",
        "subl",  # Sublime Text
        "atom",
        "gedit",
        "notepad",  # Windows
    ]

    for editor in common_editors:
        if shutil.which(editor):
            return editor

    # Final fallback
    return "vi"


def open_in_editor(file_path: Path | str) -> bool:
    """Open a file in the user's editor.

    Args:
        file_path: Path to the file to open

    Returns:
        True if successful, False otherwise
    """
    editor = get_editor()
    file_path = Path(file_path)

    # Ensure file exists
    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return False

    try:
        # Special handling for VS Code and similar editors
        if "code" in editor.lower():
            subprocess.run([editor, "--wait", str(file_path)])
        else:
            subprocess.run([editor, str(file_path)])
        return True
    except Exception as e:
        logger.error(f"Failed to open editor: {e}")
        console.print(f"[red]Failed to open editor: {e}[/red]")
        return False


def edit_text(initial_content: str = "", suffix: str = ".txt") -> str | None:
    """Open a temporary file in the editor for text input.

    Args:
        initial_content: Initial text to populate the file
        suffix: File suffix for syntax highlighting

    Returns:
        Edited text or None if editing failed
    """
    editor = get_editor()

    # Create temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as tmp:
        tmp.write(initial_content)
        tmp_path = Path(tmp.name)

    try:
        # Open in editor
        if "code" in editor.lower():
            result = subprocess.run([editor, "--wait", str(tmp_path)])
        else:
            result = subprocess.run([editor, str(tmp_path)])

        if result.returncode != 0:
            console.print("[red]Editor exited with error[/red]")
            return None

        # Read the edited content
        with open(tmp_path) as f:
            content = f.read()

        return content

    except Exception as e:
        logger.error(f"Failed to edit text: {e}")
        console.print(f"[red]Failed to edit text: {e}[/red]")
        return None

    finally:
        # Clean up temporary file
        try:
            tmp_path.unlink()
        except Exception:
            pass


def edit_yaml(initial_content: str = "") -> str | None:
    """Edit YAML content in the user's editor.

    Args:
        initial_content: Initial YAML content

    Returns:
        Edited YAML content or None
    """
    return edit_text(initial_content, suffix=".yaml")


def edit_json(initial_content: str = "") -> str | None:
    """Edit JSON content in the user's editor.

    Args:
        initial_content: Initial JSON content

    Returns:
        Edited JSON content or None
    """
    return edit_text(initial_content, suffix=".json")


def edit_toml(initial_content: str = "") -> str | None:
    """Edit TOML content in the user's editor.

    Args:
        initial_content: Initial TOML content

    Returns:
        Edited TOML content or None
    """
    return edit_text(initial_content, suffix=".toml")


def edit_python(initial_content: str = "") -> str | None:
    """Edit Python code in the user's editor.

    Args:
        initial_content: Initial Python code

    Returns:
        Edited Python code or None
    """
    return edit_text(initial_content, suffix=".py")


def create_and_edit(
    file_path: Path | str,
    template: str = "",
    create_dirs: bool = True,
) -> bool:
    """Create a new file with optional template and open in editor.

    Args:
        file_path: Path to the file to create
        template: Template content for the file
        create_dirs: Whether to create parent directories

    Returns:
        True if successful
    """
    file_path = Path(file_path)

    # Create parent directories if needed
    if create_dirs:
        file_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if file already exists
    if file_path.exists():
        response = console.input(f"[yellow]File {file_path} exists. Overwrite? [y/N]: [/yellow]")
        if response.lower() != "y":
            return False

    try:
        # Write template content
        with open(file_path, "w") as f:
            f.write(template)

        # Open in editor
        return open_in_editor(file_path)

    except Exception as e:
        logger.error(f"Failed to create and edit file: {e}")
        console.print(f"[red]Failed to create file: {e}[/red]")
        return False
