"""
SQL Server implementation of the SQL base class.
Provides both direct connections and connection pooling for Microsoft SQL Server.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pyodbc

from .sql import SQL


@dataclass
class SQLServerBase(SQL):
    """
    Base class for SQL Server operations, inheriting from SQL.

    This class provides core methods for executing queries and transactions.
    It does not automatically close connections, allowing the application
    to manage the connection lifecycle when required.
    """

    db_type = "sqlserver"
    driver: str = "ODBC Driver 18 for SQL Server"

    def read_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
        """
        Execute a read-only SQL query and fetch all rows.

        :param query: The SELECT SQL query.
        :param params: Optional dictionary of query parameters.
        :return: A list of tuples representing the query results.
        :raises RuntimeError: If query execution fails.
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()
            if params:
                # Convert dict params to positional for pyodbc
                cursor.execute(query, list(params.values()) if params else None)
            else:
                cursor.execute(query)

            results = cursor.fetchall()
            cursor.close()
            return results
        except Exception as e:
            self.logger.error(f"Database query error: {e}")
            return []

    def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> None:
        """
        Execute a non-returning SQL statement (INSERT, UPDATE, DELETE) and commit.

        :param query: The SQL statement.
        :param params: Optional dictionary of query parameters.
        :raises RuntimeError: If an error occurs during execution.
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()
            if params:
                cursor.execute(query, list(params.values()) if params else None)
            else:
                cursor.execute(query)
            self.connection.commit()
            cursor.close()
        except Exception as e:
            self.connection.rollback()
            raise RuntimeError(f"Execution failed: {e}")

    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
        """
        Execute a query with OUTPUT clause and fetch the result.

        This method is for queries where SQL Server needs to return values
        after an INSERT, UPDATE, or DELETE operation using OUTPUT.

        :param query: The SQL query containing OUTPUT.
        :param params: Optional dictionary of query parameters.
        :return: A list of tuples with the returned values.
        :raises RuntimeError: If the query execution fails.
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()
            if params:
                cursor.execute(query, list(params.values()) if params else None)
            else:
                cursor.execute(query)

            result = cursor.fetchall() if "OUTPUT" in query.upper() else []
            self.connection.commit()
            cursor.close()
            return result
        except Exception as e:
            self.connection.rollback()
            raise RuntimeError(f"Execution failed: {e}")

    def execute_many(self, query: str, params_list: List[Dict[str, Any]]) -> None:
        """
        Execute the same query with multiple parameter sets for batch operations.

        :param query: The SQL statement to execute.
        :param params_list: List of parameter dictionaries.
        :raises RuntimeError: If batch execution fails.
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()
            # Convert list of dicts to list of tuples for executemany
            params_tuples = [list(p.values()) for p in params_list]
            cursor.executemany(query, params_tuples)
            self.connection.commit()
            cursor.close()
        except Exception as e:
            self.connection.rollback()
            raise RuntimeError(f"Batch execution failed: {e}")

    def table_exists(self, table_name: str, schema: Optional[str] = None) -> bool:
        """
        Check if a table exists in the database.

        :param table_name: Name of the table.
        :param schema: Optional schema name (default: dbo).
        :return: True if table exists, False otherwise.
        """
        schema = schema or "dbo"
        query = """
            SELECT CASE WHEN EXISTS (
                SELECT * FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
            ) THEN 1 ELSE 0 END
        """
        result = self.read_query(query, {"schema": schema, "table": table_name})
        return result[0][0] == 1 if result else False

    def get_table_columns(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get column information for a table.

        :param table_name: Name of the table.
        :param schema: Optional schema name (default: dbo).
        :return: List of column information dictionaries.
        """
        schema = schema or "dbo"
        query = """
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                IS_NULLABLE,
                COLUMN_DEFAULT,
                CHARACTER_MAXIMUM_LENGTH,
                ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
        """
        results = self.read_query(query, {"schema": schema, "table": table_name})

        return [
            {
                "name": row[0],
                "type": row[1],
                "nullable": row[2] == "YES",
                "default": row[3],
                "max_length": row[4],
                "position": row[5],
            }
            for row in results
        ]

    @staticmethod
    def get_create_logs_table_sql(schema: str) -> str:
        """
        Return SQL needed to create the schema and logs table in SQL Server.

        :param schema: The schema name for the logs table.
        :return: SQL string for creating schema and logs table.
        """
        return f"""
        IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = '{schema}')
        BEGIN
            EXEC('CREATE SCHEMA {schema}')
        END

        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES
                       WHERE TABLE_SCHEMA = '{schema}' AND TABLE_NAME = 'logs')
        BEGIN
            CREATE TABLE {schema}.logs (
                id INT IDENTITY(1,1) PRIMARY KEY,
                timestamp DATETIME2 DEFAULT GETDATE(),
                level VARCHAR(50),
                message NVARCHAR(MAX),
                metadata NVARCHAR(MAX),
                created_at DATETIME2 DEFAULT GETDATE()
            );

            CREATE INDEX idx_{schema}_logs_timestamp ON {schema}.logs(timestamp DESC);
            CREATE INDEX idx_{schema}_logs_level ON {schema}.logs(level);
        END
        """


@dataclass
class SQLServer(SQLServerBase):
    """
    Direct SQL Server connection without pooling.

    This implementation creates a dedicated connection to the SQL Server database.
    Suitable for simple applications or scripts that don't require connection pooling.

    :param dbname: Database name.
    :param user: Database username.
    :param password: Database password.
    :param host: Database host.
    :param port: Database port (default: 1433).
    :param driver: ODBC driver name (default: ODBC Driver 18 for SQL Server).
    """

    def connect(self) -> None:
        """
        Establish a direct connection to the SQL Server database.

        :raises pyodbc.Error: If connecting fails.
        """
        if self.connection:
            return  # Connection is already established

        try:
            connection_string = (
                f"Driver={{{self.driver}}};"
                f"Server=tcp:{self.host},{self.port};"
                f"Database={self.dbname};"
                f"Uid={self.user};"
                f"Pwd={self.password};"
                f"Encrypt=yes;"
                f"TrustServerCertificate=no;"
                f"Connection Timeout=30;"
            )
            self.connection = pyodbc.connect(connection_string)
            self.logger.info(f"Connected to SQL Server database: {self.dbname}")
        except Exception as e:
            self.logger.error(f"Failed to connect to SQL Server: {e}")
            raise


@dataclass
class SQLServerPool(SQLServerBase):
    """
    SQL Server connection using a connection pool.

    Note: pyodbc doesn't have built-in connection pooling like psycopg2.
    This implementation manages a simple pool of connections manually.

    For production use with Azure SQL, consider using connection pooling
    at the application level or Azure SQL's built-in connection pooling.

    :param dbname: Database name.
    :param user: Database username.
    :param password: Database password.
    :param host: Database host.
    :param port: Database port (default: 1433).
    :param driver: ODBC driver name.
    :param pool_name: The name of the connection pool (default: sqlserver_pool).
    :param pool_size: Maximum number of connections (advisory, not enforced).
    """

    pool_name: str = "sqlserver_pool"
    pool_size: int = 10

    def connect(self) -> None:
        """
        Acquire a connection.

        Note: pyodbc doesn't provide connection pooling out of the box.
        This creates a single connection. For true pooling, use an external
        library or connection pool manager.

        :raises RuntimeError: If acquiring a connection fails.
        """
        if self.connection:
            return

        try:
            connection_string = (
                f"Driver={{{self.driver}}};"
                f"Server=tcp:{self.host},{self.port};"
                f"Database={self.dbname};"
                f"Uid={self.user};"
                f"Pwd={self.password};"
                f"Encrypt=yes;"
                f"TrustServerCertificate=no;"
                f"Connection Timeout=30;"
                f"MARS_Connection=yes;"  # Enable Multiple Active Result Sets
            )
            self.connection = pyodbc.connect(connection_string, pooling=True)
            self.logger.info(
                f"Connected to SQL Server pool '{self.pool_name}' (size: {self.pool_size})"
            )
        except Exception as e:
            self.logger.error(f"Failed to connect to SQL Server pool: {e}")
            raise RuntimeError(f"Error acquiring pooled connection: {e}")

    def close_connection(self) -> None:
        """
        Close the connection.

        With pyodbc pooling enabled, this returns the connection to the pool.
        """
        if self.connection:
            self.connection.close()
            self.connection = None
            self.logger.debug("Returned connection to pool")
