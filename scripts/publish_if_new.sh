#!/bin/bash
# Publish a package to GitLab Package Registry if the version is new
# Usage: ./publish_if_new.sh <package-name>

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

# Extract package info from pyproject.toml
cd "$PACKAGE_NAME"

# Get the package name and version from pyproject.toml
PYPI_NAME=$(python -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
    print(data['project']['name'])
")

VERSION=$(python -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
    print(data['project']['version'])
")

echo "Package: $PYPI_NAME"
echo "Version: $VERSION"

# Check if CI variables are set
if [ -z "$CI_PROJECT_ID" ]; then
    echo "Error: CI_PROJECT_ID not set. This script should run in GitLab CI."
    exit 1
fi

# GitLab Package Registry URL
REGISTRY_URL="${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/packages/pypi"

# Check if this version already exists in the registry
echo "Checking if version $VERSION already exists in registry..."

# Use GitLab API to check if package version exists
PACKAGE_EXISTS=$(curl -s -o /dev/null -w "%{http_code}" \
    --header "PRIVATE-TOKEN: ${CI_JOB_TOKEN}" \
    "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/packages?package_name=${PYPI_NAME}&package_version=${VERSION}")

if [ "$PACKAGE_EXISTS" = "200" ]; then
    # Check if the response actually contains our package
    PACKAGE_CHECK=$(curl -s \
        --header "PRIVATE-TOKEN: ${CI_JOB_TOKEN}" \
        "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/packages?package_name=${PYPI_NAME}" | \
        python -c "
import sys, json
data = json.load(sys.stdin)
for pkg in data:
    if pkg.get('name') == '${PYPI_NAME}' and pkg.get('version') == '${VERSION}':
        print('exists')
        sys.exit(0)
print('not_found')
" 2>/dev/null || echo "not_found")
    
    if [ "$PACKAGE_CHECK" = "exists" ]; then
        echo "Version $VERSION already exists in registry. Skipping publish."
        exit 0
    fi
fi

echo "Version $VERSION not found in registry. Publishing..."

# Check if dist directory exists
if [ ! -d "dist" ]; then
    echo "Error: dist directory not found. Run build_package.sh first."
    exit 1
fi

# Install twine for publishing
pip install --upgrade twine

# Create .pypirc for authentication
cat > ~/.pypirc << EOF
[distutils]
index-servers = gitlab

[gitlab]
repository = ${REGISTRY_URL}
username = gitlab-ci-token
password = ${CI_JOB_TOKEN}
EOF

# Publish to GitLab Package Registry
echo "Publishing to GitLab Package Registry..."
python -m twine upload \
    --repository gitlab \
    --verbose \
    dist/*

# Tag the release
if [ "$CI_COMMIT_TAG" = "" ]; then
    TAG_NAME="${PACKAGE_NAME}-v${VERSION}"
    echo "Creating git tag: $TAG_NAME"
    
    # Configure git
    git config --global user.email "gitlab-ci@fenixflow.com"
    git config --global user.name "GitLab CI"
    
    # Create and push tag
    git tag -a "$TAG_NAME" -m "Release $PACKAGE_NAME version $VERSION"
    git push "https://gitlab-ci-token:${CI_JOB_TOKEN}@${CI_SERVER_HOST}/${CI_PROJECT_PATH}.git" "$TAG_NAME" || true
fi

echo "Successfully published $PYPI_NAME version $VERSION to GitLab Package Registry"

# Output installation instructions
echo ""
echo "Installation instructions:"
echo "-------------------------"
echo "1. Create a personal access token or deploy token with 'read_api' scope"
echo "2. Install with uv:"
echo "   uv pip install ${PYPI_NAME} --index-url https://<token_name>:<token>@${CI_SERVER_HOST}/api/v4/projects/${CI_PROJECT_ID}/packages/pypi/simple"
echo ""
echo "Or add to pyproject.toml:"
echo "[[tool.uv.index]]"
echo "name = \"fenixflow\""
echo "url = \"https://<token_name>:<token>@${CI_SERVER_HOST}/api/v4/projects/${CI_PROJECT_ID}/packages/pypi/simple\""