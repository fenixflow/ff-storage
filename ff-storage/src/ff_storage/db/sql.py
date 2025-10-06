"""
Base SQL class providing flexible interface for database operations.
Based on ff_connections patterns for maximum flexibility.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SQL:
    """
    Abstract base class for SQL operations.
    Provides flexibility for different SQL backends.

    Subclasses must implement the abstract methods for their specific database.
    """

    dbname: str
    user: str
    password: str
    host: str
    port: int

    # Connection management
    pool: Optional[Any] = None
    connection: Optional[Any] = None
    cursor: Optional[Any] = None

    # Logging
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))

    # Connection methods
    def connect(self) -> None:
        """
        Establish a connection to the database.
        Must be implemented by subclasses.

        :raises NotImplementedError: Always, as this is an abstract method.
        """
        raise NotImplementedError("Subclass must implement 'connect'")

    def close_connection(self) -> None:
        """
        Close the database cursor and connection if they exist.
        Subclasses may override for specialized behavior (e.g., pooling).
        """
        if self.cursor:
            self.cursor.close()
            self.cursor = None
        if self.connection:
            self.connection.close()
            self.connection = None
            self.logger.info("Connection closed")

    # Query execution methods
    def read_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
        """
        Execute a read-only SQL query and fetch all rows.

        This method is intended for SELECT queries that do not modify the database.

        :param query: The SQL query to execute.
        :param params: Optional dictionary of parameters to be passed to the query.
        :return: A list of tuples, where each tuple represents a row.
        :raises NotImplementedError: Must be implemented by subclass.
        """
        raise NotImplementedError("Subclass must implement 'read_query'")

    def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> None:
        """
        Execute a SQL statement (INSERT, UPDATE, DELETE) that does not return rows.

        :param query: The SQL statement to be executed.
        :param params: Optional dictionary of parameters to be passed to the query.
        :raises NotImplementedError: Must be implemented by subclass.
        """
        raise NotImplementedError("Subclass must implement 'execute'")

    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
        """
        Execute a SQL query with RETURNING clause and fetch results.

        :param query: The SQL query to be executed (typically with RETURNING).
        :param params: Optional dictionary of parameters.
        :return: A list of tuples containing the returned rows.
        :raises NotImplementedError: Must be implemented by subclass.
        """
        raise NotImplementedError("Subclass must implement 'execute_query'")

    def execute_many(self, query: str, params_list: List[Dict[str, Any]]) -> None:
        """
        Execute the same query with multiple parameter sets (batch operations).

        :param query: The SQL statement to execute.
        :param params_list: List of parameter dictionaries.
        :raises NotImplementedError: Must be implemented by subclass.
        """
        raise NotImplementedError("Subclass must implement 'execute_many'")

    # Transaction management
    def begin_transaction(self) -> None:
        """
        Start a database transaction.

        :raises NotImplementedError: Can be overridden by subclass.
        """
        if self.connection:
            self.connection.autocommit = False
            self.logger.debug("Transaction started")

    def commit(self) -> None:
        """
        Commit the current transaction.

        :raises RuntimeError: If no connection exists.
        """
        if not self.connection:
            raise RuntimeError("No connection available for commit")
        self.connection.commit()
        self.logger.debug("Transaction committed")

    def rollback(self) -> None:
        """
        Rollback the current transaction.

        :raises RuntimeError: If no connection exists.
        """
        if not self.connection:
            raise RuntimeError("No connection available for rollback")
        self.connection.rollback()
        self.logger.debug("Transaction rolled back")

    # Utility methods
    def get_connection(self) -> "SQL":
        """
        Retrieve a new database connection instance.
        This method creates a new instance of the current class and establishes a connection.

        :return: New instance with established connection.
        :raises NotImplementedError: Can be overridden by subclass.
        """
        new_conn = type(self)(self.dbname, self.user, self.password, self.host, self.port)
        new_conn.connect()
        return new_conn

    def is_connected(self) -> bool:
        """
        Check if database connection is active.

        :return: True if connected, False otherwise.
        """
        return self.connection is not None

    @staticmethod
    def get_create_logs_table_sql(schema: str) -> str:
        """
        Return SQL needed to create a logs table.
        Database-specific implementations should override this.

        :param schema: The schema name for the logs table.
        :return: SQL string for creating logs table.
        :raises NotImplementedError: Must be implemented by subclass.
        """
        raise NotImplementedError("Subclass must implement 'get_create_logs_table_sql'")

    # Helper methods for common operations
    def table_exists(self, table_name: str, schema: Optional[str] = None) -> bool:
        """
        Check if a table exists in the database.

        :param table_name: Name of the table.
        :param schema: Optional schema name.
        :return: True if table exists, False otherwise.
        :raises NotImplementedError: Must be implemented by subclass.
        """
        raise NotImplementedError("Subclass must implement 'table_exists'")

    def get_table_columns(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get column information for a table.

        :param table_name: Name of the table.
        :param schema: Optional schema name.
        :return: List of column information dictionaries.
        :raises NotImplementedError: Must be implemented by subclass.
        """
        raise NotImplementedError("Subclass must implement 'get_table_columns'")
