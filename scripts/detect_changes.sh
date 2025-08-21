#!/bin/bash
# Detect which packages have changed since the last pipeline run
# Also checks for version conflicts with published packages
# Output: JSON object with "changed" array and "version_conflicts" array

# Don't exit on error - we want to handle errors gracefully
set +e

# Get the list of all packages (directories with pyproject.toml)
PACKAGES=()
for dir in */; do
    if [ -f "${dir}pyproject.toml" ]; then
        PACKAGES+=("${dir%/}")
    fi
done

# Ensure we're in a Git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "Error: Not in a Git repository" >&2
    echo '{"changed": [], "version_conflicts": []}'
    exit 0
fi

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
    # No comparison point found, check if this is the first commit
    if ! git rev-parse HEAD~1 >/dev/null 2>&1; then
        echo "First commit or shallow clone detected, marking all packages as changed" >&2
        CHANGED_PACKAGES=("${PACKAGES[@]}")
    else
        echo "No comparison commit found, checking files changed in current commit" >&2
        CHANGED_PACKAGES=()
    
    # Check what changed in the current commit
    for package in "${PACKAGES[@]}"; do
            if git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null | grep -q "^$package/"; then
                echo "Changes detected in $package" >&2
                CHANGED_PACKAGES+=("$package")
            else
                echo "No changes in $package" >&2
            fi
        done
    fi
else
    CHANGED_PACKAGES=()
    
    # Check each package for changes
    for package in "${PACKAGES[@]}"; do
        # Check if any files in the package directory have changed
        if git diff --quiet "$COMPARE_SHA" HEAD -- "$package/" 2>/dev/null; then
            echo "No changes in $package" >&2
        else
            echo "Changes detected in $package" >&2
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
            if ! git diff --quiet "$COMPARE_SHA" HEAD -- "$file" 2>/dev/null; then
                echo "Shared file changed: $file" >&2
                SHARED_CHANGED=true
                break
            fi
        fi
    done
fi

# If shared files changed and we're in a merge request, rebuild all packages
if [ "$SHARED_CHANGED" = true ] && [ "$CI_MERGE_REQUEST_ID" ]; then
    echo "Shared files changed in merge request, marking all packages for rebuild" >&2
    CHANGED_PACKAGES=("${PACKAGES[@]}")
fi

# Check for version conflicts
VERSION_CONFLICTS=()
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "" >&2
echo "Checking for version conflicts..." >&2
for package in "${CHANGED_PACKAGES[@]}"; do
    # Get current version from pyproject.toml
    if [ -f "$package/pyproject.toml" ]; then
        CURRENT_VERSION=$(python3 -c "
import tomllib
with open('$package/pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
    print(data['project']['version'])
" 2>/dev/null || echo "")
        
        if [ -n "$CURRENT_VERSION" ]; then
            # Check if this version already exists in registry
            if "${SCRIPT_DIR}/check_version_exists.sh" "$package" "$CURRENT_VERSION" >/dev/null 2>&1; then
                echo "Version conflict detected: $package v$CURRENT_VERSION already exists" >&2
                VERSION_CONFLICTS+=("$package")
            fi
        fi
    fi
done

# Output as JSON object with both arrays
printf '{\n'
printf '  "changed": '

# Output changed packages array
if [ ${#CHANGED_PACKAGES[@]} -eq 0 ]; then
    printf '[]'
else
    printf '['
    first=true
    for package in "${CHANGED_PACKAGES[@]}"; do
        if [ "$first" = true ]; then
            first=false
        else
            printf ', '
        fi
        printf '"%s"' "$package"
    done
    printf ']'
fi

printf ',\n  "version_conflicts": '

# Output version conflicts array
if [ ${#VERSION_CONFLICTS[@]} -eq 0 ]; then
    printf '[]'
else
    printf '['
    first=true
    for package in "${VERSION_CONFLICTS[@]}"; do
        if [ "$first" = true ]; then
            first=false
        else
            printf ', '
        fi
        printf '"%s"' "$package"
    done
    printf ']'
fi

printf '\n}\n'