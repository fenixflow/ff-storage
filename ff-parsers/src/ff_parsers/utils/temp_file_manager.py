"""
Temporary file management utilities.

Provides context managers for safe temporary file handling with guaranteed cleanup.
"""

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


@contextmanager
def managed_temp_file(
    suffix: str = "", prefix: str = "ff_parser_", delete_on_error: bool = True
) -> Generator[Path, None, None]:
    """
    Context manager for temporary files with guaranteed cleanup.

    Ensures temporary files are properly cleaned up even if exceptions occur.
    This consolidates the repeated pattern of creating temp files throughout
    the codebase.

    Args:
        suffix: File extension suffix (e.g., ".png", ".pdf")
        prefix: Filename prefix for identification
        delete_on_error: Whether to delete temp file if exception occurs (default: True)

    Yields:
        Path: Path object pointing to the temporary file

    Example:
        ```python
        with managed_temp_file(suffix=".png") as tmp_path:
            # Use tmp_path for operations
            img.save(tmp_path)
            result = process_image(tmp_path)
        # File automatically deleted after context exits
        ```
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, prefix=prefix, delete=False) as tmp:
            tmp_path = Path(tmp.name)
        yield tmp_path
    except Exception:
        # Re-raise exception after cleanup
        if delete_on_error and tmp_path and tmp_path.exists():
            tmp_path.unlink()
        raise
    finally:
        # Always cleanup on normal exit
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()


@contextmanager
def managed_temp_dir(prefix: str = "ff_parser_") -> Generator[Path, None, None]:
    """
    Context manager for temporary directories with guaranteed cleanup.

    Args:
        prefix: Directory name prefix for identification

    Yields:
        Path: Path object pointing to the temporary directory

    Example:
        ```python
        with managed_temp_dir() as tmp_dir:
            # Create files in tmp_dir
            (tmp_dir / "file1.txt").write_text("content")
        # Directory and all contents automatically deleted
        ```
    """
    tmp_dir = None
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        yield tmp_dir
    finally:
        # Cleanup directory and all contents
        if tmp_dir and tmp_dir.exists():
            import shutil

            shutil.rmtree(tmp_dir)
