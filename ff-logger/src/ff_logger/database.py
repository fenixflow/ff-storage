"""
Database logger implementation for audit trails.
"""

import random
import socket
import string
from datetime import datetime, timezone
from typing import Any

import structlog
from structlog.types import Processor

from .base import ScopedLogger


class DatabaseProcessor:
    """
    A structlog processor that writes log entries to a database.
    """

    def __init__(self, db_connection, schema: str = "logs", table: str = "logs"):
        """
        Initialize database processor.

        Args:
            db_connection: Database connection (must have execute method)
            schema: Database schema name
            table: Table name for logs
        """
        self.db_connection = db_connection
        self.schema = schema
        self.table = table
        self.hostname = socket.gethostname()
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Ensure the logs table exists."""
        # This is a simplified version - adapt based on your database
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.schema}.{self.table} (
            log_key VARCHAR(20) PRIMARY KEY,
            log_level VARCHAR(20),
            log_message TEXT,
            log_timestamp TIMESTAMP WITH TIME ZONE,
            logger_name VARCHAR(255),
            module VARCHAR(255),
            function_name VARCHAR(255),
            line_number INTEGER,
            hostname VARCHAR(255),
            context JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """
        try:
            if hasattr(self.db_connection, "execute"):
                self.db_connection.execute(create_sql)
        except Exception as e:
            # Table might already exist or schema issues
            print(f"Warning: Could not create logs table: {e}")

    def __call__(self, logger, name, event_dict):
        """
        Process a log entry and write to database.

        This is called by structlog for each log message.
        """
        try:
            # Generate unique key for this log entry
            log_key = "".join(random.choices(string.ascii_letters + string.digits, k=20))

            # Extract standard fields
            log_entry = {
                "log_key": log_key,
                "log_level": event_dict.get("level", "INFO"),
                "log_message": event_dict.get("event", ""),
                "log_timestamp": datetime.now(timezone.utc),
                "logger_name": event_dict.get("logger", ""),
                "module": event_dict.get("module", ""),
                "function_name": event_dict.get("func_name", ""),
                "line_number": event_dict.get("lineno", 0),
                "hostname": self.hostname,
            }

            # Store remaining fields as context JSON
            context_fields = {
                k: v
                for k, v in event_dict.items()
                if k not in ["level", "event", "logger", "module", "func_name", "lineno"]
            }

            insert_sql = f"""
            INSERT INTO {self.schema}.{self.table} (
                log_key, log_level, log_message, log_timestamp,
                logger_name, module, function_name, line_number,
                hostname, context
            ) VALUES (
                %(log_key)s, %(log_level)s, %(log_message)s, %(log_timestamp)s,
                %(logger_name)s, %(module)s, %(function_name)s, %(line_number)s,
                %(hostname)s, %(context)s::jsonb
            )
            """

            log_entry["context"] = str(context_fields)  # Convert to JSON string

            if hasattr(self.db_connection, "execute"):
                self.db_connection.execute(insert_sql, log_entry)

        except Exception as e:
            # Don't let database errors break the application
            print(f"Failed to write log to database: {e}")

        # Always return the event_dict to allow other processors to run
        return event_dict


class DatabaseLogger(ScopedLogger):
    """
    A logger that writes to a database for audit trails.

    Can optionally also output to console for debugging.
    """

    def __init__(
        self,
        name: str,
        db_connection,
        schema: str = "logs",
        table: str = "logs",
        context: dict[str, Any] | None = None,
        also_print: bool = False,
    ):
        """
        Initialize a database logger.

        Args:
            name: Logger name/scope
            db_connection: Database connection object
            schema: Database schema for logs table
            table: Table name for logs
            context: Initial context dictionary
            also_print: Whether to also print to console
        """
        self.db_connection = db_connection
        self.schema = schema
        self.table = table
        self.also_print = also_print

        super().__init__(name=name, context=context)

    def _get_default_processors(self) -> list[Processor]:
        """Get database-specific processors."""
        processors = [
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                ]
            ),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            DatabaseProcessor(
                db_connection=self.db_connection,
                schema=self.schema,
                table=self.table,
            ),
        ]

        # Optionally add console output
        if self.also_print:
            processors.append(structlog.dev.ConsoleRenderer())

        return processors
