"""
Comprehensive tests for object storage backends.
Tests both LocalObjectStorage and S3ObjectStorage implementations.
"""

import shutil
import tempfile
from unittest.mock import patch

import pytest
import pytest_asyncio
from ff_storage import LocalObjectStorage, ObjectStorage, S3ObjectStorage


class TestLocalObjectStorage:
    """Test LocalObjectStorage implementation."""

    @pytest_asyncio.fixture
    async def storage(self):
        """Create a temporary storage directory for testing."""
        temp_dir = tempfile.mkdtemp(prefix="test_storage_")
        storage = LocalObjectStorage(temp_dir)
        yield storage
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_write_and_read(self, storage):
        """Test basic write and read operations."""
        key = "test/file.txt"
        data = b"Hello, World!"
        metadata = {"content-type": "text/plain", "author": "test"}

        # Write
        result = await storage.write(key, data, metadata)
        assert result is True

        # Read
        read_data = await storage.read(key)
        assert read_data == data

        # Check metadata
        read_metadata = await storage.get_metadata(key)
        assert read_metadata == metadata

    @pytest.mark.asyncio
    async def test_exists(self, storage):
        """Test exists method."""
        key = "test/exists.txt"

        # Should not exist initially
        assert await storage.exists(key) is False

        # Write file
        await storage.write(key, b"test")

        # Should exist now
        assert await storage.exists(key) is True

    @pytest.mark.asyncio
    async def test_delete(self, storage):
        """Test delete operation."""
        key = "test/delete.txt"
        data = b"To be deleted"

        # Write file
        await storage.write(key, data)
        assert await storage.exists(key) is True

        # Delete
        result = await storage.delete(key)
        assert result is True

        # Should not exist anymore
        assert await storage.exists(key) is False

    @pytest.mark.asyncio
    async def test_list_keys(self, storage):
        """Test listing keys with prefix."""
        # Write multiple files
        await storage.write("docs/file1.txt", b"data1")
        await storage.write("docs/file2.txt", b"data2")
        await storage.write("images/pic.jpg", b"data3")

        # List all
        all_keys = await storage.list_keys()
        assert len(all_keys) == 3

        # List with prefix
        docs_keys = await storage.list_keys(prefix="docs")
        assert len(docs_keys) == 2
        assert all("docs" in key for key in docs_keys)

        # List with limit
        limited_keys = await storage.list_keys(limit=2)
        assert len(limited_keys) == 2

    @pytest.mark.asyncio
    async def test_get_size(self, storage):
        """Test getting file size."""
        key = "test/size.txt"
        data = b"12345678"  # 8 bytes

        await storage.write(key, data)
        size = await storage.get_size(key)
        assert size == 8

    @pytest.mark.asyncio
    async def test_update_metadata(self, storage):
        """Test updating metadata."""
        key = "test/meta.txt"
        initial_metadata = {"version": "1.0"}
        updated_metadata = {"version": "2.0", "updated": "true"}

        # Write with initial metadata
        await storage.write(key, b"data", initial_metadata)

        # Update metadata
        result = await storage.update_metadata(key, updated_metadata)
        assert result is True

        # Verify update
        metadata = await storage.get_metadata(key)
        assert metadata == updated_metadata

    @pytest.mark.asyncio
    async def test_copy(self, storage):
        """Test copying objects."""
        source_key = "test/source.txt"
        dest_key = "test/dest.txt"
        data = b"Copy me"
        metadata = {"test": "value"}

        # Write source
        await storage.write(source_key, data, metadata)

        # Copy
        result = await storage.copy(source_key, dest_key)
        assert result is True

        # Verify copy
        dest_data = await storage.read(dest_key)
        assert dest_data == data

        dest_metadata = await storage.get_metadata(dest_key)
        assert dest_metadata == metadata

        # Source should still exist
        assert await storage.exists(source_key) is True

    @pytest.mark.asyncio
    async def test_move(self, storage):
        """Test moving objects."""
        source_key = "test/source.txt"
        dest_key = "test/dest.txt"
        data = b"Move me"

        # Write source
        await storage.write(source_key, data)

        # Move
        result = await storage.move(source_key, dest_key)
        assert result is True

        # Verify move
        dest_data = await storage.read(dest_key)
        assert dest_data == data

        # Source should not exist
        assert await storage.exists(source_key) is False

    @pytest.mark.asyncio
    async def test_stream_read(self, storage):
        """Test reading data as stream."""
        key = "test/stream.txt"
        data = b"A" * 10000  # 10KB of data

        await storage.write(key, data)

        # Read as stream
        chunks = []
        async for chunk in storage.read_stream(key, chunk_size=1024):
            chunks.append(chunk)

        # Verify we got multiple chunks
        assert len(chunks) > 1

        # Verify complete data
        reconstructed = b"".join(chunks)
        assert reconstructed == data

    @pytest.mark.asyncio
    async def test_stream_write(self, storage):
        """Test writing data from stream."""
        key = "test/stream_write.txt"
        data = b"Stream " * 1000

        async def data_generator():
            """Generate data in chunks."""
            chunk_size = 100
            for i in range(0, len(data), chunk_size):
                yield data[i : i + chunk_size]

        # Write from stream
        result = await storage.write_stream(key, data_generator())
        assert result is True

        # Verify data
        read_data = await storage.read(key)
        assert read_data == data

    @pytest.mark.asyncio
    async def test_path_traversal_protection(self, storage):
        """Test that path traversal attacks are prevented."""
        # These keys should be rejected as path traversal attempts
        dangerous_keys = [
            "../etc/passwd",
            "../../sensitive",
            "test/../../outside",
            "test/../../../etc/passwd",
        ]

        for key in dangerous_keys:
            # Path traversal should raise ValueError
            try:
                await storage.write(key, b"data")
                # If we get here, the test should fail
                pytest.fail(f"Expected ValueError for key: {key}")
            except ValueError as e:
                assert "path traversal" in str(e).lower()

        # These keys should be allowed (they look suspicious but are safe)
        safe_keys = [
            "/etc/passwd",  # Leading slash is stripped, becomes etc/passwd under base
            "etc/passwd",  # Just a regular subdirectory
        ]

        for key in safe_keys:
            # These should succeed
            result = await storage.write(key, b"safe data")
            assert result is True

    @pytest.mark.asyncio
    async def test_atomic_write(self, storage):
        """Test that writes are atomic."""
        key = "test/atomic.txt"
        original_data = b"Original"

        # Write original
        await storage.write(key, original_data)

        # Simulate partial write failure
        with patch("aiofiles.os.rename", side_effect=Exception("Simulated failure")):
            with pytest.raises(IOError):
                await storage.write(key, b"New data")

        # Original data should still be intact
        data = await storage.read(key)
        assert data == original_data

    @pytest.mark.asyncio
    async def test_nonexistent_key_errors(self, storage):
        """Test proper error handling for nonexistent keys."""
        key = "nonexistent"

        # Read should raise KeyError
        with pytest.raises(KeyError):
            await storage.read(key)

        # Get metadata should raise KeyError
        with pytest.raises(KeyError):
            await storage.get_metadata(key)

        # Update metadata should raise KeyError
        with pytest.raises(KeyError):
            await storage.update_metadata(key, {"test": "value"})

        # Get size should raise KeyError
        with pytest.raises(KeyError):
            await storage.get_size(key)


# Note: S3 tests are commented out due to moto compatibility issues with async
# TODO: Fix moto async support or use a different mocking approach
'''
class TestS3ObjectStorage:
    """Test S3ObjectStorage implementation with mocked AWS."""

    @pytest.mark.asyncio
    @mock_aws
    async def test_write_and_read(self):
        """Test basic write and read operations."""
        key = "test/file.txt"
        data = b"Hello, S3!"
        metadata = {"content-type": "text/plain", "author": "test"}

        # Write
        result = await storage.write(key, data, metadata)
        assert result is True

        # Read
        read_data = await storage.read(key)
        assert read_data == data

        # Check metadata
        read_metadata = await storage.get_metadata(key)
        assert read_metadata["author"] == metadata["author"]
        assert read_metadata["content-type"] == metadata["content-type"]

    @pytest.mark.asyncio
    async def test_exists(self, storage):
        """Test exists method."""
        key = "test/exists.txt"

        # Should not exist initially
        assert await storage.exists(key) is False

        # Write file
        await storage.write(key, b"test")

        # Should exist now
        assert await storage.exists(key) is True

    @pytest.mark.asyncio
    async def test_delete(self, storage):
        """Test delete operation."""
        key = "test/delete.txt"
        data = b"To be deleted"

        # Write file
        await storage.write(key, data)
        assert await storage.exists(key) is True

        # Delete
        result = await storage.delete(key)
        assert result is True

        # Should not exist anymore
        assert await storage.exists(key) is False

    @pytest.mark.asyncio
    async def test_list_keys(self, storage):
        """Test listing keys with prefix."""
        # Write multiple files
        await storage.write("docs/file1.txt", b"data1")
        await storage.write("docs/file2.txt", b"data2")
        await storage.write("images/pic.jpg", b"data3")

        # List all
        all_keys = await storage.list_keys()
        assert len(all_keys) == 3

        # List with prefix
        docs_keys = await storage.list_keys(prefix="docs")
        assert len(docs_keys) == 2
        assert all("docs" in key for key in docs_keys)

    @pytest.mark.asyncio
    async def test_multipart_upload(self, storage):
        """Test multipart upload for large files."""
        key = "test/large.bin"
        # Create data larger than multipart threshold (5MB)
        data = b"X" * (6 * 1024 * 1024)  # 6MB

        # Write large file
        result = await storage.write(key, data)
        assert result is True

        # Read and verify
        read_data = await storage.read(key)
        assert read_data == data

    @pytest.mark.asyncio
    @mock_aws
    async def test_prefix_handling(self):
        """Test S3 storage with prefix."""
        session = aioboto3.Session()
        async with session.client('s3', region_name='us-east-1') as s3:
            await s3.create_bucket(Bucket='test-bucket-prefix')

        storage = S3ObjectStorage(
            bucket='test-bucket-prefix',
            prefix='myapp/data',
            region='us-east-1'
        )

        # Write with prefix
        key = "file.txt"
        await storage.write(key, b"data")

        # Verify object is stored with prefix
        async with session.client('s3', region_name='us-east-1') as s3:
            response = await s3.list_objects_v2(Bucket='test-bucket-prefix')
            assert 'Contents' in response
            assert response['Contents'][0]['Key'] == 'myapp/data/file.txt'

    @pytest.mark.asyncio
    async def test_copy_server_side(self, storage):
        """Test server-side copy in S3."""
        source_key = "test/source.txt"
        dest_key = "test/dest.txt"
        data = b"Copy me"

        # Write source
        await storage.write(source_key, data)

        # Copy
        result = await storage.copy(source_key, dest_key)
        assert result is True

        # Verify copy
        dest_data = await storage.read(dest_key)
        assert dest_data == data

        # Source should still exist
        assert await storage.exists(source_key) is True

    @pytest.mark.asyncio
    async def test_stream_read(self, storage):
        """Test reading data as stream from S3."""
        key = "test/stream.txt"
        data = b"A" * 10000  # 10KB of data

        await storage.write(key, data)

        # Read as stream
        chunks = []
        async for chunk in storage.read_stream(key, chunk_size=1024):
            chunks.append(chunk)

        # Verify we got multiple chunks
        assert len(chunks) > 1

        # Verify complete data
        reconstructed = b''.join(chunks)
        assert reconstructed == data

    @pytest.mark.asyncio
    async def test_nonexistent_key_errors(self, storage):
        """Test proper error handling for nonexistent keys."""
        key = "nonexistent"

        # Read should raise KeyError
        with pytest.raises(KeyError):
            await storage.read(key)

        # Get metadata should raise KeyError
        with pytest.raises(KeyError):
            await storage.get_metadata(key)

        # Get size should raise KeyError
        with pytest.raises(KeyError):
            await storage.get_size(key)


'''


class TestObjectStorageInterface:
    """Test that both implementations properly implement the interface."""

    def test_interface_methods(self):
        """Verify all required methods are present."""
        required_methods = [
            "write",
            "read",
            "read_stream",
            "exists",
            "delete",
            "list_keys",
            "get_metadata",
            "update_metadata",
            "get_size",
            "write_stream",
            "copy",
            "move",
        ]

        for method in required_methods:
            assert hasattr(LocalObjectStorage, method)
            assert hasattr(S3ObjectStorage, method)

    def test_inheritance(self):
        """Verify proper inheritance from ObjectStorage."""
        assert issubclass(LocalObjectStorage, ObjectStorage)
        assert issubclass(S3ObjectStorage, ObjectStorage)
