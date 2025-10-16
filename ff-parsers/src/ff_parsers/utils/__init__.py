"""
Utility functions for ff-parsers.
"""

from .attachments import (
    compute_sha256,
    normalise_filename,
    persist_attachment_bytes,
    split_extension,
)
from .cleaning import clean_text, normalize_whitespace, remove_control_characters
from .temp_file_manager import managed_temp_dir, managed_temp_file
from .validation import detect_file_type, get_mime_type, is_valid_file

__all__ = [
    "clean_text",
    "normalize_whitespace",
    "remove_control_characters",
    "is_valid_file",
    "detect_file_type",
    "get_mime_type",
    "compute_sha256",
    "normalise_filename",
    "persist_attachment_bytes",
    "split_extension",
    "managed_temp_file",
    "managed_temp_dir",
]
