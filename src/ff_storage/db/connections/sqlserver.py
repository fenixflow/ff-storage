"""
SQL Server implementation of the SQL base class.
Provides both direct connections and async connection pooling for Microsoft SQL Server.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pyodbc

from ..sql import SQL


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

    def read_query(
        self, query: str, params: Optional[Dict[str, Any]] = None, as_dict: bool = True
    ) -> List[Any]:
        """
        Execute a read-only SQL query and fetch all rows.

        :param query: The SELECT SQL query.
        :param params: Optional dictionary of query parameters.
        :param as_dict: If True, return list of dicts. If False, return list of tuples.
        :return: A list of dicts (default) or tuples representing the query results.
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

            # Convert to dicts if requested
            if as_dict and cursor.description:
                columns = [col[0] for col in cursor.description]
                dict_results = [dict(zip(columns, row)) for row in results]
                cursor.close()
                return dict_results

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
class SQLServerPool:
    """
    Async SQL Server connection pool using aioodbc.

    This provides a high-performance async connection pool for SQL Server,
    suitable for FastAPI and other async Python applications.

    Pool handles connection acquisition internally - users just call fetch/execute methods.

    :param dbname: Database name.
    :param user: Database username.
    :param password: Database password.
    :param host: Database host.
    :param port: Database port (default: 1433).
    :param driver: ODBC driver name (default: ODBC Driver 18 for SQL Server).
    :param min_size: Minimum number of connections in the pool (default: 10).
    :param max_size: Maximum number of connections in the pool (default: 20).
    """

    dbname: str
    user: str
    password: str
    host: str
    port: int = 1433
    driver: str = "ODBC Driver 18 for SQL Server"
    min_size: int = 10
    max_size: int = 20

    # Pool instance
    pool: Optional[Any] = None

    # Logging
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))

    async def connect(self) -> None:
        """
        Create async connection pool.

        Call once at application startup (e.g., FastAPI startup event).

        :raises RuntimeError: If pool creation fails.
        """
        if self.pool:
            return  # Pool already created

        try:
            import aioodbc

            dsn = (
                f"Driver={{{self.driver}}};"
                f"Server=tcp:{self.host},{self.port};"
                f"Database={self.dbname};"
                f"Uid={self.user};"
                f"Pwd={self.password};"
                f"Encrypt=yes;"
                f"TrustServerCertificate=no;"
            )

            self.pool = await aioodbc.create_pool(
                dsn=dsn, minsize=self.min_size, maxsize=self.max_size
            )
            self.logger.info(
                f"Created aioodbc pool for {self.dbname} (min={self.min_size}, max={self.max_size})"
            )
        except Exception as e:
            self.logger.error(f"Failed to create aioodbc pool: {e}")
            raise RuntimeError(f"Error creating async pool: {e}")

    async def disconnect(self) -> None:
        """
        Close the connection pool.

        Call once at application shutdown (e.g., FastAPI shutdown event).
        """
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            self.pool = None
            self.logger.info("Closed aioodbc connection pool")

    async def fetch_one(self, query: str, params: dict = None, as_dict: bool = True):
        """
        Fetch single row from database.

        Pool handles connection acquisition internally.

        :param query: SQL query (use ? for parameters).
        :param params: Dictionary of query parameters.
        :param as_dict: If True, return dict. If False, return tuple.
        :return: Single row as dict (default) or tuple, or None if no results.
        """
        if not self.pool:
            raise RuntimeError("Pool not connected. Call await pool.connect() first.")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Only pass parameters if they exist and are not empty
                if params:
                    param_values = list(params.values())
                    await cursor.execute(query, param_values)
                else:
                    await cursor.execute(query)
                result = await cursor.fetchone()

                if result is None:
                    return None

                if as_dict and cursor.description:
                    columns = [col[0] for col in cursor.description]
                    return dict(zip(columns, result))

                return result

    async def fetch_all(self, query: str, params: dict = None, as_dict: bool = True):
        """
        Fetch all rows from database.

        Pool handles connection acquisition internally.

        :param query: SQL query (use ? for parameters).
        :param params: Dictionary of query parameters.
        :param as_dict: If True, return list of dicts. If False, return list of tuples.
        :return: List of dicts (default) or tuples.
        """
        if not self.pool:
            raise RuntimeError("Pool not connected. Call await pool.connect() first.")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Only pass parameters if they exist and are not empty
                if params:
                    param_values = list(params.values())
                    await cursor.execute(query, param_values)
                else:
                    await cursor.execute(query)
                results = await cursor.fetchall()

                if as_dict and cursor.description:
                    columns = [col[0] for col in cursor.description]
                    return [dict(zip(columns, row)) for row in results]

                return results

    async def execute(self, query: str, params: dict = None):
        """
        Execute query without returning results (INSERT, UPDATE, DELETE).

        Pool handles connection acquisition internally.

        :param query: SQL query (use ? for parameters).
        :param params: Dictionary of query parameters.
        :return: Row count.
        """
        if not self.pool:
            raise RuntimeError("Pool not connected. Call await pool.connect() first.")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Only pass parameters if they exist and are not empty
                if params:
                    param_values = list(params.values())
                    await cursor.execute(query, param_values)
                else:
                    await cursor.execute(query)
                await conn.commit()
                return cursor.rowcount

    async def execute_many(self, query: str, params_list: list):
        """
        Execute query with multiple parameter sets (batch operation).

        :param query: SQL query (use ? for parameters).
        :param params_list: List of parameter dictionaries.
        """
        if not self.pool:
            raise RuntimeError("Pool not connected. Call await pool.connect() first.")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Convert list of dicts to list of tuples
                param_tuples = [list(p.values()) for p in params_list]
                await cursor.executemany(query, param_tuples)
                await conn.commit()

    async def execute_query(self, query: str, params: dict = None):
        """
        Execute a query with OUTPUT clause and fetch the result.

        This method is for queries where SQL Server needs to return values
        after an INSERT, UPDATE, or DELETE operation using OUTPUT.

        :param query: The SQL query containing OUTPUT.
        :param params: Dictionary of query parameters.
        :return: A list of dictionaries with the returned values.
        :raises RuntimeError: If the query execution fails.
        """
        if not self.pool:
            raise RuntimeError("Pool not connected. Call await pool.connect() first.")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Only pass parameters if they exist and are not empty
                if params:
                    param_values = list(params.values())
                    await cursor.execute(query, param_values)
                else:
                    await cursor.execute(query)

                results = []
                if "OUTPUT" in query.upper():
                    results = await cursor.fetchall()
                    if cursor.description:
                        columns = [col[0] for col in cursor.description]
                        results = [dict(zip(columns, row)) for row in results]

                await conn.commit()
                return results

    async def table_exists(self, table_name: str, schema: str = None) -> bool:
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
        result = await self.fetch_one(query, {"schema": schema, "table": table_name}, as_dict=False)
        return result[0] == 1 if result else False

    async def get_table_columns(self, table_name: str, schema: str = None):
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
        results = await self.fetch_all(
            query, {"schema": schema, "table": table_name}, as_dict=False
        )

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
