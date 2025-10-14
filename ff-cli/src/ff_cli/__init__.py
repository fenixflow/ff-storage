"""
FF-CLI: Fenix-wide CLI with plugin architecture.

This package provides a unified CLI for the Fenix ecosystem with support
for project-specific plugins that add namespaced commands.
"""

# Version is read from package metadata (pyproject.toml is the single source of truth)
try:
    from importlib.metadata import version

    __version__ = version("ff-cli")
except Exception:
    __version__ = "0.0.0+unknown"
