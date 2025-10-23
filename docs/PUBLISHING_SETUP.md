# Publishing Setup Guide

This guide explains how to set up authentication for publishing packages to GitHub and PyPI.

## Prerequisites

- Git installed and configured
- Python 3.10+ with `build` and `twine` packages
- Access to GitHub repository (github.com/fenixflow)
- PyPI account with appropriate permissions

## GitHub Authentication

### Option 1: SSH Key (Recommended)

1. **Check if you have an SSH key:**
   ```bash
   ls -la ~/.ssh/id_*.pub
   ```

2. **Generate SSH key if needed:**
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com"
   ```

3. **Add SSH key to ssh-agent:**
   ```bash
   eval "$(ssh-agent -s)"
   ssh-add ~/.ssh/id_ed25519
   ```

4. **Add SSH key to GitHub:**
   - Copy your public key: `cat ~/.ssh/id_ed25519.pub`
   - Go to: https://github.com/settings/keys
   - Click "New SSH key"
   - Paste your key and save

5. **Test connection:**
   ```bash
   ssh -T git@github.com
   # Should see: "Hi username! You've successfully authenticated..."
   ```

### Option 2: Personal Access Token

1. **Generate a token:**
   - Go to: https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Select scopes: `repo` (all sub-scopes)
   - Copy the token (you won't see it again!)

2. **Configure Git to use the token:**
   ```bash
   git config --global credential.helper store
   ```

3. **Use HTTPS URLs with token:**
   ```bash
   git remote add github-storage https://YOUR_TOKEN@github.com/fenixflow/ff-storage.git
   ```

## PyPI Authentication

### Option 1: API Token (Recommended)

1. **Generate PyPI API token:**
   - Go to: https://pypi.org/manage/account/token/
   - Click "Add API token"
   - Name: `fenix-packages-upload`
   - Scope: Choose "Entire account" or specific projects
   - Copy the token (starts with `pypi-`)

2. **Set environment variable:**

   **For bash/zsh (add to ~/.bashrc or ~/.zshrc):**
   ```bash
   export PYPI_TOKEN="pypi-YOUR_TOKEN_HERE"
   ```

   **For current session only:**
   ```bash
   export PYPI_TOKEN="pypi-YOUR_TOKEN_HERE"
   ```

3. **Verify it's set:**
   ```bash
   echo $PYPI_TOKEN
   # Should show: pypi-...
   ```

### Option 2: Configure .pypirc

1. **Create or edit ~/.pypirc:**
   ```bash
   nano ~/.pypirc
   ```

2. **Add configuration:**
   ```ini
   [distutils]
   index-servers =
       pypi
       testpypi

   [pypi]
   username = __token__
   password = pypi-YOUR_TOKEN_HERE

   [testpypi]
   repository = https://test.pypi.org/legacy/
   username = __token__
   password = pypi-YOUR_TESTPYPI_TOKEN_HERE
   ```

3. **Secure the file:**
   ```bash
   chmod 600 ~/.pypirc
   ```

## TestPyPI (for testing before production)

1. **Create TestPyPI account:** https://test.pypi.org/account/register/

2. **Generate TestPyPI token:**
   - Go to: https://test.pypi.org/manage/account/token/
   - Generate token similar to PyPI

3. **Set environment variable:**
   ```bash
   export TEST_PYPI_TOKEN="pypi-YOUR_TESTPYPI_TOKEN_HERE"
   ```

## Install Required Python Packages

```bash
# Install build and publishing tools
pip install build twine

# Or with uv
uv pip install build twine
```

## Verify Setup

### Test GitHub Access

```bash
# Should work without password prompt
git ls-remote git@github.com:fenixflow/ff-storage.git
```

### Test PyPI Authentication

```bash
# Check credentials without uploading
python -m twine check dist/* --verbose
```

## Quick Reference

### Environment Variables

Add these to your shell profile (~/.bashrc, ~/.zshrc, etc.):

```bash
# PyPI Tokens
export PYPI_TOKEN="pypi-YOUR_PRODUCTION_TOKEN"
export TEST_PYPI_TOKEN="pypi-YOUR_TEST_TOKEN"
```

### Using the Packages Plugin

First, install the packages plugin:
```bash
uv pip install -e ./packages_plugin
```

Then use the Fenix CLI commands:

```bash
# Check publishing configuration
fenix ff-packages check

# List all packages with current versions
fenix ff-packages list

# Test with dry-run first
fenix ff-packages pypi ff-storage --dry-run

# Publish to TestPyPI first
fenix ff-packages pypi ff-storage --test

# Then publish to production PyPI (interactive prompts)
fenix ff-packages pypi ff-storage

# Create GitHub release
fenix ff-packages github ff-storage

# Or sync to GitLab Package Registry
fenix ff-packages sync ff-storage
```

## Troubleshooting

### "Permission denied (publickey)" for GitHub

- Your SSH key is not added to GitHub
- Run: `ssh-add ~/.ssh/id_ed25519` and try again

### "Invalid or non-existent authentication" for PyPI

- Token is incorrect or expired
- Check: `echo $PYPI_TOKEN` shows the correct token
- Regenerate token if needed

### "Package version already exists" on PyPI

- You cannot overwrite published versions
- Bump version in `pyproject.toml` first
- Or use `--test` to publish to TestPyPI instead

### Script says "PYPI_TOKEN not set"

- Token not in environment variables
- Run: `export PYPI_TOKEN="pypi-..."`
- Or add to `~/.pypirc` configuration file

## Security Best Practices

1. **Never commit tokens to git:**
   - Add `.env` to `.gitignore`
   - Use environment variables or secure vaults

2. **Limit token scope:**
   - Use project-specific tokens when possible
   - Don't use account-wide tokens unless necessary

3. **Rotate tokens regularly:**
   - GitHub: Every 6-12 months
   - PyPI: Every 6-12 months

4. **Secure .pypirc:**
   - Always run: `chmod 600 ~/.pypirc`
   - Never share or commit this file

## Next Steps

After setup is complete:

1. Check configuration: `fenix ff-packages check`
2. Test with dry-run: `fenix ff-packages pypi ff-storage --dry-run`
3. Test on TestPyPI: `fenix ff-packages pypi ff-storage --test`
4. Publish to production: `fenix ff-packages pypi ff-storage`
5. Create GitHub release: `fenix ff-packages github ff-storage`

---

**Maintained by Ben Moag** ([Fenixflow](https://fenixflow.com))