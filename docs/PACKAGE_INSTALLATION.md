# Installing Fenix Packages from GitLab Registry

This guide explains how to install Fenix packages from the private GitLab Package Registry using `uv`.

## Prerequisites

1. Install `uv` package manager:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Create a GitLab access token with `read_api` scope

## Creating an Access Token

### Option 1: Personal Access Token (for developers)

1. Go to GitLab → User Settings → Access Tokens
2. Create a new token with:
   - Name: `fenix-packages-read`
   - Expiration: Set as needed
   - Scopes: Select `read_api`
3. Save the token securely

### Option 2: Deploy Token (for CI/CD and production)

1. Go to Project → Settings → Repository → Deploy Tokens
2. Create a new token with:
   - Name: `fenix-packages-deploy`
   - Expiration: Set as needed
   - Scopes: Select `read_package_registry`
3. Save the username and token

## Installation Methods

### Method 1: Direct Installation with uv

```bash
# Replace <username> and <token> with your credentials
uv pip install ff-storage \
  --index-url https://<username>:<token>@gitlab.com/api/v4/projects/<project_id>/packages/pypi/simple
```

### Method 2: Using Environment Variables

Set up environment variables to avoid exposing tokens:

```bash
# Add to your .env or shell profile
export GITLAB_TOKEN_NAME="your-token-name"
export GITLAB_TOKEN="your-token-value"
export FENIX_PROJECT_ID="your-project-id"

# Install using environment variables
uv pip install ff-storage \
  --index-url https://${GITLAB_TOKEN_NAME}:${GITLAB_TOKEN}@gitlab.com/api/v4/projects/${FENIX_PROJECT_ID}/packages/pypi/simple
```

### Method 3: Configure in pyproject.toml

Add the registry to your project's `pyproject.toml`:

```toml
[project]
dependencies = [
    "ff-storage>=0.1.0",
]

[[tool.uv.index]]
name = "gitlab-fenix"
url = "https://gitlab.com/api/v4/projects/<project_id>/packages/pypi/simple"

# For authentication, use environment variables or .netrc file
```

Then set authentication via `.netrc` file:

```bash
# Create/edit ~/.netrc
machine gitlab.com
login <token_name>
password <token>
```

Run installation:
```bash
uv sync
```

### Method 4: Using uv with a Configuration File

Create a `uv.toml` configuration file:

```toml
[index]
extra-index-url = ["https://<token_name>:<token>@gitlab.com/api/v4/projects/<project_id>/packages/pypi/simple"]
```

Then install normally:
```bash
uv pip install ff-storage
```

## Available Packages

| Package | Description | Installation |
|---------|-------------|--------------|
| `ff-storage` | Database and file storage operations | `uv pip install ff-storage` |

## Verifying Installation

After installation, verify the package:

```python
import ff_storage
print(ff_storage.__version__)

# Test imports
from ff_storage import Postgres, PostgresPool, MySQL, MySQLPool
print("Successfully imported ff-storage components")
```

## CI/CD Integration

For GitLab CI/CD pipelines, use the built-in `CI_JOB_TOKEN`:

```yaml
# .gitlab-ci.yml
install-dependencies:
  script:
    - uv pip install ff-storage --index-url https://gitlab-ci-token:${CI_JOB_TOKEN}@gitlab.com/api/v4/projects/${CI_PROJECT_ID}/packages/pypi/simple
```

## Docker Integration

For Docker builds, pass the token as a build argument:

```dockerfile
# Dockerfile
ARG GITLAB_TOKEN
ARG GITLAB_TOKEN_NAME

RUN uv pip install ff-storage \
  --index-url https://${GITLAB_TOKEN_NAME}:${GITLAB_TOKEN}@gitlab.com/api/v4/projects/<project_id>/packages/pypi/simple
```

Build with:
```bash
docker build --build-arg GITLAB_TOKEN=$GITLAB_TOKEN --build-arg GITLAB_TOKEN_NAME=$GITLAB_TOKEN_NAME .
```

## Troubleshooting

### Authentication Errors

If you get a 401 or 403 error:
1. Verify your token has `read_api` or `read_package_registry` scope
2. Check the token hasn't expired
3. Ensure you're using the correct project ID

### Package Not Found

If the package isn't found:
1. Verify the package has been published to the registry
2. Check you're using the correct package name (e.g., `ff-storage` not `ff_storage`)
3. Ensure the registry URL is correct

### SSL/TLS Issues

If you encounter SSL errors in corporate environments:
```bash
# Temporarily disable SSL verification (not recommended for production)
export UV_NATIVE_TLS=false
uv pip install ff-storage --index-url ...
```

## Security Best Practices

1. **Never commit tokens to version control**
2. Use environment variables or secure secret management
3. Rotate tokens regularly
4. Use deploy tokens for production systems
5. Limit token scopes to minimum required permissions
6. Use `.gitignore` to exclude `.netrc` and `.env` files

## Getting Your Project ID

Find your project ID in GitLab:
1. Go to your project page
2. Look for "Project ID" under the project name
3. Or find it in Settings → General

## Support

For issues or questions:
- Check the [fenix-packages repository](https://gitlab.com/fenixflow/fenix-packages)
- Contact the Fenixflow development team