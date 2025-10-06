#!/usr/bin/env python3
"""
Bump package version based on current version in GitLab Package Registry.

This script:
1. Queries the GitLab Package Registry API for the current version
2. Applies the requested version bump (patch/minor/major)
3. Updates the pyproject.toml file with the new version
4. Returns the new version for use in CI/CD

Usage:
    python bump_version_from_registry.py <package-name> <bump-type>
    
    package-name: ff-storage, ff-logger, ff-cli, ff-parsers
    bump-type: patch, minor, major
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def get_current_version_from_registry(package_name, api_url, project_id, token):
    """
    Fetch the current version from GitLab Package Registry.
    
    Returns the latest version or "0.0.0" if package not found.
    """
    # Convert package name to underscore format for PyPI
    package_underscore = package_name.replace("-", "_")

    # GitLab API endpoint for package list
    packages_url = f"{api_url}/projects/{project_id}/packages"

    # Add query parameters to filter by package type and name
    packages_url += f"?package_type=pypi&package_name={package_underscore}"

    headers = {
        "PRIVATE-TOKEN": token
    }

    try:
        req = urllib.request.Request(packages_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            packages = json.loads(response.read())

        if not packages:
            print(f"Package {package_name} not found in registry, starting from 0.0.0")
            return "0.0.0"

        # Get the highest version (packages are usually sorted newest first)
        versions = []
        for pkg in packages:
            if pkg.get("version"):
                versions.append(pkg["version"])

        if not versions:
            print(f"No versions found for {package_name}, starting from 0.0.0")
            return "0.0.0"

        # Sort versions and get the latest
        versions.sort(key=lambda v: list(map(int, v.split("."))))
        latest_version = versions[-1]

        print(f"Current version in registry for {package_name}: {latest_version}")
        return latest_version

    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"Package {package_name} not found in registry, starting from 0.0.0")
            return "0.0.0"
        else:
            print(f"Error fetching package info: {e}")
            raise
    except Exception as e:
        print(f"Error querying registry: {e}")
        raise


def bump_version(version, bump_type):
    """
    Apply semantic version bump to a version string.
    
    Args:
        version: Current version string (e.g., "1.2.3")
        bump_type: Type of bump ("patch", "minor", "major")
    
    Returns:
        New version string
    """
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {version}")

    major, minor, patch = map(int, parts)

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "patch":
        patch += 1
    else:
        raise ValueError(f"Invalid bump type: {bump_type}")

    return f"{major}.{minor}.{patch}"


def update_pyproject_toml(package_name, new_version):
    """
    Update the version in the package's pyproject.toml file.
    
    Args:
        package_name: Name of the package directory
        new_version: New version string to set
    """
    pyproject_path = Path(package_name) / "pyproject.toml"

    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found for {package_name}")

    # Read the current content
    with open(pyproject_path) as f:
        content = f.read()

    # Replace the version line
    lines = content.split("\n")
    new_lines = []
    version_updated = False

    for line in lines:
        if line.startswith("version = ") and not version_updated:
            new_lines.append(f'version = "{new_version}"')
            version_updated = True
        else:
            new_lines.append(line)

    if not version_updated:
        raise ValueError(f"Could not find version line in {pyproject_path}")

    # Write back the updated content
    with open(pyproject_path, "w") as f:
        f.write("\n".join(new_lines))

    print(f"Updated {pyproject_path} to version {new_version}")


def main():
    """Main function to handle version bumping."""
    if len(sys.argv) != 3:
        print("Usage: python bump_version_from_registry.py <package-name> <bump-type>")
        print("  package-name: ff-storage, ff-logger, ff-cli, ff-parsers")
        print("  bump-type: patch, minor, major")
        sys.exit(1)

    package_name = sys.argv[1]
    bump_type = sys.argv[2]

    # Get environment variables from GitLab CI
    api_url = os.environ.get("CI_API_V4_URL")
    project_id = os.environ.get("CI_PROJECT_ID")
    token = os.environ.get("CI_JOB_TOKEN")

    if not all([api_url, project_id, token]):
        print("Error: Required GitLab CI environment variables not found")
        print("This script should be run in a GitLab CI pipeline")
        sys.exit(1)

    # Validate inputs
    valid_packages = ["ff-storage", "ff-logger", "ff-cli", "ff-parsers"]
    if package_name not in valid_packages:
        print(f"Error: Invalid package name: {package_name}")
        print(f"Valid packages: {', '.join(valid_packages)}")
        sys.exit(1)

    valid_bump_types = ["patch", "minor", "major"]
    if bump_type not in valid_bump_types:
        print(f"Error: Invalid bump type: {bump_type}")
        print(f"Valid types: {', '.join(valid_bump_types)}")
        sys.exit(1)

    try:
        # Get current version from registry
        current_version = get_current_version_from_registry(
            package_name, api_url, project_id, token
        )

        # Calculate new version
        new_version = bump_version(current_version, bump_type)
        print(f"Bumping {package_name} from {current_version} to {new_version} ({bump_type})")

        # Update pyproject.toml
        update_pyproject_toml(package_name, new_version)

        # Output the new version for use in CI
        print(f"NEW_VERSION={new_version}")

        # Also write to a file for easier consumption in CI
        with open(f"{package_name}_new_version.txt", "w") as f:
            f.write(new_version)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
