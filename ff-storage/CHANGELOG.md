# Changelog

All notable changes to ff-storage will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2024-12-16

### Added
- Initial public release
- MIT License for open source distribution
- Comprehensive README with usage examples
- PyPI package metadata and classifiers

### Changed
- Updated package metadata for public distribution
- Changed from proprietary to MIT license

## [0.1.4] - 2024-09-15

### Fixed
- Connection pooling improvements for PostgreSQL
- Thread safety in MySQL connection handling

## [0.1.3] - 2024-09-10

### Added
- MySQL connection pooling support
- Query builder utilities for complex SQL construction

## [0.1.2] - 2024-09-01

### Added
- S3 object storage implementation with streaming support
- Multipart upload for large files
- S3-compatible services support (MinIO, etc.)

### Fixed
- Memory efficiency in streaming operations
- Path traversal protection in local storage

## [0.1.1] - 2024-08-25

### Added
- Local filesystem object storage with atomic writes
- Metadata sidecar files for object properties
- Async/await support throughout object storage

### Fixed
- Race conditions in concurrent file writes

## [0.1.0] - 2024-08-20

### Added
- Initial release with core functionality
- PostgreSQL database support with connection pooling
- MySQL database support
- SQL migration management system
- Abstract base classes for database operations
- Dataclass models with UUID and timestamp support

---

Maintained by **Ben Moag** ([Fenixflow](https://fenixflow.com))

[Unreleased]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.2.0...HEAD
[0.2.0]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.4...ff-storage-v0.2.0
[0.1.4]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.3...ff-storage-v0.1.4
[0.1.3]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.2...ff-storage-v0.1.3
[0.1.2]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.1...ff-storage-v0.1.2
[0.1.1]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-storage-v0.1.0...ff-storage-v0.1.1
[0.1.0]: https://gitlab.com/fenixflow/fenix-packages/-/releases/ff-storage-v0.1.0