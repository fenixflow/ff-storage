# ff-logger

[![PyPI version](https://badge.fury.io/py/ff-logger.svg)](https://badge.fury.io/py/ff-logger)
[![Python Support](https://img.shields.io/pypi/pyversions/ff-logger.svg)](https://pypi.org/project/ff-logger/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A scoped, instance-based logging package for Fenixflow applications. Unlike traditional Python logging which uses a global configuration, ff-logger provides self-contained logger instances that can be passed around as objects, with support for context binding and multiple output formats.

Created by **Ben Moag** at **[Fenixflow](https://fenixflow.com)**

## Quick Start

### Installation

#### From PyPI
```bash
pip install ff-logger
```

#### From GitLab
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
    level="INFO",  # Can use strings now! (or logging.INFO)
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

Add permanent context fields to your logger instance:

```python
# Add context that will appear in all subsequent logs
logger.bind(
    request_id="req-456",
    user_id=789,
    ip="192.168.1.1"
)

# All messages now include the bound context
logger.info("Processing payment")
logger.error("Payment failed", error_code="CARD_DECLINED")

# bind() returns self for chaining
logger.bind(session_id="xyz").info("Session started")
```

**Note:** As of v0.3.0, `bind()` modifies the logger instance in place rather than creating a new one. This is cleaner and more intuitive. The method validates that fields are not reserved and values are JSON-serializable.

## Logger Types

### ConsoleLogger
Outputs colored, human-readable logs to console:

```python
from ff_logger import ConsoleLogger

logger = ConsoleLogger(
    name="app",
    level="INFO",  # String or int (logging.INFO)
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
    level="WARNING",  # String or int levels supported
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

### v0.4.0 Features

#### Temporary Context Manager
Use the `temp_context()` context manager to add temporary fields that are automatically removed:

```python
logger = ConsoleLogger("app")

with logger.temp_context(request_id="123", user_id=456):
    logger.info("Processing request")  # Includes request_id and user_id
    logger.info("Request complete")    # Still includes the fields

# Fields automatically removed after context
logger.info("Next request")  # request_id and user_id no longer present
```

#### Lazy Evaluation for Performance
Pass callables as kwargs to defer expensive computations until needed:

```python
logger = ConsoleLogger("app", level="ERROR")  # Only ERROR and above

# This callable is NEVER executed (DEBUG is disabled)
logger.debug("Debug info", expensive_data=lambda: compute_expensive_data())

# This callable IS executed (ERROR is enabled)
logger.error("Error occurred", context=lambda: gather_error_context())
```

#### Robust JSON Serialization
JSON logger now handles complex Python types without crashing:

```python
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from pathlib import Path

logger = JSONLogger("app")

# All of these work automatically
logger.info("Event",
    timestamp=datetime.now(),      # → ISO format string
    user_id=uuid4(),                # → string representation
    price=Decimal("19.99"),         # → float
    file_path=Path("/tmp/file"),    # → string
    status=Status.ACTIVE            # → enum value
)
```

#### Thread-Safe Context Updates
All context operations are now thread-safe:

```python
logger = ConsoleLogger("app")

# Safe to call from multiple threads
def worker(worker_id):
    logger.bind(worker_id=worker_id)
    logger.info("Worker started")

threads = [Thread(target=worker, args=(i,)) for i in range(10)]
```

### v0.3.0 Features

#### Flexible Log Levels
Accepts both string and integer log levels for better developer experience:
- Strings: `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`, `"CRITICAL"`
- Case-insensitive: `"info"` works the same as `"INFO"`
- Integers: Traditional `logging.DEBUG`, `logging.INFO`, etc.
- Numeric values: `10`, `20`, `30`, `40`, `50`

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

### Flexible Log Levels

```python
# All of these work now (v0.3.0+):
logger1 = ConsoleLogger("app", level="DEBUG")     # String
logger2 = ConsoleLogger("app", level="info")      # Case-insensitive
logger3 = ConsoleLogger("app", level=logging.INFO) # Traditional int
logger4 = ConsoleLogger("app", level=20)          # Numeric value
logger5 = ConsoleLogger("app")                    # Default: "DEBUG"

# Supported string levels:
# "DEBUG", "INFO", "WARNING"/"WARN", "ERROR", "CRITICAL"
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

Python's logging module reserves 23+ field names for LogRecord internals. If you use these as context fields in log calls, they're automatically prefixed with `x_` to prevent conflicts:

```python
# Constructor 'name' parameter - this works as expected
logger = ConsoleLogger("my_app")  # ✅ Sets logger name

# Log method 'name' kwarg - automatically prefixed to avoid conflict
logger.info("Message", name="custom")  # Becomes x_name="custom"

# Other reserved fields also prefixed
logger.info("Event",
    module="auth",      # Becomes x_module="auth"
    process="worker",   # Becomes x_process="worker"
    thread="t-1"        # Becomes x_thread="t-1"
)
```

**Reserved fields include:** `name`, `module`, `pathname`, `funcName`, `process`, `thread`, `levelname`, `msg`, `args`, and 15+ more. See [Python logging documentation](https://docs.python.org/3/library/logging.html#logrecord-attributes) for the complete list.

**Why?** These fields are used internally by Python's LogRecord class. Overwriting them would cause crashes like "Attempt to overwrite 'name' in LogRecord".

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