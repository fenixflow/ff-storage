# Manual Release Pipeline Guide

## Overview

The manual release pipeline allows you to selectively release packages with automatic version bumping. This pipeline is completely standalone and can only be triggered manually from the GitLab UI.

## Features

- **Selective Package Release**: Choose which packages to release
- **Version Bump Control**: Select patch/minor/major bump for each package
- **Registry-Based Versioning**: Reads current version from GitLab Package Registry (not local files)
- **Atomic Updates**: Single commit at the end prevents race conditions
- **Automatic Tagging**: Creates git tags for each released package

## How to Use

### 1. Navigate to Pipeline Page

Go to **CI/CD > Pipelines** in your GitLab project and click **"Run pipeline"**.

### 2. Select the Manual Release Pipeline

- **Branch**: Select `main` (or the branch with `.gitlab-ci-manual-release.yml`)
- **Pipeline**: Choose `.gitlab-ci-manual-release.yml` from the dropdown

### 3. Configure Package Releases

You'll see dropdown inputs for each package:

- `ff_storage_bump`: Version bump for ff-storage
- `ff_logger_bump`: Version bump for ff-logger
- `ff_cli_bump`: Version bump for ff-cli
- `ff_parsers_bump`: Version bump for ff-parsers

For each package, select:
- **none**: Skip this package (default)
- **patch**: Bump patch version (0.1.2 → 0.1.3)
- **minor**: Bump minor version (0.1.2 → 0.2.0)
- **major**: Bump major version (0.1.2 → 1.0.0)

### 4. Run the Pipeline

Click **"Run pipeline"** to start the release process.

## Pipeline Workflow

The pipeline executes in these stages:

### Stage 1: Prepare
- Queries GitLab Package Registry for current versions
- Calculates new versions based on your selections
- Updates local pyproject.toml files (not committed yet)

### Stage 2: Build
- Builds only the selected packages
- Creates Python wheels with new versions

### Stage 3: Publish
- Publishes packages to GitLab Package Registry
- Each package is published independently

### Stage 4: Finalize
- Commits all pyproject.toml updates in a single commit
- Commit message includes `[skip ci]` to prevent triggering other pipelines
- Creates git tags for each released package (e.g., `ff-storage-v0.1.4`)
- Pushes commit and tags to main branch

## Version Numbering

The pipeline follows [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.0.0): Breaking changes
- **MINOR** (0.1.0): New features, backwards compatible
- **PATCH** (0.0.1): Bug fixes, backwards compatible

## Important Notes

1. **Registry as Source of Truth**: The pipeline reads current versions from the registry, not from git. This ensures we're always bumping from the last published version.

2. **First Release**: If a package has never been published, it starts from version `0.0.0`.

3. **Atomic Commits**: All version updates are committed together at the end to prevent race conditions.

4. **Manual Only**: This pipeline cannot be triggered by commits or merge requests. It's purely manual.

5. **Skip CI**: The version update commit includes `[skip ci]` to prevent triggering the regular CI pipeline.

## Example Scenarios

### Releasing a Bug Fix

If you've fixed a bug in `ff-storage`:
1. Set `ff_storage_bump` to `patch`
2. Leave others as `none`
3. Run pipeline

Result: `ff-storage` goes from `0.1.3` to `0.1.4`

### Major Release for Multiple Packages

For a coordinated major release:
1. Set `ff_storage_bump` to `major`
2. Set `ff_logger_bump` to `major`
3. Set `ff_cli_bump` to `major`
4. Leave `ff_parsers_bump` as `none`
5. Run pipeline

Result: 
- `ff-storage`: `0.1.3` → `1.0.0`
- `ff-logger`: `0.1.2` → `1.0.0`
- `ff-cli`: `0.1.2` → `1.0.0`
- `ff-parsers`: unchanged

## Troubleshooting

### Pipeline Fails at Prepare Stage

- Check that the GitLab CI token has access to the Package Registry API
- Verify the package names are correct

### Pipeline Fails at Publish Stage

- Ensure no duplicate version exists in the registry
- Check that the CI token has write access to the Package Registry

### Pipeline Fails at Finalize Stage

- Verify the CI token has write access to the repository
- Check that the main branch is not protected against CI pushes

## Security Considerations

- The pipeline uses `CI_JOB_TOKEN` for authentication
- Commits are made as "GitLab CI" user
- Tags are signed with the CI identity
- The `[skip ci]` tag prevents recursive pipeline triggers