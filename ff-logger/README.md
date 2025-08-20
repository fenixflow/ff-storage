# ff-logger

A structured logging package for Fenixflow applications using structlog.

## Features

- **Scoped Loggers**: Isolated logger instances with their own context
- **Multiple Backends**: Console, JSON, Database, and Null loggers
- **Zero-Cost Null Logger**: No performance overhead when logging is disabled
- **Structured Logging**: Key-value pairs for better log analysis
- **Flexible Configuration**: Environment variables, config files, or code
- **Thread-Safe**: Safe for concurrent use
- **Type-Safe**: Full type hints for better IDE support

## Installation

```bash
# Basic installation
uv pip install ff-logger

# With database support
uv pip install "ff-logger[database]"

# For development
uv pip install "ff-logger[dev]"
```

## Quick Start

### Basic Usage

```python
from ff_logger import ConsoleLogger

# Create a scoped logger
logger = ConsoleLogger("my_service")

# Log with structured data
logger.info("user_login", user_id=123, ip="192.168.1.1")
logger.error("database_error", error="Connection timeout", retry_count=3)

# Bind context for all subsequent logs
logger = logger.bind(request_id="abc-123", environment="production")
logger.info("processing_request")  # Will include request_id and environment
```

### Different Logger Types

```python
# Console logger for development
from ff_logger import ConsoleLogger
logger = ConsoleLogger("dev")

# JSON logger for production
from ff_logger import JSONLogger
logger = JSONLogger("prod")

# Database logger for audit trails
from ff_logger import DatabaseLogger
logger = DatabaseLogger("audit", connection=db_conn)

# Null logger to disable logging (zero-cost)
from ff_logger import NullLogger
logger = NullLogger("disabled")
```

### Configuration

```python
from ff_logger import configure_logging

# Configure globally
configure_logging(
    level="INFO",
    format="json",
    add_timestamp=True,
    add_hostname=True,
)

# Or use environment variables
# FF_LOG_LEVEL=INFO
# FF_LOG_FORMAT=json
# FF_LOG_ADD_TIMESTAMP=true
```

### Advanced Features

```python
from ff_logger import ScopedLogger

# Create custom logger with processors
logger = ScopedLogger(
    "custom",
    processors=[
        add_timestamp,
        add_hostname,
        filter_secrets,
        JSONRenderer(),
    ]
)

# Async support
async def process():
    logger.info("async_operation", status="started")
    await some_operation()
    logger.info("async_operation", status="completed")

# Exception logging with traceback
try:
    risky_operation()
except Exception as e:
    logger.exception("operation_failed", error=str(e))
```

## Logger Types

### ConsoleLogger
- Outputs to stdout/stderr with colors
- Human-readable format
- Best for development

### JSONLogger
- Outputs structured JSON lines
- Machine-parseable
- Best for production/log aggregation

### DatabaseLogger
- Writes to database table
- Supports PostgreSQL and MySQL
- Best for audit trails

### NullLogger
- No-op implementation
- Zero performance cost
- Best for testing or disabling logs

## Performance

The NullLogger provides true zero-cost logging:

```python
# With NullLogger, expensive operations are never executed
logger.debug("data", result=expensive_function())  # expensive_function() not called!

# No if statements needed in your code
# Just swap the logger implementation
```

## Development

```bash
# Install with dev dependencies
cd ff-logger
uv sync --extra dev

# Run tests
uv run pytest tests/

# Format code
uv run black src/
uv run ruff check src/

# Type checking
uv run mypy src/
```

## Configuration Options

| Option | Environment Variable | Default | Description |
|--------|---------------------|---------|-------------|
| `level` | `FF_LOG_LEVEL` | `INFO` | Minimum log level |
| `format` | `FF_LOG_FORMAT` | `console` | Output format (console/json) |
| `add_timestamp` | `FF_LOG_ADD_TIMESTAMP` | `true` | Include timestamps |
| `add_hostname` | `FF_LOG_ADD_HOSTNAME` | `false` | Include hostname |
| `add_process_info` | `FF_LOG_ADD_PROCESS_INFO` | `false` | Include PID/thread |

## License

Proprietary - Fenixflow Internal Use Only