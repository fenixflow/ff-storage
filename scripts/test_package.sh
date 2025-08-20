#!/bin/bash
# Test a package locally before publishing
# Usage: ./test_package.sh <package-name>

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

echo "Testing package: $PACKAGE_NAME"
echo "================================"

# Change to package directory
cd "$PACKAGE_NAME"

# Create a virtual environment for testing
echo "Creating test environment..."
uv venv .test-env
source .test-env/bin/activate

# Install the package with dev dependencies
echo "Installing package with dev dependencies..."
uv sync --extra dev

# Run tests if they exist
if [ -d "tests" ]; then
    echo ""
    echo "Running tests..."
    echo "----------------"
    uv run pytest tests/ -v
else
    echo "No tests directory found"
fi

# Run linting
echo ""
echo "Running linting checks..."
echo "------------------------"

# Run ruff
echo "Running ruff..."
uv run ruff check src/ || true

# Run black
echo "Running black..."
uv run black --check src/ || true

# Try importing the package
echo ""
echo "Testing imports..."
echo "-----------------"
uv run python -c "
import sys
sys.path.insert(0, 'src')
try:
    import ff_storage
    print(f'✓ Successfully imported ff_storage')
    print(f'  Version: {ff_storage.__version__}')
    
    # Test specific imports
    from ff_storage import Postgres, PostgresPool, MySQL, MySQLPool, MigrationManager
    print('✓ All main exports imported successfully')
except ImportError as e:
    print(f'✗ Import failed: {e}')
    sys.exit(1)
"

# Clean up
deactivate
rm -rf .test-env

echo ""
echo "================================"
echo "✓ Package test completed successfully!"
echo "================================"