"""
Unit tests for path traversal prevention in local storage (B5).

Tests cover:
- Path traversal via ../ sequences
- Path traversal via prefix collision
- Symlink attacks (if applicable)
"""

import tempfile
from pathlib import Path

import pytest


class TestLocalStoragePathTraversal:
    """Tests for LocalObjectStorage path traversal prevention."""

    def test_valid_paths_accepted(self):
        """Valid paths within base directory should be accepted."""
        from ff_storage.object.local import LocalObjectStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalObjectStorage(tmpdir)

            # Valid paths
            valid_keys = [
                "file.txt",
                "subdir/file.txt",
                "a/b/c/file.txt",
                "file-with-dashes.txt",
                "file_with_underscores.txt",
            ]

            for key in valid_keys:
                path = storage._validate_key(key)
                assert path.is_relative_to(storage.base_path)

    def test_dot_dot_traversal_blocked(self):
        """Path traversal via ../ should be blocked."""
        from ff_storage.object.local import LocalObjectStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a subdirectory so traversal attempts have somewhere to go
            base_path = Path(tmpdir) / "storage"
            base_path.mkdir()
            storage = LocalObjectStorage(str(base_path))

            # These should definitely escape the base directory
            traversal_attempts = [
                "../etc/passwd",
                "../../etc/passwd",
                "subdir/../../../etc/passwd",
                "a/b/c/../../../../etc/passwd",
            ]

            for key in traversal_attempts:
                with pytest.raises(ValueError, match="path traversal detected"):
                    storage._validate_key(key)

    def test_prefix_collision_blocked(self):
        """Path traversal via prefix collision should be blocked.

        This tests the fix for using is_relative_to() instead of
        string startswith() check.

        Example: if base_path=/data/storage, an attacker should NOT
        be able to access /data/storage2/secrets just because it
        starts with /data/storage.
        """
        from ff_storage.object.local import LocalObjectStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create base directory
            base_path = Path(tmpdir) / "storage"
            base_path.mkdir()

            # Create a sibling directory that shares a prefix
            sibling_path = Path(tmpdir) / "storage2"
            sibling_path.mkdir()
            (sibling_path / "secrets.txt").write_text("secret data")

            storage = LocalObjectStorage(str(base_path))

            # Attempt to access sibling via path manipulation
            # This would succeed with string startswith() but fail with is_relative_to()
            with pytest.raises(ValueError, match="path traversal detected"):
                storage._validate_key("../storage2/secrets.txt")

    def test_absolute_path_blocked(self):
        """Absolute paths should be normalized and checked."""
        from ff_storage.object.local import LocalObjectStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalObjectStorage(tmpdir)

            # Absolute paths that escape
            absolute_attempts = [
                "/etc/passwd",
                "/tmp/malicious",
            ]

            for key in absolute_attempts:
                # Leading slash is stripped, then path is checked
                # This should either work (if within base) or raise
                try:
                    path = storage._validate_key(key)
                    # If it doesn't raise, verify it's within base
                    assert path.is_relative_to(storage.base_path)
                except ValueError:
                    pass  # Expected for paths that escape

    def test_double_encoded_traversal_blocked(self):
        """URL-encoded path traversal should be blocked."""
        from ff_storage.object.local import LocalObjectStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalObjectStorage(tmpdir)

            # These are literal strings, not URL-decoded
            # The pathlib.resolve() will handle them appropriately
            encoded_attempts = [
                "..%2F..%2Fetc%2Fpasswd",  # Literal %2F
                "%2e%2e/etc/passwd",  # Literal %2e
            ]

            for key in encoded_attempts:
                try:
                    path = storage._validate_key(key)
                    # If resolved, must be within base
                    assert path.is_relative_to(storage.base_path)
                except ValueError:
                    pass  # Also acceptable if rejected

    def test_null_byte_handling(self):
        """Null bytes in paths should not cause issues."""
        from ff_storage.object.local import LocalObjectStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalObjectStorage(tmpdir)

            # Null byte injection attempts
            null_attempts = [
                "file.txt\x00.jpg",
                "legit\x00../../../etc/passwd",
            ]

            for key in null_attempts:
                # Should either raise an error or handle safely
                try:
                    path = storage._validate_key(key)
                    assert path.is_relative_to(storage.base_path)
                except (ValueError, OSError):
                    pass  # Expected - null bytes are invalid


class TestPathValidationEdgeCases:
    """Edge case tests for path validation."""

    def test_deeply_nested_valid_path(self):
        """Deeply nested valid paths should work."""
        from ff_storage.object.local import LocalObjectStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalObjectStorage(tmpdir)

            deep_path = "/".join(["subdir"] * 50) + "/file.txt"
            path = storage._validate_key(deep_path)
            assert path.is_relative_to(storage.base_path)

    def test_unicode_in_path(self):
        """Unicode characters in paths should be handled."""
        from ff_storage.object.local import LocalObjectStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalObjectStorage(tmpdir)

            unicode_paths = [
                "документ.txt",  # Russian
                "文档.txt",  # Chinese
                "ドキュメント.txt",  # Japanese
                "émoji_📁/file.txt",  # Mixed
            ]

            for key in unicode_paths:
                path = storage._validate_key(key)
                assert path.is_relative_to(storage.base_path)

    def test_spaces_in_path(self):
        """Paths with spaces should be handled correctly."""
        from ff_storage.object.local import LocalObjectStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalObjectStorage(tmpdir)

            space_paths = [
                "my file.txt",
                "my folder/my file.txt",
                "   leading spaces.txt",
            ]

            for key in space_paths:
                path = storage._validate_key(key)
                assert path.is_relative_to(storage.base_path)

    def test_special_characters_in_path(self):
        """Special characters should be handled."""
        from ff_storage.object.local import LocalObjectStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalObjectStorage(tmpdir)

            special_paths = [
                "file-with-dash.txt",
                "file_with_underscore.txt",
                "file.multiple.dots.txt",
                "file (with parens).txt",
            ]

            for key in special_paths:
                path = storage._validate_key(key)
                assert path.is_relative_to(storage.base_path)


class TestListKeysPathTraversal:
    """Tests for list_keys path traversal prevention (Issue #3)."""

    @pytest.mark.asyncio
    async def test_list_keys_rejects_path_traversal(self):
        """list_keys should return empty list for path traversal attempts."""
        from ff_storage.object.local import LocalObjectStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create base directory inside temp
            base_path = Path(tmpdir) / "storage"
            base_path.mkdir()

            # Create a file inside storage
            (base_path / "legit.txt").write_text("legit content")

            storage = LocalObjectStorage(str(base_path))

            # Path traversal attempts should return empty list
            traversal_prefixes = [
                "../",
                "../../",
                "../../../etc",
                "subdir/../../../etc",
            ]

            for prefix in traversal_prefixes:
                keys = await storage.list_keys(prefix)
                assert keys == [], f"Expected empty list for prefix '{prefix}'"

    @pytest.mark.asyncio
    async def test_list_keys_valid_nested_prefix(self):
        """list_keys should work with valid nested prefixes."""
        from ff_storage.object.local import LocalObjectStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalObjectStorage(tmpdir)

            # Create nested directory structure
            docs_path = Path(tmpdir) / "docs" / "reports"
            docs_path.mkdir(parents=True)
            (docs_path / "q1.pdf").write_text("report content")

            # List with valid prefix
            keys = await storage.list_keys("docs/reports")
            assert "docs/reports/q1.pdf" in keys

    @pytest.mark.asyncio
    async def test_list_keys_nonexistent_prefix(self):
        """list_keys should return empty for nonexistent prefix."""
        from ff_storage.object.local import LocalObjectStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalObjectStorage(tmpdir)

            keys = await storage.list_keys("nonexistent/path")
            assert keys == []

    @pytest.mark.asyncio
    async def test_list_keys_prefix_collision_blocked(self):
        """list_keys should not allow prefix collision attacks."""
        from ff_storage.object.local import LocalObjectStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create base and sibling directories
            base_path = Path(tmpdir) / "storage"
            base_path.mkdir()
            (base_path / "legit.txt").write_text("legit")

            sibling_path = Path(tmpdir) / "storage2"
            sibling_path.mkdir()
            (sibling_path / "secret.txt").write_text("secret")

            storage = LocalObjectStorage(str(base_path))

            # Attempt prefix collision
            keys = await storage.list_keys("../storage2")
            assert keys == [], "Should not list files from sibling directory"
