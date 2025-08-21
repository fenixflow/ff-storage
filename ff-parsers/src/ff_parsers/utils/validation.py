"""
File validation utilities for ff-parsers.
"""

from pathlib import Path
from typing import Optional, Union
import mimetypes

# Try to import magic, but make it optional
try:
    import magic

    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False


def get_mime_type(file_path: Union[str, Path]) -> Optional[str]:
    """
    Get MIME type of a file using python-magic if available, otherwise mimetypes.

    Args:
        file_path: Path to the file

    Returns:
        MIME type string or None if cannot be determined
    """
    try:
        file_path = Path(file_path)
        if not file_path.exists():
            return None

        # Try python-magic first if available (more accurate)
        if HAS_MAGIC:
            try:
                mime = magic.from_file(str(file_path), mime=True)
                return mime
            except Exception:
                pass

        # Fall back to mimetypes module
        mime_type, _ = mimetypes.guess_type(str(file_path))
        return mime_type
    except Exception:
        return None


def detect_file_type(file_path: Union[str, Path]) -> Optional[str]:
    """
    Detect file type based on content and extension.

    Args:
        file_path: Path to the file

    Returns:
        File type string (e.g., 'pdf', 'excel', 'word', 'email', 'text')
    """
    file_path = Path(file_path)

    if not file_path.exists():
        return None

    # Get MIME type
    mime_type = get_mime_type(file_path)

    # Map MIME types to our file types
    mime_mapping = {
        "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "excel",
        "application/vnd.ms-excel": "excel",
        "text/csv": "csv",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word",
        "application/msword": "word",
        "message/rfc822": "email",
        "text/plain": "text",
        "text/html": "html",
    }

    if mime_type in mime_mapping:
        return mime_mapping[mime_type]

    # Fall back to extension-based detection
    extension = file_path.suffix.lower()
    extension_mapping = {
        ".pdf": "pdf",
        ".xlsx": "excel",
        ".xls": "excel",
        ".csv": "csv",
        ".docx": "word",
        ".doc": "word",
        ".eml": "email",
        ".msg": "email",
        ".txt": "text",
        ".html": "html",
        ".htm": "html",
    }

    return extension_mapping.get(extension)


def is_valid_file(file_path: Union[str, Path], expected_type: Optional[str] = None) -> bool:
    """
    Check if a file is valid and optionally matches expected type.

    Args:
        file_path: Path to the file
        expected_type: Expected file type (e.g., 'pdf', 'excel')

    Returns:
        True if file is valid, False otherwise
    """
    file_path = Path(file_path)

    # Check file exists and is a file
    if not file_path.exists() or not file_path.is_file():
        return False

    # Check file is not empty
    if file_path.stat().st_size == 0:
        return False

    # If expected type is specified, verify it matches
    if expected_type:
        detected_type = detect_file_type(file_path)
        if detected_type != expected_type:
            return False

    return True


def estimate_file_complexity(file_path: Union[str, Path]) -> str:
    """
    Estimate the complexity of parsing a file based on size and type.

    Args:
        file_path: Path to the file

    Returns:
        Complexity level: 'simple', 'moderate', or 'complex'
    """
    file_path = Path(file_path)

    if not file_path.exists():
        return "unknown"

    size_mb = file_path.stat().st_size / (1024 * 1024)
    file_type = detect_file_type(file_path)

    # Size-based thresholds
    if size_mb < 1:
        size_complexity = "simple"
    elif size_mb < 10:
        size_complexity = "moderate"
    else:
        size_complexity = "complex"

    # Type-based complexity
    type_complexity = {
        "text": "simple",
        "csv": "simple",
        "email": "moderate",
        "word": "moderate",
        "excel": "moderate",
        "pdf": "complex",
        "html": "moderate",
    }.get(file_type, "moderate")

    # Return the higher complexity
    if size_complexity == "complex" or type_complexity == "complex":
        return "complex"
    elif size_complexity == "moderate" or type_complexity == "moderate":
        return "moderate"
    else:
        return "simple"
