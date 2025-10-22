"""Authentication checking utilities for GitHub and PyPI."""

import os
import subprocess
from pathlib import Path


def check_github_auth() -> tuple[bool, str]:
    """Check if GitHub authentication is configured.

    Returns:
        Tuple of (is_authenticated, message)
    """
    # First check for GITHUB_TOKEN (preferred for CI/CD and consistency with PyPI)
    token = os.getenv("GITHUB_TOKEN")
    if token:
        # GitHub tokens can start with: ghp_ (personal), gho_ (OAuth), ghs_ (server), github_pat_ (fine-grained)
        if token.startswith(("ghp_", "gho_", "ghs_", "github_pat_")):
            return True, "GitHub token found in environment"
        return False, "GITHUB_TOKEN doesn't look like a valid GitHub token"

    # Fall back to SSH key check
    ssh_key_paths = [
        Path.home() / ".ssh" / "id_ed25519",
        Path.home() / ".ssh" / "id_rsa",
    ]

    has_ssh_key = any(p.exists() for p in ssh_key_paths)

    if not has_ssh_key:
        return False, "No GitHub token or SSH key found"

    # Test GitHub connection
    try:
        result = subprocess.run(
            ["ssh", "-T", "git@github.com"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # SSH to GitHub returns 1 even on success with message about authentication
        if "successfully authenticated" in result.stderr.lower():
            return True, "GitHub SSH authentication working"
        return False, f"GitHub SSH test failed: {result.stderr}"
    except subprocess.TimeoutExpired:
        return False, "GitHub SSH connection timed out"
    except Exception as e:
        return False, f"Error testing GitHub SSH: {e}"


def check_pypi_auth(test_pypi: bool = False) -> tuple[bool, str]:
    """Check if PyPI authentication is configured.

    Args:
        test_pypi: Check TestPyPI token instead of production

    Returns:
        Tuple of (is_authenticated, message)
    """
    if test_pypi:
        token_var = "TEST_PYPI_TOKEN"
        pypi_name = "TestPyPI"
    else:
        token_var = "PYPI_TOKEN"
        pypi_name = "PyPI"

    token = os.getenv(token_var)

    if not token:
        # Check .pypirc
        pypirc_path = Path.home() / ".pypirc"
        if pypirc_path.exists():
            return (
                True,
                f"{pypi_name} configured in ~/.pypirc (token not in env)",
            )
        return False, f"{token_var} not set and ~/.pypirc not found"

    if not token.startswith("pypi-"):
        return False, f"{token_var} doesn't look like a valid PyPI token"

    return True, f"{pypi_name} token found in environment"


def check_all_auth() -> dict[str, tuple[bool, str]]:
    """Check all authentication requirements.

    Returns:
        Dictionary with auth check results
    """
    return {
        "github": check_github_auth(),
        "pypi": check_pypi_auth(test_pypi=False),
        "test_pypi": check_pypi_auth(test_pypi=True),
    }
