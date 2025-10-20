#!/bin/bash
# Mirror a package to its GitHub repository
# Usage: ./mirror_to_github.sh <package-name> [--dry-run]

set -e

PACKAGE_NAME="$1"
DRY_RUN=false

# Check for dry-run flag
if [[ "$2" == "--dry-run" || "$1" == "--dry-run" ]]; then
    DRY_RUN=true
    if [[ "$1" == "--dry-run" ]]; then
        PACKAGE_NAME="$2"
    fi
fi

# List of supported packages (easily extensible)
SUPPORTED_PACKAGES=("ff-storage" "ff-logger")

# Usage
usage() {
    echo "Usage: $0 <package-name> [--dry-run]"
    echo ""
    echo "Supported packages:"
    for pkg in "${SUPPORTED_PACKAGES[@]}"; do
        echo "  - $pkg"
    done
    echo ""
    echo "Options:"
    echo "  --dry-run    Show what would be done without actually doing it"
    echo ""
    echo "Examples:"
    echo "  $0 ff-storage"
    echo "  $0 ff-logger --dry-run"
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

# Determine remote name and GitHub URL
REMOTE_NAME="github-${PACKAGE_NAME#ff-}"  # e.g., github-storage
GITHUB_URL="git@github.com:fenixflow/${PACKAGE_NAME}.git"

echo "============================================="
echo "GitHub Mirror Script"
echo "============================================="
echo "Package:      $PACKAGE_NAME"
echo "GitHub repo:  $GITHUB_URL"
echo "Remote name:  $REMOTE_NAME"
echo "Dry run:      $DRY_RUN"
echo "============================================="
echo ""

# Check if remote already exists
if git remote get-url "$REMOTE_NAME" >/dev/null 2>&1; then
    EXISTING_URL=$(git remote get-url "$REMOTE_NAME")
    if [ "$EXISTING_URL" != "$GITHUB_URL" ]; then
        echo "⚠️  Remote '$REMOTE_NAME' exists but points to different URL:"
        echo "   Current: $EXISTING_URL"
        echo "   Expected: $GITHUB_URL"
        read -p "Update remote URL? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if [ "$DRY_RUN" = false ]; then
                git remote set-url "$REMOTE_NAME" "$GITHUB_URL"
                echo "✓ Updated remote URL"
            else
                echo "[DRY RUN] Would update remote URL"
            fi
        else
            echo "Aborting."
            exit 1
        fi
    else
        echo "✓ Remote '$REMOTE_NAME' already configured correctly"
    fi
else
    echo "Adding remote '$REMOTE_NAME'..."
    if [ "$DRY_RUN" = false ]; then
        git remote add "$REMOTE_NAME" "$GITHUB_URL"
        echo "✓ Added remote '$REMOTE_NAME'"
    else
        echo "[DRY RUN] Would add remote: $REMOTE_NAME → $GITHUB_URL"
    fi
fi

echo ""
echo "Fetching current branch..."
CURRENT_BRANCH=$(git branch --show-current)
echo "Current branch: $CURRENT_BRANCH"

echo ""
echo "Checking for uncommitted changes..."
if ! git diff-index --quiet HEAD --; then
    echo "⚠️  You have uncommitted changes!"
    git status --short
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborting."
        exit 1
    fi
fi

echo ""
echo "Preparing to push to GitHub..."
echo "This will push:"
echo "  - Current branch: $CURRENT_BRANCH"
echo "  - All tags matching: ${PACKAGE_NAME}-v*"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would execute:"
    echo "  git push $REMOTE_NAME $CURRENT_BRANCH"
    echo "  git push $REMOTE_NAME --tags --force"
    echo ""
    echo "[DRY RUN] No changes made"
    exit 0
fi

read -p "Push to $GITHUB_URL? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborting."
    exit 1
fi

echo ""
echo "Pushing branch '$CURRENT_BRANCH' to GitHub..."
git push "$REMOTE_NAME" "$CURRENT_BRANCH"
echo "✓ Pushed branch"

echo ""
echo "Pushing tags to GitHub..."
# Push all tags, but specifically those for this package
git push "$REMOTE_NAME" --tags
echo "✓ Pushed tags"

echo ""
echo "============================================="
echo "✓ Successfully mirrored $PACKAGE_NAME to GitHub"
echo "============================================="
echo ""
echo "GitHub repository: https://github.com/fenixflow/${PACKAGE_NAME}"
echo ""
echo "Note: This pushed the entire monorepo. If you want individual"
echo "package repos with separate history, consider using git-subtree"
echo "or git-filter-repo for more advanced splitting."