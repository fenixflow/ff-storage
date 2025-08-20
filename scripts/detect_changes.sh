#!/bin/bash
# Detect which packages have changed since the last pipeline run
# Output: JSON array of changed package names

set -e

# Get the list of all packages (directories with pyproject.toml)
PACKAGES=()
for dir in */; do
    if [ -f "${dir}pyproject.toml" ]; then
        PACKAGES+=("${dir%/}")
    fi
done

# Determine the comparison commit
COMPARE_SHA=""
if [ -n "$CI_COMMIT_BEFORE_SHA" ] && [ "$CI_COMMIT_BEFORE_SHA" != "0000000000000000000000000000000000000000" ]; then
    COMPARE_SHA="$CI_COMMIT_BEFORE_SHA"
elif [ -n "$CI_MERGE_REQUEST_DIFF_BASE_SHA" ]; then
    # In merge requests, compare against the base
    COMPARE_SHA="$CI_MERGE_REQUEST_DIFF_BASE_SHA"
else
    # Try to get the previous commit on the same branch
    COMPARE_SHA=$(git rev-parse HEAD~1 2>/dev/null || echo "")
fi

if [ -z "$COMPARE_SHA" ]; then
    # No comparison point found, only check changed packages based on current commit
    echo "No comparison commit found, checking files changed in current commit"
    CHANGED_PACKAGES=()
    
    # Check what changed in the current commit
    for package in "${PACKAGES[@]}"; do
        if git diff-tree --no-commit-id --name-only -r HEAD | grep -q "^$package/"; then
            echo "Changes detected in $package"
            CHANGED_PACKAGES+=("$package")
        else
            echo "No changes in $package"
        fi
    done
else
    CHANGED_PACKAGES=()
    
    # Check each package for changes
    for package in "${PACKAGES[@]}"; do
        # Check if any files in the package directory have changed
        if git diff --quiet "$COMPARE_SHA" HEAD -- "$package/"; then
            echo "No changes in $package"
        else
            echo "Changes detected in $package"
            CHANGED_PACKAGES+=("$package")
        fi
    done
fi

# Also check for changes in shared scripts that might affect all packages
SHARED_FILES=(.gitlab-ci.yml scripts/)
SHARED_CHANGED=false

if [ -n "$COMPARE_SHA" ]; then
    for file in "${SHARED_FILES[@]}"; do
        if [ -e "$file" ]; then
            if ! git diff --quiet "$COMPARE_SHA" HEAD -- "$file"; then
                echo "Shared file changed: $file"
                SHARED_CHANGED=true
                break
            fi
        fi
    done
fi

# If shared files changed and we're in a merge request, rebuild all packages
if [ "$SHARED_CHANGED" = true ] && [ "$CI_MERGE_REQUEST_ID" ]; then
    echo "Shared files changed in merge request, marking all packages for rebuild"
    CHANGED_PACKAGES=("${PACKAGES[@]}")
fi

# Output as JSON array
if [ ${#CHANGED_PACKAGES[@]} -eq 0 ]; then
    echo "[]"
else
    printf '['
    first=true
    for package in "${CHANGED_PACKAGES[@]}"; do
        if [ "$first" = true ]; then
            first=false
        else
            printf ','
        fi
        printf '"%s"' "$package"
    done
    printf ']\n'
fi