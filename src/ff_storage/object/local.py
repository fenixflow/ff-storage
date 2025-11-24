"""
Local filesystem implementation of the ObjectStorage interface.
Provides async file operations with atomic writes and metadata management.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional

import aiofiles
import aiofiles.os

from .base import ObjectStorage


class LocalObjectStorage(ObjectStorage):
    """
    Local filesystem storage backend.

    Stores objects as files and metadata as JSON sidecar files.
    Implements atomic writes using temporary files and rename operations.

    Example:
        >>> storage = LocalObjectStorage("/var/storage")
        >>> await storage.write("docs/report.pdf", pdf_bytes, {"author": "John"})
        >>> data = await storage.read("docs/report.pdf")
        >>> metadata = await storage.get_metadata("docs/report.pdf")
    """

    METADATA_SUFFIX = ".meta.json"

    def __init__(self, base_path: str):
        """
        Initialize local storage with a base directory.

        Args:
            base_path: The root directory for storage
        """
        self.base_path = Path(base_path).resolve()
        # Create base directory if it doesn't exist
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _validate_key(self, key: str) -> Path:
        """
        Validate and resolve a storage key to a safe file path.

        Args:
            key: The storage key

        Returns:
            Resolved path

        Raises:
            ValueError: If the key would escape the base path
        """
        # Remove leading slashes and normalize
        clean_key = key.lstrip("/")

        # Resolve the full path
        full_path = (self.base_path / clean_key).resolve()

        # Ensure the path is within our base directory (prevent traversal)
        if not str(full_path).startswith(str(self.base_path)):
            raise ValueError(f"Invalid key: {key} (path traversal detected)")

        return full_path

    def _get_metadata_path(self, file_path: Path) -> Path:
        """Get the metadata file path for a given file."""
        return Path(str(file_path) + self.METADATA_SUFFIX)

    async def write(self, key: str, data: bytes, metadata: Optional[Dict[str, str]] = None) -> bool:
        """
        Write data to local filesystem with atomic operation.

        Uses temporary file + rename for atomicity.
        """
        # Validate key first, let ValueError propagate
        file_path = self._validate_key(key)

        try:
            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write to temporary file first (atomic write)
            with tempfile.NamedTemporaryFile(
                dir=file_path.parent, delete=False, prefix=f".{file_path.name}.", suffix=".tmp"
            ) as tmp_file:
                tmp_path = Path(tmp_file.name)

            # Write data to temp file
            async with aiofiles.open(tmp_path, "wb") as f:
                await f.write(data)

            # Atomically replace the target file
            await aiofiles.os.rename(tmp_path, file_path)

            # Write metadata if provided
            if metadata:
                await self._write_metadata(file_path, metadata)

            return True

        except Exception as e:
            # Clean up temp file if it exists
            try:
                if "tmp_path" in locals():
                    await aiofiles.os.remove(tmp_path)
            except Exception:
                pass
            raise IOError(f"Failed to write {key}: {e}")

    async def _write_metadata(self, file_path: Path, metadata: Dict[str, str]) -> None:
        """Write metadata to a JSON sidecar file atomically."""
        meta_path = self._get_metadata_path(file_path)

        # Write to temp file first
        with tempfile.NamedTemporaryFile(
            dir=file_path.parent,
            delete=False,
            prefix=f".{meta_path.name}.",
            suffix=".tmp",
            mode="w",
        ) as tmp_file:
            json.dump(metadata, tmp_file, indent=2)
            tmp_path = Path(tmp_file.name)

        # Atomically replace
        await aiofiles.os.rename(tmp_path, meta_path)

    async def read(self, key: str) -> bytes:
        """Read data from local filesystem."""
        try:
            file_path = self._validate_key(key)

            if not await aiofiles.os.path.exists(file_path):
                raise KeyError(f"Key not found: {key}")

            async with aiofiles.open(file_path, "rb") as f:
                return await f.read()

        except KeyError:
            raise
        except Exception as e:
            raise IOError(f"Failed to read {key}: {e}")

    async def read_stream(self, key: str, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        """Read data as a stream of chunks."""
        try:
            file_path = self._validate_key(key)

            if not await aiofiles.os.path.exists(file_path):
                raise KeyError(f"Key not found: {key}")

            async with aiofiles.open(file_path, "rb") as f:
                while True:
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

        except KeyError:
            raise
        except Exception as e:
            raise IOError(f"Failed to stream {key}: {e}")

    async def exists(self, key: str) -> bool:
        """Check if a file exists."""
        try:
            file_path = self._validate_key(key)
            return await aiofiles.os.path.exists(file_path)
        except ValueError:
            return False

    async def delete(self, key: str) -> bool:
        """Delete a file and its metadata."""
        try:
            file_path = self._validate_key(key)
            meta_path = self._get_metadata_path(file_path)

            # Delete the main file
            if await aiofiles.os.path.exists(file_path):
                await aiofiles.os.remove(file_path)

            # Delete metadata if it exists
            if await aiofiles.os.path.exists(meta_path):
                await aiofiles.os.remove(meta_path)

            # Clean up empty parent directories
            await self._cleanup_empty_dirs(file_path.parent)

            return True

        except Exception as e:
            raise IOError(f"Failed to delete {key}: {e}")

    async def _cleanup_empty_dirs(self, dir_path: Path) -> None:
        """Remove empty directories up to base path."""
        try:
            while dir_path != self.base_path:
                if not any(dir_path.iterdir()):
                    await aiofiles.os.rmdir(dir_path)
                    dir_path = dir_path.parent
                else:
                    break
        except Exception:
            pass  # Ignore errors in cleanup

    async def list_keys(self, prefix: str = "", limit: int = 1000) -> List[str]:
        """List files with optional prefix filter."""
        try:
            keys = []
            prefix_path = self.base_path / prefix.lstrip("/")

            # Walk the directory tree
            for root, dirs, files in os.walk(prefix_path):
                for file in files:
                    # Skip metadata files
                    if file.endswith(self.METADATA_SUFFIX):
                        continue

                    # Get relative path from base
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(self.base_path)
                    keys.append(str(rel_path))

                    if len(keys) >= limit:
                        return keys

            return keys

        except Exception as e:
            raise IOError(f"Failed to list keys: {e}")

    async def get_metadata(self, key: str) -> Dict[str, str]:
        """Get metadata for a file."""
        try:
            file_path = self._validate_key(key)

            if not await aiofiles.os.path.exists(file_path):
                raise KeyError(f"Key not found: {key}")

            meta_path = self._get_metadata_path(file_path)

            if not await aiofiles.os.path.exists(meta_path):
                return {}

            async with aiofiles.open(meta_path, "r") as f:
                content = await f.read()
                return json.loads(content)

        except KeyError:
            raise
        except Exception as e:
            raise IOError(f"Failed to get metadata for {key}: {e}")

    async def update_metadata(self, key: str, metadata: Dict[str, str]) -> bool:
        """Update metadata for a file."""
        try:
            file_path = self._validate_key(key)

            if not await aiofiles.os.path.exists(file_path):
                raise KeyError(f"Key not found: {key}")

            await self._write_metadata(file_path, metadata)
            return True

        except KeyError:
            raise
        except Exception as e:
            raise IOError(f"Failed to update metadata for {key}: {e}")

    async def get_size(self, key: str) -> int:
        """Get the size of a file in bytes."""
        try:
            file_path = self._validate_key(key)

            if not await aiofiles.os.path.exists(file_path):
                raise KeyError(f"Key not found: {key}")

            stat = await aiofiles.os.stat(file_path)
            return stat.st_size

        except KeyError:
            raise
        except Exception as e:
            raise IOError(f"Failed to get size for {key}: {e}")

    async def write_stream(
        self, key: str, stream: AsyncIterator[bytes], metadata: Optional[Dict[str, str]] = None
    ) -> bool:
        """Write data from a stream with atomic operation."""
        try:
            file_path = self._validate_key(key)

            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write to temporary file first
            with tempfile.NamedTemporaryFile(
                dir=file_path.parent, delete=False, prefix=f".{file_path.name}.", suffix=".tmp"
            ) as tmp_file:
                tmp_path = Path(tmp_file.name)

            # Stream data to temp file
            async with aiofiles.open(tmp_path, "wb") as f:
                async for chunk in stream:
                    await f.write(chunk)

            # Atomically replace the target file
            await aiofiles.os.rename(tmp_path, file_path)

            # Write metadata if provided
            if metadata:
                await self._write_metadata(file_path, metadata)

            return True

        except Exception as e:
            # Clean up temp file if it exists
            try:
                if "tmp_path" in locals():
                    await aiofiles.os.remove(tmp_path)
            except Exception:
                pass
            raise IOError(f"Failed to write stream to {key}: {e}")
