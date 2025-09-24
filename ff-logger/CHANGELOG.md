# Changelog

All notable changes to ff-logger will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2024-01-23

### Added
- **Flexible log levels**: Loggers now accept both string and integer log levels
  - Strings: `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`, `"CRITICAL"`
  - Case-insensitive: `"info"` works the same as `"INFO"`
  - Includes `"WARN"` as an alias for `"WARNING"`
  - Backward compatible with integer levels (`logging.INFO`, `20`, etc.)
- **Context validation in bind()**: The `bind()` method now validates:
  - Reserved fields are rejected with helpful error messages
  - Values must be JSON-serializable (str, int, float, bool, list, dict)

### Changed
- **Simplified bind() method**: Now modifies the logger instance in place instead of creating a new one
  - Returns `self` for method chaining
  - More intuitive behavior - adds context to existing logger
  - Much cleaner implementation with less code duplication
- **Removed redundant handler.setLevel() calls**: Handlers now inherit the logger's level automatically
  - Cleaner separation of concerns
  - Level is managed once in the base class

### Fixed
- Type hints now use modern Python syntax (`int | str` instead of `Union[int, str]`)
- Eliminated code duplication across logger implementations

### Developer Experience
- Configuration-friendly: Can now use strings from config files/environment variables
- No need to import `logging` module for basic usage
- Better error messages when using reserved fields or invalid values

## [0.2.3] - 2024-01-20

### Changed
- Updated package dependencies and build configuration

## [0.2.0] - 2024-12-11

### Added
- Initial public release
- MIT License for open source distribution
- Comprehensive README with usage examples
- PyPI package metadata and classifiers

### Changed
- Updated package metadata for public distribution
- Changed from proprietary to MIT license

## [0.1.1] - 2024-08-22

### Added
- Database logger implementation with ff-storage integration
- File logger with rotation support (size and time-based)
- Improved context binding with `bind()` method
- Support for reserved field name handling (auto-prefixing with `x_`)

### Fixed
- Thread safety improvements for concurrent logging
- Memory efficiency optimizations in context handling

## [0.1.0] - 2024-08-20

### Added
- Initial release with core functionality
- ConsoleLogger with colored output support
- JSONLogger for structured logging
- NullLogger for testing and disabled logging
- Instance-based architecture with zero dependencies
- Context binding for permanent fields
- Built on Python's standard logging module

---

Maintained by **Ben Moag** ([Fenixflow](https://fenixflow.com))

[Unreleased]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-logger-v0.2.0...HEAD
[0.2.0]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-logger-v0.1.2...ff-logger-v0.2.0
[0.1.2]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-logger-v0.1.1...ff-logger-v0.1.2
[0.1.1]: https://gitlab.com/fenixflow/fenix-packages/-/compare/ff-logger-v0.1.0...ff-logger-v0.1.1
[0.1.0]: https://gitlab.com/fenixflow/fenix-packages/-/releases/ff-logger-v0.1.0