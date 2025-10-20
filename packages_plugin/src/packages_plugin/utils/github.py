"""GitHub utilities for mirroring packages."""

import subprocess
from pathlib import Path

from .constants import GITHUB_REPOS


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
    if package_name not in GITHUB_REPOS:
        return False, f"Package {package_name} not in supported list"

    github_url = GITHUB_REPOS[package_name]
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


def push_to_github(package_name: str, branch: str | None = None) -> tuple[bool, str]:
    """Push package to GitHub.

    Args:
        package_name: Name of the package
        branch: Branch to push (None for current)

    Returns:
        Tuple of (success, message)
    """
    remote_name = f"github-{package_name.split('-')[1]}"

    # Ensure remote exists
    success, message = add_github_remote(package_name)
    if not success:
        return False, message

    # Get current branch if not specified
    if branch is None:
        _, branch, _ = check_git_status()

    try:
        # Push branch
        result = subprocess.run(
            ["git", "push", remote_name, branch],
            capture_output=True,
            text=True,
            check=True,
        )

        # Push tags
        subprocess.run(
            ["git", "push", remote_name, "--tags"],
            capture_output=True,
            text=True,
            check=True,
        )

        return True, f"Pushed {branch} and tags to GitHub"

    except subprocess.CalledProcessError as e:
        return False, f"Push failed: {e.stderr}"