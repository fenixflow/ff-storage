"""PyPI utilities for publishing packages."""

import os
import subprocess
import urllib.request
from pathlib import Path

from .constants import PYPI_API_URL, TEST_PYPI_API_URL


def check_pypi_version(package_name: str, version: str, test_pypi: bool = False) -> tuple[bool, str]:
    """Check if a version exists on PyPI.

    Args:
        package_name: PyPI package name
        version: Version to check
        test_pypi: Check TestPyPI instead

    Returns:
        Tuple of (exists, message)
    """
    api_url = TEST_PYPI_API_URL if test_pypi else PYPI_API_URL
    url = f"{api_url}/{package_name}/{version}/json"

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status == 200:
                return True, f"Version {version} exists on {'TestPyPI' if test_pypi else 'PyPI'}"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, f"Version {version} not found on {'TestPyPI' if test_pypi else 'PyPI'}"
        return False, f"Error checking version: HTTP {e.code}"
    except Exception as e:
        return False, f"Error checking version: {e}"

    return False, "Unknown status"


def publish_to_pypi(
    package_path: Path,
    test_pypi: bool = False,
) -> tuple[bool, str]:
    """Publish package to PyPI using twine.

    Args:
        package_path: Path to package directory
        test_pypi: Publish to TestPyPI instead

    Returns:
        Tuple of (success, message)
    """
    dist_path = package_path / "dist"
    if not dist_path.exists() or not list(dist_path.glob("*")):
        return False, "No build artifacts found in dist/"

    # Determine repository and token
    if test_pypi:
        repository = "testpypi"
        token_var = "TEST_PYPI_TOKEN"
    else:
        repository = "pypi"
        token_var = "PYPI_TOKEN"

    token = os.getenv(token_var)

    # Build twine command
    cmd = [
        "python3",
        "-m",
        "twine",
        "upload",
        "--repository",
        repository,
        "--verbose",
    ]

    # Add token if available
    if token:
        cmd.extend(["--username", "__token__", "--password", token])

    cmd.append("dist/*")

    try:
        result = subprocess.run(
            cmd,
            cwd=package_path,
            capture_output=True,
            text=True,
            check=True,
        )

        return True, f"Published to {'TestPyPI' if test_pypi else 'PyPI'} successfully"

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else e.stdout
        return False, f"Upload failed: {error_msg}"
    except Exception as e:
        return False, f"Upload error: {e}"


def create_git_tag(package_name: str, version: str) -> tuple[bool, str]:
    """Create a git tag for the package version.

    Args:
        package_name: Package name (e.g., 'ff-storage')
        version: Version string (e.g., '2.0.1')

    Returns:
        Tuple of (success, message)
    """
    tag_name = f"{package_name}-v{version}"

    # Check if tag already exists
    try:
        result = subprocess.run(
            ["git", "rev-parse", tag_name],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return False, f"Tag {tag_name} already exists"
    except Exception:
        pass

    # Create tag
    try:
        subprocess.run(
            ["git", "tag", "-a", tag_name, "-m", f"Release {package_name} version {version}"],
            capture_output=True,
            text=True,
            check=True,
        )

        return True, f"Created tag {tag_name}"

    except subprocess.CalledProcessError as e:
        return False, f"Failed to create tag: {e.stderr}"


def push_git_tag(tag_name: str, remote: str = "origin") -> tuple[bool, str]:
    """Push a git tag to remote.

    Args:
        tag_name: Tag name to push
        remote: Remote name (default: origin)

    Returns:
        Tuple of (success, message)
    """
    try:
        subprocess.run(
            ["git", "push", remote, tag_name],
            capture_output=True,
            text=True,
            check=True,
        )

        return True, f"Pushed tag {tag_name} to {remote}"

    except subprocess.CalledProcessError as e:
        return False, f"Failed to push tag: {e.stderr}"
