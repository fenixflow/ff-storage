#!/bin/bash
# Automatically bump package versions based on commit messages
# Usage: ./bump_version.sh [--commit-back]
#
# Commit message tags:
#   [major] - Breaking changes (0.1.0 -> 1.0.0)
#   [minor] - New features (0.1.0 -> 0.2.0)
#   [patch] or no tag - Bug fixes (0.1.0 -> 0.1.1)
#   [skip-version] - Don't bump version
#   [skip-ci] - Skip CI entirely (used by CI commits)

set -e

# Parse arguments
COMMIT_BACK=false
if [ "$1" = "--commit-back" ]; then
    COMMIT_BACK=true
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "==================================="
echo "Version Bump Script"
echo "==================================="

# Function to bump version
bump_version() {
    local current_version=$1
    local bump_type=$2
    
    # Parse current version
    IFS='.' read -r major minor patch <<< "$current_version"
    
    case $bump_type in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch)
            patch=$((patch + 1))
            ;;
        none)
            # No change
            ;;
        *)
            echo -e "${RED}Unknown bump type: $bump_type${NC}"
            exit 1
            ;;
    esac
    
    echo "$major.$minor.$patch"
}

# Get commit message(s) to analyze
if [ -n "$CI_MERGE_REQUEST_IID" ]; then
    # In a merge request, check all commits in the MR
    echo "Analyzing merge request commits..."
    COMMIT_MSGS=$(git log --format=%B origin/main..HEAD 2>/dev/null || git log -1 --format=%B)
elif [ -n "$CI_COMMIT_SHA" ]; then
    # In CI, check the current commit
    echo "Analyzing current commit..."
    COMMIT_MSGS=$(git log -1 --format=%B)
else
    # Local run, check the last commit
    echo "Analyzing last commit..."
    COMMIT_MSGS=$(git log -1 --format=%B)
fi

# Check if this is already a version bump commit (to prevent loops)
if echo "$COMMIT_MSGS" | grep -q "\[skip-ci\]"; then
    echo -e "${YELLOW}This is a CI version bump commit, skipping version bump${NC}"
    exit 0
fi

# Determine version bump type from commit messages
BUMP_TYPE="patch"  # Default to patch
if echo "$COMMIT_MSGS" | grep -qi "\[skip-version\]"; then
    BUMP_TYPE="none"
    echo -e "${YELLOW}Found [skip-version] tag, no version bump needed${NC}"
elif echo "$COMMIT_MSGS" | grep -qi "\[major\]"; then
    BUMP_TYPE="major"
    echo -e "${GREEN}Found [major] tag, will bump major version${NC}"
elif echo "$COMMIT_MSGS" | grep -qi "\[minor\]"; then
    BUMP_TYPE="minor"
    echo -e "${GREEN}Found [minor] tag, will bump minor version${NC}"
else
    echo -e "${GREEN}No version tag found, defaulting to patch bump${NC}"
fi

if [ "$BUMP_TYPE" = "none" ]; then
    echo "No version bump required"
    exit 0
fi

# Load changed packages from detect_changes output if available
if [ -f "changed_packages.json" ]; then
    # Parse JSON array
    CHANGED_PACKAGES=$(python3 -c "import json; packages = json.load(open('changed_packages.json')); print(' '.join(packages) if packages else '')")
    if [ -z "$CHANGED_PACKAGES" ]; then
        echo -e "${YELLOW}No packages have changed, skipping version bump${NC}"
        exit 0
    fi
    echo "Changed packages: $CHANGED_PACKAGES"
else
    # If no change detection, process all packages
    echo "No change detection file found, processing all packages..."
    CHANGED_PACKAGES=""
    for dir in */; do
        if [ -f "${dir}pyproject.toml" ]; then
            CHANGED_PACKAGES="$CHANGED_PACKAGES ${dir%/}"
        fi
    done
fi

# Track if any versions were bumped
VERSIONS_BUMPED=false
BUMPED_PACKAGES=""

# Process each changed package
for package in $CHANGED_PACKAGES; do
    if [ ! -f "$package/pyproject.toml" ]; then
        echo -e "${YELLOW}Skipping $package - no pyproject.toml found${NC}"
        continue
    fi
    
    echo ""
    echo "Processing package: $package"
    echo "-----------------------------------"
    
    # Get current version
    CURRENT_VERSION=$(python3 -c "
import tomllib
with open('$package/pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
    print(data['project']['version'])
" 2>/dev/null || echo "")
    
    if [ -z "$CURRENT_VERSION" ]; then
        echo -e "${RED}Could not read version from $package/pyproject.toml${NC}"
        continue
    fi
    
    echo "Current version: $CURRENT_VERSION"
    
    # Calculate new version
    NEW_VERSION=$(bump_version "$CURRENT_VERSION" "$BUMP_TYPE")
    
    if [ "$NEW_VERSION" = "$CURRENT_VERSION" ]; then
        echo "Version unchanged: $CURRENT_VERSION"
        continue
    fi
    
    echo -e "${GREEN}New version: $NEW_VERSION${NC}"
    
    # Update pyproject.toml
    python3 << EOF
import re

# Read the file
with open('$package/pyproject.toml', 'r') as f:
    content = f.read()

# Update version using regex to preserve formatting
content = re.sub(
    r'^version = ["\'"][^"\']*["\'"]',
    'version = "$NEW_VERSION"',
    content,
    flags=re.MULTILINE
)

# Write back
with open('$package/pyproject.toml', 'w') as f:
    f.write(content)

print('Version updated successfully')
EOF
    
    VERSIONS_BUMPED=true
    BUMPED_PACKAGES="$BUMPED_PACKAGES $package:$NEW_VERSION"
    
    # Create version artifact for CI
    if [ -n "$CI" ]; then
        echo "$NEW_VERSION" > "$package/.version"
        echo "Created version artifact: $package/.version"
    fi
done

# If versions were bumped and --commit-back is set, commit the changes
if [ "$VERSIONS_BUMPED" = true ] && [ "$COMMIT_BACK" = true ] && [ -n "$CI" ]; then
    echo ""
    echo "==================================="
    echo "Committing version changes back to repository..."
    echo "==================================="
    
    # Configure git for CI
    git config --global user.email "gitlab-ci@fenixflow.com"
    git config --global user.name "GitLab CI"
    
    # Add all modified pyproject.toml files
    for package in $CHANGED_PACKAGES; do
        if [ -f "$package/pyproject.toml" ]; then
            git add "$package/pyproject.toml"
        fi
    done
    
    # Check if there are changes to commit
    if git diff --cached --quiet; then
        echo "No version changes to commit"
    else
        # Create commit message
        COMMIT_MSG="[skip-ci] Bump package versions"
        for info in $BUMPED_PACKAGES; do
            IFS=':' read -r pkg ver <<< "$info"
            COMMIT_MSG="$COMMIT_MSG
  - $pkg -> $ver"
        done
        
        # Commit changes
        git commit -m "$COMMIT_MSG"
        
        # Push back to the branch
        if [ -n "$CI_COMMIT_REF_NAME" ]; then
            echo "Pushing version changes to $CI_COMMIT_REF_NAME..."
            git push "https://gitlab-ci-token:${CI_JOB_TOKEN}@${CI_SERVER_HOST}/${CI_PROJECT_PATH}.git" HEAD:${CI_COMMIT_REF_NAME}
            echo -e "${GREEN}Version changes committed and pushed successfully${NC}"
        else
            echo -e "${YELLOW}Not in CI environment, skipping push${NC}"
        fi
    fi
elif [ "$VERSIONS_BUMPED" = true ]; then
    echo ""
    echo -e "${GREEN}Versions bumped locally. Changes not committed.${NC}"
    echo "To commit manually, run: git add */pyproject.toml && git commit -m '[skip-ci] Bump versions'"
else
    echo ""
    echo "No versions were bumped"
fi

echo ""
echo "==================================="
echo "Version bump complete"
echo "===================================="