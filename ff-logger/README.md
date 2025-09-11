# ff-logger

[![PyPI version](https://badge.fury.io/py/ff-logger.svg)](https://badge.fury.io/py/ff-logger)
[![Python Support](https://img.shields.io/pypi/pyversions/ff-logger.svg)](https://pypi.org/project/ff-logger/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A scoped, instance-based logging package for Fenixflow applications. Unlike traditional Python logging which uses a global configuration, ff-logger provides self-contained logger instances that can be passed around as objects, with support for context binding and multiple output formats.

Created by **Ben Moag** at **[Fenixflow](https://fenixflow.com)**

## Quick Start

### Installation

#### From PyPI (when published)
```bash
pip install ff-logger
```

#### From GitLab (current)
```bash
pip install git+https://gitlab.com/fenixflow/fenix-packages.git#subdirectory=ff-logger
```

### Basic Usage

```python
from ff_logger import ConsoleLogger
import logging

# Create a logger instance with permanent context
logger = ConsoleLogger(
    name="my_app",
    level=logging.INFO,
    context={"service": "api", "environment": "production"}
)

# Log messages with the permanent context
logger.info("Application started")
# Output: [2025-08-20 10:00:00] INFO [my_app] Application started | service="api" environment="production"

# Add runtime context with kwargs
logger.info("Request processed", request_id="req-123", duration=45)
# Output includes both permanent and runtime context
```

### Context Binding

Create scoped loggers with additional permanent context:

```python
# Create a request-scoped logger
request_logger = logger.bind(
    request_id="req-456",
    user_id=789,
    ip="192.168.1.1"
)

# All messages from request_logger include the bound context
request_logger.info("Processing payment")
request_logger.error("Payment failed", error_code="CARD_DECLINED")
```

## Logger Types

### ConsoleLogger
Outputs colored, human-readable logs to console:

```python
from ff_logger import ConsoleLogger

logger = ConsoleLogger(
    name="app",
    level=logging.INFO,
    colors=True,  # Enable colored output
    show_hostname=False  # Optional hostname in logs
)
```

### JSONLogger
Outputs structured JSON lines, perfect for log aggregation:

```python
from ff_logger import JSONLogger

logger = JSONLogger(
    name="app",
    level=logging.INFO,
    show_hostname=True,
    include_timestamp=True
)

logger.info("Event occurred", event_type="user_login", user_id=123)
# Output: {"level":"INFO","logger":"app","message":"Event occurred","timestamp":"2025-08-20T10:00:00Z","event_type":"user_login","user_id":123,...}
```

### FileLogger
Writes to files with rotation support:

```python
from ff_logger import FileLogger

logger = FileLogger(
    name="app",
    filename="/var/log/app.log",
    rotation_type="size",  # "size", "time", or "none"
    max_bytes=10*1024*1024,  # 10MB
    backup_count=5
)
```

### NullLogger
Zero-cost logger for testing or when logging is disabled:

```python
from ff_logger import NullLogger

# Preferred: Use directly as a class (no instantiation needed)
NullLogger.info("This does nothing")  # No-op
NullLogger.debug("Debug message")     # No-op

# As a default parameter (perfect for dependency injection)
def process_data(data, logger=NullLogger):
    logger.info("Processing data: %s", data)
    return data * 2

# Call without providing a logger
result = process_data([1, 2, 3])

# Backward compatibility: Can still instantiate if needed
logger = NullLogger()  # All parameters are optional
logger.info("This also does nothing")
```

### DatabaseLogger
Writes logs to a database table (requires ff-storage):

```python
from ff_logger import DatabaseLogger
from ff_storage.db.postgres import PostgresPool

db = PostgresPool(...)
logger = DatabaseLogger(
    name="app",
    db_connection=db,
    table_name="logs",
    schema="public"
)
```

## Key Features

### Instance-Based
Each logger is a self-contained instance with its own configuration:

```python
def process_data(logger):
    """Accept any logger instance."""
    logger.info("Processing started")
    # ... do work ...
    logger.info("Processing complete")

# Use with different loggers
console = ConsoleLogger("console")
json_log = JSONLogger("json")

process_data(console)  # Outputs to console
process_data(json_log)  # Outputs as JSON
```

### Context Preservation
Permanent context fields appear in every log message:

```python
logger = ConsoleLogger(
    name="worker",
    context={
        "worker_id": "w-1",
        "datacenter": "us-east-1"
    }
)

# Every log includes worker_id and datacenter
logger.info("Task started")
logger.error("Task failed")
```

### Zero Dependencies
Built entirely on Python's standard `logging` module - no external dependencies required for core functionality.

## Migration from Traditional Logging

```python
# Traditional Python logging (global)
import logging
logging.info("Message")

# ff-logger (instance-based)
from ff_logger import ConsoleLogger
logger = ConsoleLogger("app")
logger.info("Message")
```

## Advanced Usage

### Custom Log Levels

```python
import logging

# Create logger with custom level
logger = ConsoleLogger(
    name="debug_app",
    level=logging.DEBUG  # Show all messages including debug
)
```

### Exception Logging

```python
try:
    risky_operation()
except Exception:
    logger.exception("Operation failed")
    # Automatically includes full traceback
```

### Reserved Fields

Some field names are reserved by Python's logging module. If you use them, they'll be automatically prefixed with `x_`:

```python
# "module" is reserved, becomes "x_module"
logger.info("Message", module="auth")
```

## Testing

Use `NullLogger` in tests for zero overhead:

```python
def test_my_function():
    # Option 1: Pass the class directly
    result = my_function(logger=NullLogger)  # No logging output
    assert result == expected
    
    # Option 2: Functions with NullLogger as default
    def my_function(data, logger=NullLogger):
        logger.info("Processing: %s", data)
        return process(data)
    
    # In tests, just call without logger parameter
    result = my_function(test_data)  # Silent by default
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request to the [GitLab repository](https://gitlab.com/fenixflow/fenix-packages).

## License

MIT License - see [LICENSE](LICENSE) file for details.

Copyright (c) 2024 Ben Moag / Fenixflow