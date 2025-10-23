"""GitHub utilities for mirroring packages."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .constants import GITHUB_REPOS, REPO_ROOT


def get_github_url(package_name: str) -> str:
    """Get GitHub URL for a package, using token auth if available.

    Args:
        package_name: Name of the package (e.g., 'ff-storage')

    Returns:
        GitHub repository URL (HTTPS with token or SSH)
    """
    # Check for GITHUB_TOKEN environment variable
    token = os.getenv("GITHUB_TOKEN")

    if token:
        # Use HTTPS with token authentication
        return f"https://{token}@github.com/fenixflow/{package_name}.git"
    else:
        # Fall back to SSH URL from constants
        return GITHUB_REPOS.get(package_name, f"git@github.com:fenixflow/{package_name}.git")


def check_git_status() -> tuple[bool, str, list[str]]:
    """Check git repository status.

    Returns:
        Tuple of (is_clean, current_branch, uncommitted_files)
    """
    try:
        # Get current branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        )
        current_branch = result.stdout.strip()

        # Check for uncommitted changes
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        uncommitted = [line.strip() for line in result.stdout.split("\n") if line.strip()]

        is_clean = len(uncommitted) == 0

        return is_clean, current_branch, uncommitted

    except subprocess.CalledProcessError as e:
        return False, "", [f"Git error: {e.stderr}"]


def get_remote_url(remote_name: str) -> str | None:
    """Get URL for a git remote.

    Args:
        remote_name: Name of the remote

    Returns:
        Remote URL or None if not found
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", remote_name],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


def add_github_remote(package_name: str) -> tuple[bool, str]:
    """Add GitHub remote for a package.

    Args:
        package_name: Name of the package (e.g., 'ff-storage')

    Returns:
        Tuple of (success, message)
    """
    github_url = get_github_url(package_name)
    remote_name = f"github-{package_name.split('-')[1]}"  # e.g., github-storage

    # Check if remote already exists
    existing_url = get_remote_url(remote_name)

    if existing_url:
        if existing_url == github_url:
            return True, f"Remote {remote_name} already configured correctly"
        else:
            # Update URL
            try:
                subprocess.run(
                    ["git", "remote", "set-url", remote_name, github_url],
                    check=True,
                    capture_output=True,
                )
                return True, f"Updated remote {remote_name} URL"
            except subprocess.CalledProcessError as e:
                return False, f"Failed to update remote: {e.stderr}"

    # Add new remote
    try:
        subprocess.run(
            ["git", "remote", "add", remote_name, github_url],
            check=True,
            capture_output=True,
        )
        return True, f"Added remote {remote_name}"
    except subprocess.CalledProcessError as e:
        return False, f"Failed to add remote: {e.stderr}"


def push_to_github(
    package_name: str, package_path: str, branch: str = "main"
) -> tuple[bool, str]:
    """Push package snapshot to GitHub from remote origin/main.

    Creates a clean GitHub mirror with:
    - Single commit containing current package state
    - No history (clean slate)
    - Extracted from GitLab's committed origin/main (ignores local changes)
    - Force push to completely replace GitHub repo

    This matches the GitLab CI/CD pipeline behavior by using only committed code.

    Args:
        package_name: Name of the package (e.g., 'ff-storage')
        package_path: Path to package directory (e.g., 'ff-storage')
        branch: Target branch on GitHub (default: 'main')

    Returns:
        Tuple of (success, message)
    """
    # Get GitHub URL with token
    github_url = get_github_url(package_name)

    if not github_url:
        return False, "GitHub URL could not be determined"

    # Create temp directory for mirror
    temp_dir = None

    try:
        # Step 1: Fetch latest from GitLab origin
        subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(REPO_ROOT),
        )

        # Step 2: Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix=f"github-mirror-{package_name}-")
        temp_path = Path(temp_dir)

        # Step 3: Extract package directory from origin/main using git archive
        # This gets ONLY committed code, ignoring local uncommitted changes
        archive_process = subprocess.run(
            ["git", "archive", "origin/main", f"{package_path}/"],
            capture_output=True,
            check=True,
            cwd=str(REPO_ROOT),
        )

        # Extract the archive to temp directory
        subprocess.run(
            ["tar", "-x", "-C", str(temp_path)],
            input=archive_process.stdout,
            check=True,
        )

        # Move package contents to root of temp dir (remove package_path prefix)
        # CRITICAL: Extract basename to prevent absolute path concatenation bug
        package_dir_name = Path(package_path).name  # Gets "ff-storage" from any path format
        package_temp = temp_path / package_dir_name
        if package_temp.exists():
            # Move all contents from package_temp/* to temp_path/
            for item in package_temp.iterdir():
                shutil.move(str(item), str(temp_path / item.name))
            # Remove now-empty package directory
            package_temp.rmdir()

        # Step 4: Initialize git repo in temp directory
        subprocess.run(
            ["git", "init"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(temp_path),
        )

        # Configure git user (required for commit)
        subprocess.run(
            ["git", "config", "user.name", "Fenixflow Bot"],
            capture_output=True,
            check=True,
            cwd=str(temp_path),
        )
        subprocess.run(
            ["git", "config", "user.email", "bot@fenixflow.com"],
            capture_output=True,
            check=True,
            cwd=str(temp_path),
        )

        # Step 5: Add all files and create single commit
        subprocess.run(
            ["git", "add", "."],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(temp_path),
        )

        # Get version from pyproject.toml if available for commit message
        commit_msg = f"Mirror {package_name} from GitLab"
        pyproject = temp_path / "pyproject.toml"
        if pyproject.exists():
            # Try to extract version
            try:
                content = pyproject.read_text()
                for line in content.split("\n"):
                    if line.startswith("version"):
                        version = line.split("=")[1].strip().strip('"')
                        commit_msg = f"Mirror {package_name} v{version}"
                        break
            except Exception:
                pass  # Use default message if version extraction fails

        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(temp_path),
        )

        # Step 6: Force push to GitHub (completely replaces existing content)
        subprocess.run(
            ["git", "push", "--force", github_url, f"HEAD:{branch}"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(temp_path),
        )

        # Step 7: Push package-specific tags from main repo
        # Get all tags matching the package name pattern
        tag_result = subprocess.run(
            ["git", "tag", "-l", f"{package_name}-v*"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(REPO_ROOT),
        )
        tags = [tag.strip() for tag in tag_result.stdout.split("\n") if tag.strip()]

        if tags:
            # Push each tag individually to avoid pushing unrelated tags
            for tag in tags:
                subprocess.run(
                    ["git", "push", "--force", github_url, f"refs/tags/{tag}:refs/tags/{tag}"],
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=str(REPO_ROOT),
                )

        tag_msg = f" and {len(tags)} tag(s)" if tags else ""
        return True, f"Mirrored {package_name} to {branch}{tag_msg}"

    except subprocess.CalledProcessError as e:
        # stderr is already a string when text=True is used
        error_msg = e.stderr if e.stderr else str(e)
        return False, f"Mirror failed: {error_msg}"

    finally:
        # Always clean up temp directory
        if temp_dir and Path(temp_dir).exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
