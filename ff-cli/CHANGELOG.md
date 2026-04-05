# Changelog

All notable changes to ff-cli will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-04-05

### Added

- **[SERVICES]** 9 new service definitions (13 total):
  - Infrastructure: `mongo`, `mongo-express`, `azurite`
  - Applications: `agents`, `chat`, `flow-api`, `flow-mcp`, `bridge`, `frontend`
  - All with healthchecks, OrbStack DNS, and `${VAR:-default}` environment expansion

- **[BRANDING]** NIAS brand configuration
  - `nias` entry point for contract-specific CLI branding
  - Separate Docker network (`nias-network`), container prefix, OrbStack domain suffix
  - Same plugins and commands, different deployment context

- **[COMMANDS]** New command groups ported from ix-cli:
  - `fenix dev lint|format|test|ports` — developer utilities (ruff, pytest, port scanning)
  - `fenix setup` — new joiner bootstrapping with software checks and `--fix` flag
  - `fenix builds list|build|push` — Docker image management with buildx multi-platform support
  - `fenix tf init|plan|apply|destroy` — Terraform operations wrapper

- **[SERVICES]** Enhanced service lifecycle commands:
  - `fenix services prune` — remove orphaned containers
  - `fenix services reset` — hard reset with `--nuke` for volume cleanup
  - `fenix services remove` — delete user service definitions

- **[DOCTOR]** Expanded to 21-point comprehensive diagnostic:
  - Python, uv, git, Docker, OrbStack checks
  - Config validation, network existence, port conflicts
  - Plugin integrity and orphan detection
  - `--fix` flag for auto-remediation
  - `--json` flag for structured output

### Changed

- **[SERVICES]** `image` field now optional when `build` config is present; auto-generates `{brand}/{name}:latest`
- **[SERVICES]** Fixed postgres default port from 5435 to 5432

## [0.4.1] - 2026-01-06

### Initial tracked release
- Plugin architecture with entry point discovery
- Service management (up, down, restart, ps, logs, exec, build)
- Dynamic branding system
- 4 default services: postgres, redis, rabbitmq, minio
