#!/bin/bash
# Publish a package to PyPI
# Usage: ./publish_to_pypi.sh <package-name> [--test] [--dry-run]

set -e

PACKAGE_NAME="$1"
USE_TEST_PYPI=false
DRY_RUN=false

# Parse flags
shift || true
while [[ $# -gt 0 ]]; do
    case "$1" in
        --test)
            USE_TEST_PYPI=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# List of supported packages (easily extensible)
SUPPORTED_PACKAGES=("ff-storage" "ff-logger")

# Usage
usage() {
    echo "Usage: $0 <package-name> [--test] [--dry-run]"
    echo ""
    echo "Supported packages:"
    for pkg in "${SUPPORTED_PACKAGES[@]}"; do
        echo "  - $pkg"
    done
    echo ""
    echo "Options:"
    echo "  --test       Publish to TestPyPI instead of production PyPI"
    echo "  --dry-run    Build and check, but don't actually publish"
    echo ""
    echo "Authentication:"
    echo "  Set PYPI_TOKEN environment variable or configure ~/.pypirc"
    echo "  For TestPyPI, set TEST_PYPI_TOKEN"
    echo ""
    echo "Examples:"
    echo "  $0 ff-storage                    # Publish to PyPI"
    echo "  $0 ff-logger --test              # Publish to TestPyPI"
    echo "  $0 ff-storage --dry-run          # Build and check only"
    exit 1
}

# Validate input
if [ -z "$PACKAGE_NAME" ]; then
    echo "Error: Package name required"
    usage
fi

# Check if package is supported
if [[ ! " ${SUPPORTED_PACKAGES[@]} " =~ " ${PACKAGE_NAME} " ]]; then
    echo "Error: Package '$PACKAGE_NAME' is not in the supported list"
    usage
fi

# Check if package directory exists
if [ ! -d "$PACKAGE_NAME" ]; then
    echo "Error: Package directory '$PACKAGE_NAME' not found"
    exit 1
fi

cd "$PACKAGE_NAME"

# Extract package metadata
echo "Reading package metadata..."
PYPI_NAME=$(python3 -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
    print(data['project']['name'])
")

VERSION=$(python3 -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
    print(data['project']['version'])
")

if [ "$USE_TEST_PYPI" = true ]; then
    PYPI_URL="https://test.pypi.org"
    PYPI_API_URL="https://test.pypi.org/pypi"
    REPOSITORY="testpypi"
else
    PYPI_URL="https://pypi.org"
    PYPI_API_URL="https://pypi.org/pypi"
    REPOSITORY="pypi"
fi

echo "============================================="
echo "PyPI Publishing Script"
echo "============================================="
echo "Package:      $PYPI_NAME"
echo "Version:      $VERSION"
echo "Target:       $REPOSITORY"
echo "Dry run:      $DRY_RUN"
echo "============================================="
echo ""

# Check if version exists on PyPI
echo "Checking if version $VERSION already exists on $REPOSITORY..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${PYPI_API_URL}/${PYPI_NAME}/${VERSION}/json" || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    echo "⚠️  Version $VERSION already exists on $REPOSITORY"
    echo "   URL: ${PYPI_URL}/project/${PYPI_NAME}/${VERSION}/"
    echo ""
    read -p "Version exists. Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborting."
        exit 0
    fi
elif [ "$HTTP_CODE" = "404" ]; then
    echo "✓ Version $VERSION not found on $REPOSITORY (ready to publish)"
else
    echo "⚠️  Could not check version on $REPOSITORY (HTTP $HTTP_CODE)"
    echo "   Continuing anyway..."
fi

echo ""
echo "Cleaning previous builds..."
rm -rf dist/ build/ *.egg-info
echo "✓ Cleaned build directories"

echo ""
echo "Building package..."
if ! python3 -m build; then
    echo "Error: Build failed"
    exit 1
fi
echo "✓ Built package"

echo ""
echo "Build artifacts:"
ls -lh dist/
echo ""

# Check package with twine
echo "Checking package with twine..."
if ! python3 -m twine check dist/*; then
    echo "Error: Package check failed"
    exit 1
fi
echo "✓ Package check passed"

if [ "$DRY_RUN" = true ]; then
    echo ""
    echo "============================================="
    echo "[DRY RUN] Would upload to $REPOSITORY:"
    echo "============================================="
    ls -1 dist/
    echo ""
    echo "[DRY RUN] No changes made"
    exit 0
fi

# Check authentication
echo ""
if [ "$USE_TEST_PYPI" = true ]; then
    if [ -z "$TEST_PYPI_TOKEN" ]; then
        echo "⚠️  TEST_PYPI_TOKEN not set"
        echo "   Set it with: export TEST_PYPI_TOKEN=pypi-..."
        echo "   Or configure ~/.pypirc with [testpypi] section"
    else
        echo "✓ Using TEST_PYPI_TOKEN from environment"
    fi
else
    if [ -z "$PYPI_TOKEN" ]; then
        echo "⚠️  PYPI_TOKEN not set"
        echo "   Set it with: export PYPI_TOKEN=pypi-..."
        echo "   Or configure ~/.pypirc with [pypi] section"
    else
        echo "✓ Using PYPI_TOKEN from environment"
    fi
fi

echo ""
echo "Ready to publish $PYPI_NAME v$VERSION to $REPOSITORY"
read -p "Proceed with upload? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborting."
    exit 0
fi

echo ""
echo "Publishing to $REPOSITORY..."

# Build twine upload command
UPLOAD_CMD="python3 -m twine upload --repository $REPOSITORY"

# Add token if available
if [ "$USE_TEST_PYPI" = true ] && [ -n "$TEST_PYPI_TOKEN" ]; then
    UPLOAD_CMD="$UPLOAD_CMD --username __token__ --password $TEST_PYPI_TOKEN"
elif [ "$USE_TEST_PYPI" = false ] && [ -n "$PYPI_TOKEN" ]; then
    UPLOAD_CMD="$UPLOAD_CMD --username __token__ --password $PYPI_TOKEN"
fi

UPLOAD_CMD="$UPLOAD_CMD --verbose dist/*"

# Execute upload
if eval "$UPLOAD_CMD"; then
    echo ""
    echo "============================================="
    echo "✓ Successfully published $PYPI_NAME v$VERSION"
    echo "============================================="
    echo ""
    echo "Package URL: ${PYPI_URL}/project/${PYPI_NAME}/${VERSION}/"
    echo ""
    echo "Installation:"
    if [ "$USE_TEST_PYPI" = true ]; then
        echo "  pip install --index-url https://test.pypi.org/simple/ $PYPI_NAME"
    else
        echo "  pip install $PYPI_NAME"
        echo "  uv pip install $PYPI_NAME"
    fi
    echo ""

    # Offer to create git tag
    TAG_NAME="${PACKAGE_NAME}-v${VERSION}"
    echo "Would you like to create a git tag?"
    echo "Tag: $TAG_NAME"
    read -p "Create tag? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cd ..
        if git rev-parse "$TAG_NAME" >/dev/null 2>&1; then
            echo "⚠️  Tag $TAG_NAME already exists"
        else
            git tag -a "$TAG_NAME" -m "Release $PYPI_NAME version $VERSION"
            echo "✓ Created tag $TAG_NAME"
            echo ""
            echo "Push tag with: git push origin $TAG_NAME"
        fi
    fi
else
    echo ""
    echo "Error: Upload failed"
    exit 1
fi
