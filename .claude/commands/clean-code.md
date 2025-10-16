---
allowed-tools: Bash(isort:*), Bash(ruff:*)
description: Clean and lint the entire codebase
---

Clean the codebase by running code formatters and linters:

1. Run isort to sort imports: `uvx isort .`
2. Run ruff check to check for issues: `uvx ruff check . --fix`
3. Run ruff format to format code: `uvx ruff format .`

Please run these commands in sequence and report the results. Fix any issues that are auto-fixable and then ask if you should fix the rest.
