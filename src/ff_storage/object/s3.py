"""
S3 and S3-compatible storage implementation of the ObjectStorage interface.
Supports AWS S3, MinIO, and other S3-compatible services.
"""

from typing import Any, AsyncIterator, Dict, List, Optional

import aioboto3
from botocore.exceptions import ClientError

from .base import ObjectStorage


class S3ObjectStorage(ObjectStorage):
    """
    S3-compatible storage backend.

    Supports AWS S3 and S3-compatible services (MinIO, Wasabi, etc.).
    Uses aioboto3 for async operations and connection pooling.

    Example:
        >>> # AWS S3
        >>> storage = S3ObjectStorage(bucket="my-bucket", region="us-east-1")
        >>> await storage.write("docs/report.pdf", pdf_bytes)
        >>>
        >>> # MinIO or other S3-compatible
        >>> storage = S3ObjectStorage(
        ...     bucket="my-bucket",
        ...     endpoint_url="http://localhost:9000",
        ...     access_key_id="minioadmin",
        ...     secret_access_key="minioadmin"
        ... )
    """

    # Multipart upload threshold (5MB)
    MULTIPART_THRESHOLD = 5 * 1024 * 1024
    # Multipart chunk size (5MB minimum for S3)
    MULTIPART_CHUNK_SIZE = 5 * 1024 * 1024

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: str = "us-east-1",
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        session_token: Optional[str] = None,
    ):
        """
        Initialize S3 storage backend.

        Args:
            bucket: S3 bucket name
            prefix: Optional prefix for all keys
            region: AWS region (default: us-east-1)
            access_key_id: AWS access key ID (uses environment/config if not provided)
            secret_access_key: AWS secret access key
            endpoint_url: Custom endpoint URL for S3-compatible services
            session_token: AWS session token for temporary credentials
        """
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""
        self.region = region
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.endpoint_url = endpoint_url
        self.session_token = session_token
        self._session = None

    def _get_full_key(self, key: str) -> str:
        """Get the full S3 key including prefix."""
        clean_key = key.lstrip("/")
        return f"{self.prefix}{clean_key}" if self.prefix else clean_key

    def _strip_prefix(self, full_key: str) -> str:
        """Remove prefix from a full S3 key."""
        if self.prefix and full_key.startswith(self.prefix):
            return full_key[len(self.prefix) :]
        return full_key

    async def _get_client(self):
        """Get or create S3 client with connection pooling."""
        if not self._session:
            self._session = aioboto3.Session(
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                aws_session_token=self.session_token,
                region_name=self.region,
            )

        # Return a context manager for the client
        return self._session.client("s3", endpoint_url=self.endpoint_url)

    async def write(self, key: str, data: bytes, metadata: Optional[Dict[str, str]] = None) -> bool:
        """
        Write data to S3 with optional metadata.

        Uses multipart upload for large files.
        """
        try:
            full_key = self._get_full_key(key)

            # Prepare metadata
            extra_args = {}
            if metadata:
                # boto3 handles the 'x-amz-meta-' prefix internally for custom metadata
                extra_args["Metadata"] = metadata

                # Handle content-type specially
                if "content-type" in metadata:
                    extra_args["ContentType"] = metadata["content-type"]

            async with await self._get_client() as client:
                # Use multipart upload for large files
                if len(data) > self.MULTIPART_THRESHOLD:
                    await self._multipart_upload(client, full_key, data, extra_args)
                else:
                    # Simple put for small files
                    await client.put_object(
                        Bucket=self.bucket, Key=full_key, Body=data, **extra_args
                    )

            return True

        except Exception as e:
            raise IOError(f"Failed to write {key}: {e}")

    async def _multipart_upload(self, client: Any, key: str, data: bytes, extra_args: Dict) -> None:
        """Perform multipart upload for large files."""
        # Initiate multipart upload
        response = await client.create_multipart_upload(Bucket=self.bucket, Key=key, **extra_args)
        upload_id = response["UploadId"]

        try:
            parts = []

            # Upload parts
            for i in range(0, len(data), self.MULTIPART_CHUNK_SIZE):
                part_number = (i // self.MULTIPART_CHUNK_SIZE) + 1
                chunk = data[i : i + self.MULTIPART_CHUNK_SIZE]

                response = await client.upload_part(
                    Bucket=self.bucket,
                    Key=key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=chunk,
                )

                parts.append({"ETag": response["ETag"], "PartNumber": part_number})

            # Complete multipart upload
            await client.complete_multipart_upload(
                Bucket=self.bucket, Key=key, UploadId=upload_id, MultipartUpload={"Parts": parts}
            )

        except Exception:
            # Abort the multipart upload on error
            await client.abort_multipart_upload(Bucket=self.bucket, Key=key, UploadId=upload_id)
            raise

    async def read(self, key: str) -> bytes:
        """Read data from S3."""
        try:
            full_key = self._get_full_key(key)

            async with await self._get_client() as client:
                try:
                    response = await client.get_object(Bucket=self.bucket, Key=full_key)
                    async with response["Body"] as stream:
                        return await stream.read()

                except client.exceptions.NoSuchKey:
                    raise KeyError(f"Key not found: {key}")

        except KeyError:
            raise
        except Exception as e:
            raise IOError(f"Failed to read {key}: {e}")

    async def read_stream(self, key: str, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        """Read data as a stream of chunks."""
        try:
            full_key = self._get_full_key(key)

            async with await self._get_client() as client:
                try:
                    response = await client.get_object(Bucket=self.bucket, Key=full_key)

                    async with response["Body"] as stream:
                        while True:
                            chunk = await stream.read(chunk_size)
                            if not chunk:
                                break
                            yield chunk

                except client.exceptions.NoSuchKey:
                    raise KeyError(f"Key not found: {key}")

        except KeyError:
            raise
        except Exception as e:
            raise IOError(f"Failed to stream {key}: {e}")

    async def exists(self, key: str) -> bool:
        """Check if an object exists in S3."""
        try:
            full_key = self._get_full_key(key)

            async with await self._get_client() as client:
                try:
                    await client.head_object(Bucket=self.bucket, Key=full_key)
                    return True
                except client.exceptions.NoSuchKey:
                    return False
                except ClientError as e:
                    if e.response["Error"]["Code"] == "404":
                        return False
                    raise

        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """Delete an object from S3."""
        try:
            full_key = self._get_full_key(key)

            async with await self._get_client() as client:
                await client.delete_object(Bucket=self.bucket, Key=full_key)

            return True

        except Exception as e:
            raise IOError(f"Failed to delete {key}: {e}")

    async def list_keys(self, prefix: str = "", limit: int = 1000) -> List[str]:
        """List objects with optional prefix filter."""
        try:
            full_prefix = self._get_full_key(prefix) if prefix else self.prefix
            keys = []

            async with await self._get_client() as client:
                paginator = client.get_paginator("list_objects_v2")

                async for page in paginator.paginate(
                    Bucket=self.bucket, Prefix=full_prefix, PaginationConfig={"MaxItems": limit}
                ):
                    if "Contents" in page:
                        for obj in page["Contents"]:
                            # Strip our prefix from the key
                            key = self._strip_prefix(obj["Key"])
                            keys.append(key)

                            if len(keys) >= limit:
                                return keys

            return keys

        except Exception as e:
            raise IOError(f"Failed to list keys: {e}")

    async def get_metadata(self, key: str) -> Dict[str, str]:
        """Get metadata for an S3 object."""
        try:
            full_key = self._get_full_key(key)

            async with await self._get_client() as client:
                try:
                    response = await client.head_object(Bucket=self.bucket, Key=full_key)

                    # Extract custom metadata (strip x-amz-meta- prefix)
                    metadata = {}
                    if "Metadata" in response:
                        metadata = response["Metadata"]

                    # Add content-type if present
                    if "ContentType" in response:
                        metadata["content-type"] = response["ContentType"]

                    return metadata

                except client.exceptions.NoSuchKey:
                    raise KeyError(f"Key not found: {key}")

        except KeyError:
            raise
        except Exception as e:
            raise IOError(f"Failed to get metadata for {key}: {e}")

    async def update_metadata(self, key: str, metadata: Dict[str, str]) -> bool:
        """
        Update metadata for an S3 object.

        Note: S3 requires copying the object to update metadata.
        """
        try:
            full_key = self._get_full_key(key)

            async with await self._get_client() as client:
                # Prepare metadata
                s3_metadata = metadata.copy()
                extra_args = {"Metadata": s3_metadata}

                # Handle content-type specially
                if "content-type" in metadata:
                    extra_args["ContentType"] = metadata["content-type"]
                    extra_args["MetadataDirective"] = "REPLACE"

                # Copy object to itself with new metadata
                await client.copy_object(
                    Bucket=self.bucket,
                    Key=full_key,
                    CopySource={"Bucket": self.bucket, "Key": full_key},
                    **extra_args,
                )

            return True

        except Exception as e:
            raise IOError(f"Failed to update metadata for {key}: {e}")

    async def get_size(self, key: str) -> int:
        """Get the size of an S3 object in bytes."""
        try:
            full_key = self._get_full_key(key)

            async with await self._get_client() as client:
                try:
                    response = await client.head_object(Bucket=self.bucket, Key=full_key)
                    return response["ContentLength"]

                except client.exceptions.NoSuchKey:
                    raise KeyError(f"Key not found: {key}")

        except KeyError:
            raise
        except Exception as e:
            raise IOError(f"Failed to get size for {key}: {e}")

    async def write_stream(
        self, key: str, stream: AsyncIterator[bytes], metadata: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Write data from a stream to S3.

        For now, collects all chunks and writes at once.
        TODO: Implement true streaming with multipart upload.
        """
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)

        data = b"".join(chunks)
        return await self.write(key, data, metadata)

    async def copy(self, source_key: str, dest_key: str) -> bool:
        """
        Copy an object within S3 (server-side copy).
        """
        try:
            source_full_key = self._get_full_key(source_key)
            dest_full_key = self._get_full_key(dest_key)

            async with await self._get_client() as client:
                await client.copy_object(
                    Bucket=self.bucket,
                    Key=dest_full_key,
                    CopySource={"Bucket": self.bucket, "Key": source_full_key},
                )

            return True

        except Exception:
            return False

    async def generate_presigned_url(
        self, key: str, expiration: int = 3600, operation: str = "get_object"
    ) -> str:
        """
        Generate a presigned URL for an S3 object.

        Args:
            key: The storage key/path
            expiration: URL expiration time in seconds (default: 1 hour)
            operation: The S3 operation ('get_object' or 'put_object')

        Returns:
            Presigned URL string
        """
        full_key = self._get_full_key(key)

        async with await self._get_client() as client:
            return await client.generate_presigned_url(
                ClientMethod=operation,
                Params={"Bucket": self.bucket, "Key": full_key},
                ExpiresIn=expiration,
            )
