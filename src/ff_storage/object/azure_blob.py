"""
Azure Blob Storage implementation of the ObjectStorage interface.
Supports both Azurite (local development) and production Azure Blob Storage.
"""

import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.storage.blob.aio import BlobServiceClient as AsyncBlobServiceClient

from .base import ObjectStorage


class AzureBlobObjectStorage(ObjectStorage):
    """
    Azure Blob Storage backend.

    Supports both Azurite (local development) and production Azure Blob Storage
    with identical API. Uses Azure Storage SDK for blob operations.

    Authentication Methods:
        - Connection String: For Azurite (local development) or when using access keys
        - Managed Identity: For production Azure deployments with DefaultAzureCredential

    Example:
        >>> # Azurite (local development with connection string)
        >>> storage = AzureBlobObjectStorage(
        ...     container_name="ixr-documents",
        ...     connection_string="DefaultEndpointsProtocol=http;AccountName=fenixstorage;..."
        ... )
        >>>
        >>> # Production Azure Blob Storage with connection string
        >>> storage = AzureBlobObjectStorage(
        ...     container_name="ixr-documents",
        ...     connection_string="DefaultEndpointsProtocol=https;AccountName=myaccount;..."
        ... )
        >>>
        >>> # Production with Managed Identity (DefaultAzureCredential)
        >>> storage = AzureBlobObjectStorage(
        ...     container_name="ixr-documents",
        ...     account_url="https://mystorageaccount.blob.core.windows.net"
        ... )
        >>>
        >>> # Production with custom credential
        >>> from azure.identity import DefaultAzureCredential
        >>> storage = AzureBlobObjectStorage(
        ...     container_name="ixr-documents",
        ...     account_url="https://mystorageaccount.blob.core.windows.net",
        ...     credential=DefaultAzureCredential()
        ... )
        >>>
        >>> await storage.write("ixrs/IXR000001/renewal/file.pdf", data)
    """

    def __init__(
        self,
        container_name: str,
        connection_string: str | None = None,
        account_url: str | None = None,
        credential: Any | None = None,
        prefix: str = "",
    ):
        """
        Initialize Azure Blob Storage backend.

        Args:
            container_name: Name of the container for blobs
            connection_string: Azure Storage connection string (for Azurite/local dev)
            account_url: Azure Storage account URL (for managed identity)
            credential: Optional credential object (defaults to DefaultAzureCredential)
            prefix: Optional prefix for all keys (similar to S3ObjectStorage)

        Note:
            Provide EITHER connection_string OR account_url, not both.
        """
        # Validation
        if connection_string and account_url:
            raise ValueError("Provide either connection_string OR account_url, not both")
        if not connection_string and not account_url:
            raise ValueError("Must provide either connection_string or account_url")

        self.connection_string = connection_string
        self.account_url = account_url
        self.credential = credential
        self.container_name = container_name
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""

        # Initialize sync client based on authentication method
        if connection_string:
            self._sync_client = BlobServiceClient.from_connection_string(connection_string)
        else:
            self._sync_client = BlobServiceClient(
                account_url=account_url, credential=credential or DefaultAzureCredential()
            )

        self._sync_container_client = self._sync_client.get_container_client(container_name)

        # Async client (will be initialized lazily)
        self._async_client: Optional[AsyncBlobServiceClient] = None

        # Create container if it doesn't exist (sync during init)
        try:
            self._sync_container_client.create_container()
        except Exception as e:
            error_msg = str(e).lower()
            # Only ignore if container already exists
            if "containeralreadyexists" in error_msg or "already exists" in error_msg:
                pass  # Container already exists - this is fine
            else:
                # Other errors (connectivity, permissions, etc.) should be raised
                raise IOError(
                    f"Failed to create or access Azure Blob container '{container_name}': {e}"
                ) from e

    def _get_full_key(self, key: str) -> str:
        """Get the full blob name including prefix."""
        clean_key = key.lstrip("/")
        return f"{self.prefix}{clean_key}" if self.prefix else clean_key

    def _strip_prefix(self, full_key: str) -> str:
        """Remove prefix from a full blob name."""
        if self.prefix and full_key.startswith(self.prefix):
            return full_key[len(self.prefix) :]
        return full_key

    async def _get_async_client(self) -> AsyncBlobServiceClient:
        """Get or create async blob service client."""
        if self._async_client is None:
            if self.connection_string:
                self._async_client = AsyncBlobServiceClient.from_connection_string(
                    self.connection_string
                )
            else:
                self._async_client = AsyncBlobServiceClient(
                    account_url=self.account_url,
                    credential=self.credential or DefaultAzureCredential(),
                )
        return self._async_client

    async def write(self, key: str, data: bytes, metadata: Optional[Dict[str, str]] = None) -> bool:
        """
        Write data to Azure Blob Storage with optional metadata.

        Args:
            key: The storage key/path for the blob
            data: The bytes to store
            metadata: Optional metadata dictionary

        Returns:
            True if successful, False otherwise
        """
        try:
            full_key = self._get_full_key(key)

            # Prepare content settings
            content_type = "application/octet-stream"
            if metadata and "content-type" in metadata:
                content_type = metadata["content-type"]

            content_settings = ContentSettings(content_type=content_type)

            # Filter metadata (Azure has restrictions on metadata keys)
            azure_metadata = {}
            if metadata:
                for k, v in metadata.items():
                    if k != "content-type":  # Already handled in ContentSettings
                        # Azure metadata keys must be valid C# identifiers
                        # Replace invalid chars with underscores
                        safe_key = k.replace("-", "_").replace(".", "_")
                        azure_metadata[safe_key] = str(v)

            # Upload blob (run sync operation in thread pool)
            blob_client = self._sync_container_client.get_blob_client(full_key)
            await asyncio.to_thread(
                blob_client.upload_blob,
                data,
                overwrite=True,
                metadata=azure_metadata,
                content_settings=content_settings,
            )

            return True

        except Exception as e:
            raise IOError(f"Failed to write {key}: {e}")

    async def read(self, key: str) -> bytes:
        """
        Read data from Azure Blob Storage.

        Args:
            key: The storage key/path for the blob

        Returns:
            The stored bytes
        """
        try:
            full_key = self._get_full_key(key)

            blob_client = self._sync_container_client.get_blob_client(full_key)

            # Download blob (run sync operation in thread pool)
            download_stream = await asyncio.to_thread(blob_client.download_blob)
            data = await asyncio.to_thread(download_stream.readall)

            return data

        except ResourceNotFoundError:
            raise KeyError(f"Key not found: {key}")
        except Exception as e:
            raise IOError(f"Failed to read {key}: {e}")

    async def read_stream(self, key: str, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        """
        Read data from Azure Blob Storage as a stream of chunks.

        Args:
            key: The storage key/path for the blob
            chunk_size: Size of each chunk in bytes

        Yields:
            Chunks of bytes
        """
        try:
            full_key = self._get_full_key(key)

            blob_client = self._sync_container_client.get_blob_client(full_key)

            # Download blob as stream (run sync operation in thread pool)
            download_stream = await asyncio.to_thread(blob_client.download_blob)

            # Read chunks
            while True:
                chunk = await asyncio.to_thread(download_stream.readinto, bytearray(chunk_size))
                if not chunk:
                    break
                yield bytes(chunk)

        except ResourceNotFoundError:
            raise KeyError(f"Key not found: {key}")
        except Exception as e:
            raise IOError(f"Failed to stream {key}: {e}")

    async def exists(self, key: str) -> bool:
        """
        Check if a blob exists in Azure Blob Storage.

        Args:
            key: The storage key/path to check

        Returns:
            True if the key exists, False otherwise
        """
        try:
            full_key = self._get_full_key(key)

            blob_client = self._sync_container_client.get_blob_client(full_key)

            # Check if blob exists (run sync operation in thread pool)
            exists = await asyncio.to_thread(blob_client.exists)

            return exists

        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete a blob from Azure Blob Storage.

        Args:
            key: The storage key/path to delete

        Returns:
            True if successful or key didn't exist, False on error
        """
        try:
            full_key = self._get_full_key(key)

            blob_client = self._sync_container_client.get_blob_client(full_key)

            # Delete blob (run sync operation in thread pool)
            await asyncio.to_thread(blob_client.delete_blob)

            return True

        except ResourceNotFoundError:
            return True  # Already deleted
        except Exception as e:
            raise IOError(f"Failed to delete {key}: {e}")

    async def list_keys(self, prefix: str = "", limit: int = 1000) -> List[str]:
        """
        List blobs with optional prefix filter.

        Args:
            prefix: Optional prefix to filter keys
            limit: Maximum number of keys to return

        Returns:
            List of matching keys
        """
        try:
            full_prefix = self._get_full_key(prefix) if prefix else self.prefix

            keys = []

            # List blobs (run sync operation in thread pool)
            blob_list = await asyncio.to_thread(
                lambda: list(
                    self._sync_container_client.list_blobs(
                        name_starts_with=full_prefix, results_per_page=limit
                    )
                )
            )

            for blob in blob_list:
                # Strip our prefix from the key
                key = self._strip_prefix(blob.name)
                keys.append(key)

                if len(keys) >= limit:
                    break

            return keys

        except Exception as e:
            raise IOError(f"Failed to list keys: {e}")

    async def get_metadata(self, key: str) -> Dict[str, str]:
        """
        Get metadata for a blob.

        Args:
            key: The storage key/path

        Returns:
            Dictionary of metadata
        """
        try:
            full_key = self._get_full_key(key)

            blob_client = self._sync_container_client.get_blob_client(full_key)

            # Get properties (run sync operation in thread pool)
            properties = await asyncio.to_thread(blob_client.get_blob_properties)

            metadata = {}
            if properties.metadata:
                # Convert underscores back to hyphens (reverse of write operation)
                for k, v in properties.metadata.items():
                    original_key = k.replace("_", "-")
                    metadata[original_key] = v

            # Add content-type
            if properties.content_settings and properties.content_settings.content_type:
                metadata["content-type"] = properties.content_settings.content_type

            return metadata

        except ResourceNotFoundError:
            raise KeyError(f"Key not found: {key}")
        except Exception as e:
            raise IOError(f"Failed to get metadata for {key}: {e}")

    async def update_metadata(self, key: str, metadata: Dict[str, str]) -> bool:
        """
        Update metadata for a blob.

        Args:
            key: The storage key/path
            metadata: New metadata dictionary

        Returns:
            True if successful, False otherwise
        """
        try:
            full_key = self._get_full_key(key)

            blob_client = self._sync_container_client.get_blob_client(full_key)

            # Filter and prepare metadata
            azure_metadata = {}
            for k, v in metadata.items():
                if k != "content-type":
                    safe_key = k.replace("-", "_").replace(".", "_")
                    azure_metadata[safe_key] = str(v)

            # Update metadata (run sync operation in thread pool)
            await asyncio.to_thread(blob_client.set_blob_metadata, metadata=azure_metadata)

            return True

        except ResourceNotFoundError:
            raise KeyError(f"Key not found: {key}")
        except Exception as e:
            raise IOError(f"Failed to update metadata for {key}: {e}")

    async def get_size(self, key: str) -> int:
        """
        Get the size of a blob in bytes.

        Args:
            key: The storage key/path

        Returns:
            Size in bytes
        """
        try:
            full_key = self._get_full_key(key)

            blob_client = self._sync_container_client.get_blob_client(full_key)

            # Get properties (run sync operation in thread pool)
            properties = await asyncio.to_thread(blob_client.get_blob_properties)

            return properties.size

        except ResourceNotFoundError:
            raise KeyError(f"Key not found: {key}")
        except Exception as e:
            raise IOError(f"Failed to get size for {key}: {e}")

    def close(self) -> None:
        """Close Azure Storage client connections."""
        try:
            if self._sync_client:
                self._sync_client.close()
            if self._async_client:
                # Async client cleanup happens during async context exit
                pass
        except Exception:
            pass

    def __del__(self):
        """Cleanup on garbage collection."""
        self.close()
