"""Constants for package publishing."""

from pathlib import Path

# Repository root path
# Plugin location: fenix-packages/packages_plugin/src/packages_plugin/utils/constants.py
# Repo root is 4 levels up from this file
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent

# Supported packages for publishing
SUPPORTED_PACKAGES = ["ff-storage", "ff-logger"]

# GitHub repository mapping
GITHUB_REPOS = {
    "ff-storage": "git@github.com:fenixflow/ff-storage.git",
    "ff-logger": "git@github.com:fenixflow/ff-logger.git",
}

# PyPI URLs
PYPI_URL = "https://pypi.org"
PYPI_API_URL = "https://pypi.org/pypi"
TEST_PYPI_URL = "https://test.pypi.org"
TEST_PYPI_API_URL = "https://test.pypi.org/pypi"
