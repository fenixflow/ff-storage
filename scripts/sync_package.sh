#!/bin/bash
# Sync a package - test, build, mirror to GitHub, and publish to PyPI
# Usage: ./sync_package.sh <package-name> [--skip-tests] [--skip-github] [--skip-pypi] [--test-pypi] [--dry-run]

set -e

PACKAGE_NAME="$1"
SKIP_TESTS=false
SKIP_GITHUB=false
SKIP_PYPI=false
USE_TEST_PYPI=false
DRY_RUN=false

# Parse flags
shift || true
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --skip-github)
            SKIP_GITHUB=true
            shift
            ;;
        --skip-pypi)
            SKIP_PYPI=true
            shift
            ;;
        --test-pypi)
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
    echo "Usage: $0 <package-name> [options]"
    echo ""
    echo "Supported packages:"
    for pkg in "${SUPPORTED_PACKAGES[@]}"; do
        echo "  - $pkg"
    done
    echo ""
    echo "Options:"
    echo "  --skip-tests     Skip running tests"
    echo "  --skip-github    Skip mirroring to GitHub"
    echo "  --skip-pypi      Skip publishing to PyPI"
    echo "  --test-pypi      Use TestPyPI instead of production PyPI"
    echo "  --dry-run        Show what would be done without doing it"
    echo ""
    echo "This script performs the following steps:"
    echo "  1. Run package tests"
    echo "  2. Build package"
    echo "  3. Mirror to GitHub"
    echo "  4. Publish to PyPI"
    echo ""
    echo "Examples:"
    echo "  $0 ff-storage                           # Full sync"
    echo "  $0 ff-logger --skip-tests               # Skip tests"
    echo "  $0 ff-storage --test-pypi               # Use TestPyPI"
    echo "  $0 ff-logger --skip-github --skip-pypi  # Only test and build"
    echo "  $0 ff-storage --dry-run                 # Preview actions"
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

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================="
echo "Package Sync Script"
echo "============================================="
echo "Package:       $PACKAGE_NAME"
echo "Skip tests:    $SKIP_TESTS"
echo "Skip GitHub:   $SKIP_GITHUB"
echo "Skip PyPI:     $SKIP_PYPI"
echo "Use TestPyPI:  $USE_TEST_PYPI"
echo "Dry run:       $DRY_RUN"
echo "============================================="
echo ""

# Step 1: Run Tests
if [ "$SKIP_TESTS" = false ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Step 1/4: Running Tests"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    if [ "$DRY_RUN" = false ]; then
        if [ -f "$SCRIPT_DIR/test_package.sh" ]; then
            "$SCRIPT_DIR/test_package.sh" "$PACKAGE_NAME"
        else
            echo "Running pytest directly..."
            cd "$PACKAGE_NAME"
            pytest tests/ -v
            cd ..
        fi
        echo "✓ Tests passed"
    else
        echo "[DRY RUN] Would run: $SCRIPT_DIR/test_package.sh $PACKAGE_NAME"
    fi
    echo ""
else
    echo "⊘ Skipping tests"
    echo ""
fi

# Step 2: Build Package
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2/4: Building Package"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$DRY_RUN" = false ]; then
    cd "$PACKAGE_NAME"
    echo "Cleaning previous builds..."
    rm -rf dist/ build/ *.egg-info
    echo "Building..."
    python3 -m build
    echo "✓ Built package"
    cd ..
else
    echo "[DRY RUN] Would clean and build $PACKAGE_NAME"
fi
echo ""

# Step 3: Mirror to GitHub
if [ "$SKIP_GITHUB" = false ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Step 3/4: Mirroring to GitHub"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    GITHUB_FLAGS=""
    if [ "$DRY_RUN" = true ]; then
        GITHUB_FLAGS="--dry-run"
    fi

    if [ "$DRY_RUN" = false ] || [ "$DRY_RUN" = true ]; then
        "$SCRIPT_DIR/mirror_to_github.sh" "$PACKAGE_NAME" $GITHUB_FLAGS
    fi
    echo ""
else
    echo "⊘ Skipping GitHub mirror"
    echo ""
fi

# Step 4: Publish to PyPI
if [ "$SKIP_PYPI" = false ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Step 4/4: Publishing to PyPI"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    PYPI_FLAGS=""
    if [ "$USE_TEST_PYPI" = true ]; then
        PYPI_FLAGS="--test"
    fi
    if [ "$DRY_RUN" = true ]; then
        PYPI_FLAGS="$PYPI_FLAGS --dry-run"
    fi

    "$SCRIPT_DIR/publish_to_pypi.sh" "$PACKAGE_NAME" $PYPI_FLAGS
    echo ""
else
    echo "⊘ Skipping PyPI publish"
    echo ""
fi

# Summary
echo "============================================="
if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Sync preview completed"
else
    echo "✓ Package sync completed successfully"
fi
echo "============================================="
echo ""
echo "Package: $PACKAGE_NAME"
echo ""
if [ "$SKIP_TESTS" = false ]; then
    echo "✓ Tests passed"
fi
if [ "$DRY_RUN" = false ]; then
    echo "✓ Package built"
fi
if [ "$SKIP_GITHUB" = false ]; then
    if [ "$DRY_RUN" = false ]; then
        echo "✓ Mirrored to GitHub: https://github.com/fenixflow/${PACKAGE_NAME}"
    else
        echo "⊙ Would mirror to GitHub"
    fi
fi
if [ "$SKIP_PYPI" = false ]; then
    if [ "$USE_TEST_PYPI" = true ]; then
        if [ "$DRY_RUN" = false ]; then
            echo "✓ Published to TestPyPI"
        else
            echo "⊙ Would publish to TestPyPI"
        fi
    else
        if [ "$DRY_RUN" = false ]; then
            echo "✓ Published to PyPI"
        else
            echo "⊙ Would publish to PyPI"
        fi
    fi
fi
echo ""
