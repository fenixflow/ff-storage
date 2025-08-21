#!/bin/bash
# Check if a specific package version exists in GitLab Package Registry
# Usage: ./check_version_exists.sh <package_name> <version>
# Returns: 0 if version exists, 1 if not

set -e

PACKAGE_NAME=$1
VERSION=$2

# Validate inputs
if [ -z "$PACKAGE_NAME" ] || [ -z "$VERSION" ]; then
    echo "Usage: $0 <package_name> <version>"
    exit 2
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# GitLab API endpoint for package registry
# We'll check if the package file exists
PROJECT_ID="${CI_PROJECT_ID:-73458224}"  # Default to fenix-packages project ID
GITLAB_URL="${CI_SERVER_URL:-https://gitlab.com}"

# Function to check package in registry
check_package_exists() {
    local package=$1
    local version=$2
    
    # Try to fetch package metadata from GitLab Package Registry
    # We check for the wheel file which should always exist if package was published
    local wheel_file="${package//-/_}-${version}-py3-none-any.whl"
    local api_url="${GITLAB_URL}/api/v4/projects/${PROJECT_ID}/packages/pypi/files/${package//-/_}/${version}/${wheel_file}"
    
    echo "Checking if ${package} version ${version} exists in registry..."
    echo "API URL: ${api_url}"
    
    # Use curl to check if the file exists (HEAD request)
    # We don't need auth for public packages, but we'll use CI token if available
    if [ -n "$CI_JOB_TOKEN" ]; then
        response=$(curl -s -o /dev/null -w "%{http_code}" --head \
            --header "JOB-TOKEN: ${CI_JOB_TOKEN}" \
            "${api_url}")
    else
        response=$(curl -s -o /dev/null -w "%{http_code}" --head "${api_url}")
    fi
    
    if [ "$response" = "200" ] || [ "$response" = "302" ]; then
        echo -e "${YELLOW}Version ${version} of ${package} already exists in registry${NC}"
        return 0
    elif [ "$response" = "404" ]; then
        echo -e "${GREEN}Version ${version} of ${package} does not exist in registry${NC}"
        return 1
    else
        echo -e "${RED}Unexpected response code: ${response}${NC}"
        echo "This might indicate a network or authentication issue"
        # Return 1 (not exists) to allow publishing to proceed
        # Better to try and fail than to block unnecessarily
        return 1
    fi
}

# Check if version exists
if check_package_exists "$PACKAGE_NAME" "$VERSION"; then
    exit 0  # Version exists
else
    exit 1  # Version does not exist
fi