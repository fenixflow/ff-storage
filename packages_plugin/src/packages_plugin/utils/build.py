"""Build utilities for package building."""

import shutil
import subprocess
from pathlib import Path


def clean_build(package_path: Path) -> None:
    """Clean build artifacts from package directory.

    Args:
        package_path: Path to package directory
    """
    directories_to_clean = ["dist", "build", "*.egg-info"]

    for pattern in directories_to_clean:
        if "*" in pattern:
            # Handle glob patterns
            for item in package_path.glob(pattern):
                if item.is_dir():
                    shutil.rmtree(item)
        else:
            item = package_path / pattern
            if item.exists():
                shutil.rmtree(item)


def build_package(package_path: Path) -> tuple[bool, str]:
    """Build a package using python -m build.

    Args:
        package_path: Path to package directory

    Returns:
        Tuple of (success, message)
    """
    try:
        # Clean first
        clean_build(package_path)

        # Run build
        result = subprocess.run(
            ["python3", "-m", "build"],
            cwd=package_path,
            capture_output=True,
            text=True,
            check=True,
        )

        return True, "Package built successfully"

    except subprocess.CalledProcessError as e:
        return False, f"Build failed: {e.stderr}"
    except Exception as e:
        return False, f"Build error: {e}"


def check_package(package_path: Path) -> tuple[bool, str]:
    """Check package with twine.

    Args:
        package_path: Path to package directory

    Returns:
        Tuple of (success, message)
    """
    dist_path = package_path / "dist"
    if not dist_path.exists():
        return False, "No dist/ directory found"

    try:
        result = subprocess.run(
            ["python3", "-m", "twine", "check", "dist/*"],
            cwd=package_path,
            capture_output=True,
            text=True,
            check=True,
            shell=True,
        )

        return True, "Package check passed"

    except subprocess.CalledProcessError as e:
        return False, f"Package check failed: {e.stderr}"
    except Exception as e:
        return False, f"Check error: {e}"


def get_package_info(package_path: Path) -> dict[str, str]:
    """Get package name and version from pyproject.toml.

    Args:
        package_path: Path to package directory

    Returns:
        Dictionary with 'name' and 'version' keys
    """
    import tomli

    pyproject_path = package_path / "pyproject.toml"

    with open(pyproject_path, "rb") as f:
        data = tomli.load(f)

    return {
        "name": data["project"]["name"],
        "version": data["project"]["version"],
    }