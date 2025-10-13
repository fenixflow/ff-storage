"""
Helpers for hashing, normalising, and persisting attachment assets.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Optional, Tuple


_FILENAME_SANITIZER = re.compile(r"[^A-Za-z0-9._-]+")


def compute_sha256(data: bytes) -> str:
    """Return the SHA-256 hex digest for the provided bytes."""
    sha = hashlib.sha256()
    sha.update(data)
    return sha.hexdigest()


def normalise_filename(name: str, default_stem: str = "asset") -> str:
    """
    Produce a filesystem-friendly filename.

    Keeps alphanumeric characters plus '.', '_', and '-'. Any other character is replaced
    with '-'. Lowercases the result to keep things deterministic.
    """
    stem = name or default_stem
    stem = stem.strip()
    if not stem:
        stem = default_stem

    stem = _FILENAME_SANITIZER.sub("-", stem)
    stem = stem.strip("-").lower()
    return stem or default_stem


def split_extension(name: str) -> Tuple[str, str]:
    """Split a filename into stem and extension (including dot)."""
    stem, ext = os.path.splitext(name)
    return stem, ext.lower()


def build_deterministic_filename(name: str, sha256: str) -> str:
    """
    Construct a deterministic filename using the provided name and hash.

    Format: ``<sanitised-name>-<hash-prefix><extension>``. The hash prefix keeps filenames
    unique and is short enough to be readable when inspected manually.
    """
    stem, ext = split_extension(name)
    slug = normalise_filename(stem or "attachment")
    prefix = sha256[:10]
    return f"{slug}-{prefix}{ext or ''}"


def ensure_directory(root: Path) -> Path:
    """Create the directory when it does not exist and return it."""
    root.mkdir(parents=True, exist_ok=True)
    return root


def persist_attachment_bytes(
    data: bytes, output_root: Path, filename: Optional[str] = None
) -> Path:
    """
    Persist attachment bytes to disk using a deterministic filename.

    Args:
        data: Attachment payload
        output_root: Base directory to store attachments under
        filename: Preferred filename; when omitted, the SHA hash is used
    """
    ensure_directory(output_root)
    sha256 = compute_sha256(data)
    if filename:
        sanitised = build_deterministic_filename(filename, sha256)
    else:
        sanitised = f"attachment-{sha256[:16]}"

    path = output_root / sanitised
    path.write_bytes(data)
    return path
