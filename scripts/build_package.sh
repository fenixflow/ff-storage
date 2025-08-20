#!/bin/bash
# Build a specific package
# Usage: ./build_package.sh <package-name>

set -e

PACKAGE_NAME="$1"

if [ -z "$PACKAGE_NAME" ]; then
    echo "Error: Package name required"
    echo "Usage: $0 <package-name>"
    exit 1
fi

if [ ! -d "$PACKAGE_NAME" ]; then
    echo "Error: Package directory '$PACKAGE_NAME' not found"
    exit 1
fi

if [ ! -f "$PACKAGE_NAME/pyproject.toml" ]; then
    echo "Error: No pyproject.toml found in '$PACKAGE_NAME'"
    exit 1
fi

echo "Building package: $PACKAGE_NAME"

# Change to package directory
cd "$PACKAGE_NAME"

# Clean previous builds
rm -rf dist/ build/ *.egg-info src/*.egg-info

# Install build dependencies
echo "Installing build dependencies..."
# In CI, use pip directly; locally, use uv
if [ -n "$CI" ]; then
    pip install --upgrade build wheel setuptools
else
    uv pip install --upgrade build wheel setuptools
fi

# Build the package
echo "Building distribution packages..."
if [ -n "$CI" ]; then
    python -m build
else
    uv run python -m build
fi

# List built files
echo "Built packages:"
ls -la dist/

# Verify the wheel (optional, may not be available)
echo "Verifying wheel..."
if [ -n "$CI" ]; then
    pip install check-wheel-contents 2>/dev/null && check-wheel-contents dist/*.whl || true
else
    uv pip install check-wheel-contents 2>/dev/null && uv run check-wheel-contents dist/*.whl || true
fi

echo "Build completed successfully for $PACKAGE_NAME"