"""
Database logger implementation for ff-logger.
"""

import logging
import random
import socket
import string
from datetime import datetime, timezone
from typing import Any

from .base import ScopedLogger
from .utils import extract_extra_fields


class DatabaseHandler(logging.Handler):
    """
    A logging handler that inserts log messages into a database table.
    Compatible with ff-storage database connections.
    """

    def __init__(
        self,
        db_connection,
        table_name: str = "logs",
        schema: str = "public",
        level: int | str = "DEBUG",
        ensure_table: bool = True,
    ):
        """
        Initialize the database handler.

        Args:
            db_connection: Database connection (ff_storage compatible)
            table_name: Name of the logs table (default: "logs")
            schema: Database schema (default: "public")
            level: Minimum log level as int or string (default: "DEBUG")
            ensure_table: Whether to create table if it doesn't exist
        """
        from ..utils import normalize_level

        super().__init__(level=normalize_level(level))
        self.db_connection = db_connection
        self.table_name = table_name
        self.schema = schema
        self.hostname = socket.gethostname()

        if ensure_table:
            self._ensure_table()

    def _ensure_table(self):
        """
        Ensure the logs table exists. Creates it if not present.
        """
        # This is PostgreSQL-specific SQL, but can be adapted
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.schema}.{self.table_name} (
            id SERIAL PRIMARY KEY,
            log_key VARCHAR(20) UNIQUE NOT NULL,
            log_level VARCHAR(20) NOT NULL,
            log_message TEXT NOT NULL,
            log_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
            logger_name VARCHAR(255),
            module VARCHAR(255),
            function_name VARCHAR(255),
            line_number INTEGER,
            hostname VARCHAR(255),
            process_id INTEGER,
            thread_id BIGINT,
            extra_data JSONB,
            exception_info TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_timestamp
            ON {self.schema}.{self.table_name}(log_timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_level
            ON {self.schema}.{self.table_name}(log_level);
        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_logger
            ON {self.schema}.{self.table_name}(logger_name);
        """

        try:
            # Handle both direct execute and transaction-based connections
            if hasattr(self.db_connection, "execute"):
                self.db_connection.execute(create_table_sql)
            elif hasattr(self.db_connection, "write_query"):
                # For ff_storage SQL connections
                for stmt in create_table_sql.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        self.db_connection.write_query(stmt)
        except Exception as e:
            # Log the error but don't fail initialization
            print(f"Warning: Could not ensure logs table exists: {e}")

    def emit(self, record: logging.LogRecord) -> None:
        """
        Insert a log record into the database.

        Args:
            record: The log record to insert
        """
        try:
            # Generate a unique key for this log entry
            log_key = "".join(random.choices(string.ascii_letters + string.digits, k=20))

            # Extract extra fields (context + kwargs)
            extra_data = extract_extra_fields(record)

            # Prepare the log entry
            log_entry = {
                "log_key": log_key,
                "log_level": record.levelname,
                "log_message": record.getMessage(),
                "log_timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc),
                "logger_name": record.name,
                "module": record.module,
                "function_name": record.funcName,
                "line_number": record.lineno,
                "hostname": self.hostname,
                "process_id": record.process,
                "thread_id": record.thread,
            }

            # Handle extra data as JSON
            if extra_data:
                # For PostgreSQL, we can use JSONB
                # For MySQL, we'd use JSON type
                import json

                log_entry["extra_data"] = json.dumps(extra_data)
            else:
                log_entry["extra_data"] = None

            # Handle exception info
            if record.exc_info:
                log_entry["exception_info"] = self.format(record)
            else:
                log_entry["exception_info"] = None

            # Build the INSERT statement
            insert_sql = f"""
            INSERT INTO {self.schema}.{self.table_name} (
                log_key, log_level, log_message, log_timestamp,
                logger_name, module, function_name, line_number,
                hostname, process_id, thread_id, extra_data, exception_info
            ) VALUES (
                %(log_key)s, %(log_level)s, %(log_message)s, %(log_timestamp)s,
                %(logger_name)s, %(module)s, %(function_name)s, %(line_number)s,
                %(hostname)s, %(process_id)s, %(thread_id)s,
                %(extra_data)s::jsonb, %(exception_info)s
            )
            """

            # Execute the insert
            if hasattr(self.db_connection, "execute"):
                self.db_connection.execute(insert_sql, log_entry)
            elif hasattr(self.db_connection, "write_query"):
                # For ff_storage SQL connections
                self.db_connection.write_query(insert_sql, log_entry)

        except Exception:
            # If insertion fails, use the parent class error handler
            self.handleError(record)


class DatabaseLogger(ScopedLogger):
    """
    A scoped logger that writes to a database table.
    Can optionally also write to console for debugging.
    """

    def __init__(
        self,
        name: str,
        db_connection,
        level: int | str = "DEBUG",
        context: dict[str, Any] | None = None,
        table_name: str = "logs",
        schema: str = "public",
        ensure_table: bool = True,
        also_console: bool = False,
    ):
        """
        Initialize the database logger.

        Args:
            name: Logger name
            db_connection: Database connection (ff_storage compatible)
            level: Logging level as int or string (default: "DEBUG")
            context: Permanent context fields
            table_name: Name of the logs table
            schema: Database schema
            ensure_table: Whether to create table if it doesn't exist
            also_console: Whether to also log to console
        """
        super().__init__(name, level, context)

        # Add database handler
        db_handler = DatabaseHandler(
            db_connection=db_connection,
            table_name=table_name,
            schema=schema,
            level=self.level,  # Use normalized level from parent
            ensure_table=ensure_table,
        )
        self.logger.addHandler(db_handler)

        # Optionally add console handler for debugging
        if also_console:
            console_handler = logging.StreamHandler()
            # No need to set handler level - inherits from logger

            # Use a simple formatter for console
            formatter = logging.Formatter("[%(asctime)s] %(levelname)s [%(name)s] %(message)s")
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

        # Store configuration for local use
        self.db_connection = db_connection
        self.table_name = table_name
        self.schema = schema
        self.also_console = also_console

    # bind() method inherited from ScopedLogger base class
