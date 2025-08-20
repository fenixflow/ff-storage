#!/bin/bash
# Build all packages locally (for development/testing)
# This script is for manual use, not used by CI/CD

set -e

echo "Building all Fenix packages..."
echo "================================"

# Find all packages (directories with pyproject.toml)
PACKAGES=()
for dir in */; do
    if [ -f "${dir}pyproject.toml" ]; then
        PACKAGES+=("${dir%/}")
    fi
done

if [ ${#PACKAGES[@]} -eq 0 ]; then
    echo "No packages found!"
    exit 1
fi

echo "Found packages: ${PACKAGES[*]}"
echo ""

# Build each package
SUCCESS_COUNT=0
FAILED_PACKAGES=()

for package in "${PACKAGES[@]}"; do
    echo "----------------------------------------"
    echo "Building: $package"
    echo "----------------------------------------"
    
    if ./scripts/build_package.sh "$package"; then
        echo "✓ Successfully built $package"
        ((SUCCESS_COUNT++))
    else
        echo "✗ Failed to build $package"
        FAILED_PACKAGES+=("$package")
    fi
    echo ""
done

# Summary
echo "================================"
echo "Build Summary"
echo "================================"
echo "Total packages: ${#PACKAGES[@]}"
echo "Successful: $SUCCESS_COUNT"
echo "Failed: ${#FAILED_PACKAGES[@]}"

if [ ${#FAILED_PACKAGES[@]} -gt 0 ]; then
    echo ""
    echo "Failed packages:"
    for package in "${FAILED_PACKAGES[@]}"; do
        echo "  - $package"
    done
    exit 1
fi

echo ""
echo "All packages built successfully!"