"""
Abstract base class for object storage backends.
Provides a consistent interface for different storage implementations.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Optional


class ObjectStorage(ABC):
    """
    Abstract base class for object storage backends.

    All methods are async to support non-blocking I/O operations.
    Implementations should handle their own connection pooling and error handling.

    Example:
        >>> storage = LocalObjectStorage("/path/to/storage")
        >>> await storage.write("documents/file.pdf", data, {"content-type": "application/pdf"})
        >>> data = await storage.read("documents/file.pdf")
        >>> exists = await storage.exists("documents/file.pdf")
    """

    @abstractmethod
    async def write(self, key: str, data: bytes, metadata: Optional[Dict[str, str]] = None) -> bool:
        """
        Write data to storage with optional metadata.

        Args:
            key: The storage key/path for the object
            data: The bytes to store
            metadata: Optional metadata dictionary

        Returns:
            True if successful, False otherwise

        Raises:
            ValueError: If the key is invalid
            IOError: If write operation fails
        """
        pass

    @abstractmethod
    async def read(self, key: str) -> bytes:
        """
        Read data from storage.

        Args:
            key: The storage key/path for the object

        Returns:
            The stored bytes

        Raises:
            KeyError: If the key doesn't exist
            IOError: If read operation fails
        """
        pass

    @abstractmethod
    async def read_stream(self, key: str, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        """
        Read data from storage as a stream of chunks.

        Args:
            key: The storage key/path for the object
            chunk_size: Size of each chunk in bytes

        Yields:
            Chunks of bytes

        Raises:
            KeyError: If the key doesn't exist
            IOError: If read operation fails
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in storage.

        Args:
            key: The storage key/path to check

        Returns:
            True if the key exists, False otherwise
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete data from storage.

        Args:
            key: The storage key/path to delete

        Returns:
            True if successful or key didn't exist, False on error

        Raises:
            IOError: If delete operation fails
        """
        pass

    @abstractmethod
    async def list_keys(self, prefix: str = "", limit: int = 1000) -> List[str]:
        """
        List keys with optional prefix filter.

        Args:
            prefix: Optional prefix to filter keys
            limit: Maximum number of keys to return

        Returns:
            List of matching keys

        Raises:
            IOError: If list operation fails
        """
        pass

    @abstractmethod
    async def get_metadata(self, key: str) -> Dict[str, str]:
        """
        Get metadata for a key.

        Args:
            key: The storage key/path

        Returns:
            Dictionary of metadata

        Raises:
            KeyError: If the key doesn't exist
            IOError: If operation fails
        """
        pass

    @abstractmethod
    async def update_metadata(self, key: str, metadata: Dict[str, str]) -> bool:
        """
        Update metadata for a key.

        Args:
            key: The storage key/path
            metadata: New metadata dictionary

        Returns:
            True if successful, False otherwise

        Raises:
            KeyError: If the key doesn't exist
            IOError: If operation fails
        """
        pass

    @abstractmethod
    async def get_size(self, key: str) -> int:
        """
        Get the size of an object in bytes.

        Args:
            key: The storage key/path

        Returns:
            Size in bytes

        Raises:
            KeyError: If the key doesn't exist
            IOError: If operation fails
        """
        pass

    async def write_stream(
        self, key: str, stream: AsyncIterator[bytes], metadata: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Write data to storage from an async stream.

        Default implementation collects all chunks and writes at once.
        Backends should override for more efficient streaming.

        Args:
            key: The storage key/path for the object
            stream: Async iterator yielding bytes
            metadata: Optional metadata dictionary

        Returns:
            True if successful, False otherwise
        """
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        data = b"".join(chunks)
        return await self.write(key, data, metadata)

    async def copy(self, source_key: str, dest_key: str) -> bool:
        """
        Copy an object within the storage.

        Default implementation reads and writes. Backends may override
        for more efficient server-side copy.

        Args:
            source_key: The source storage key/path
            dest_key: The destination storage key/path

        Returns:
            True if successful, False otherwise
        """
        try:
            data = await self.read(source_key)
            metadata = await self.get_metadata(source_key)
            return await self.write(dest_key, data, metadata)
        except Exception:
            return False

    async def move(self, source_key: str, dest_key: str) -> bool:
        """
        Move an object within the storage.

        Args:
            source_key: The source storage key/path
            dest_key: The destination storage key/path

        Returns:
            True if successful, False otherwise
        """
        if await self.copy(source_key, dest_key):
            return await self.delete(source_key)
        return False
