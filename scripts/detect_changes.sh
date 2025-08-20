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

# If no previous successful pipeline, consider all packages changed
if [ -z "$CI_COMMIT_BEFORE_SHA" ] || [ "$CI_COMMIT_BEFORE_SHA" = "0000000000000000000000000000000000000000" ]; then
    # First pipeline run or no previous commit
    echo "No previous commit found, checking all packages"
    CHANGED_PACKAGES=("${PACKAGES[@]}")
else
    CHANGED_PACKAGES=()
    
    # Check each package for changes
    for package in "${PACKAGES[@]}"; do
        # Check if any files in the package directory have changed
        if git diff --quiet "$CI_COMMIT_BEFORE_SHA" HEAD -- "$package/"; then
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

for file in "${SHARED_FILES[@]}"; do
    if [ -e "$file" ]; then
        if ! git diff --quiet "$CI_COMMIT_BEFORE_SHA" HEAD -- "$file"; then
            echo "Shared file changed: $file"
            SHARED_CHANGED=true
            break
        fi
    fi
done

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