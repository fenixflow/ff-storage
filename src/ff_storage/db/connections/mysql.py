"""
MySQL implementation of the SQL base class.
Provides both direct connections and async connection pooling.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import mysql.connector
from mysql.connector import Error

from ..sql import SQL

# Async pool requires aiomysql
try:
    import aiomysql
except ImportError:
    aiomysql = None


@dataclass
class MySQLBase(SQL):
    """
    Base class for MySQL operations, inheriting from SQL.

    This class provides core methods for executing queries and transactions.
    It does not automatically close connections, allowing the application
    to manage the connection lifecycle when required.
    """

    db_type = "mysql"

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
        if self.connection is None or self.cursor is None:
            self.logger.info("Database connection not established, reconnecting...")
            self.connect()

        try:
            self.cursor.execute(query, params or {})
            results = self.cursor.fetchall()

            # Convert to dicts if requested
            if as_dict and self.cursor.description:
                columns = [col[0] for col in self.cursor.description]
                return [dict(zip(columns, row)) for row in results]

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
        if not self.connection or not self.connection.is_connected() or self.cursor is None:
            self.connect()

        try:
            self.cursor.execute(query, params or {})
            self.connection.commit()
        except Error as e:
            self.connection.rollback()
            raise RuntimeError(f"Execution failed: {e}")

    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
        """
        Execute a query and return results.

        MySQL doesn't have RETURNING clause, so for INSERT operations,
        we return the last insert ID if available.

        :param query: The SQL query.
        :param params: Optional dictionary of query parameters.
        :return: Query results or last insert ID for INSERT operations.
        :raises RuntimeError: If the query execution fails.
        """
        if not self.connection or not self.connection.is_connected() or self.cursor is None:
            self.connect()

        try:
            self.cursor.execute(query, params or {})

            # Check if this was an INSERT operation
            if query.strip().upper().startswith("INSERT"):
                # Get last insert ID for INSERT operations
                last_id = self.cursor.lastrowid
                self.connection.commit()
                return [(last_id,)] if last_id else []
            else:
                # For SELECT or other operations that return data
                result = self.cursor.fetchall()
                self.connection.commit()
                return result
        except Error as e:
            self.connection.rollback()
            raise RuntimeError(f"Execution failed: {e}")

    def execute_many(self, query: str, params_list: List[Dict[str, Any]]) -> None:
        """
        Execute the same query with multiple parameter sets for batch operations.

        :param query: The SQL statement to execute.
        :param params_list: List of parameter dictionaries.
        :raises RuntimeError: If batch execution fails.
        """
        if not self.connection or not self.connection.is_connected() or self.cursor is None:
            self.connect()

        try:
            self.cursor.executemany(query, params_list)
            self.connection.commit()
        except Error as e:
            self.connection.rollback()
            raise RuntimeError(f"Batch execution failed: {e}")

    def table_exists(self, table_name: str, schema: Optional[str] = None) -> bool:
        """
        Check if a table exists in the database.

        :param table_name: Name of the table.
        :param schema: Optional schema/database name.
        :return: True if table exists, False otherwise.
        """
        schema = schema or self.dbname
        query = """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = %(schema)s
            AND table_name = %(table)s
        """
        result = self.read_query(query, {"schema": schema, "table": table_name})
        return result[0][0] > 0 if result else False

    def get_table_columns(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get column information for a table.

        :param table_name: Name of the table.
        :param schema: Optional schema/database name.
        :return: List of column information dictionaries.
        """
        schema = schema or self.dbname
        query = """
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length,
                column_key,
                extra
            FROM information_schema.columns
            WHERE table_schema = %(schema)s
            AND table_name = %(table)s
            ORDER BY ordinal_position
        """
        results = self.read_query(query, {"schema": schema, "table": table_name})

        return [
            {
                "name": row[0],
                "type": row[1],
                "nullable": row[2] == "YES",
                "default": row[3],
                "max_length": row[4],
                "key": row[5],
                "extra": row[6],
            }
            for row in results
        ]

    def get_open_connections(self) -> int:
        """
        Get the number of open MySQL connections.

        :return: Number of open connections, or -1 if unable to check.
        """
        try:
            result = self.read_query("SHOW STATUS WHERE `variable_name` = 'Threads_connected'")
            return int(result[0][1]) if result else -1
        except Exception as e:
            self.logger.error(f"Error checking open connections: {e}")
            return -1

    @staticmethod
    def get_create_logs_table_sql(schema: str) -> str:
        """
        Return SQL needed to create the schema and logs table in MySQL.

        :param schema: The schema/database name for the logs table.
        :return: SQL string for creating logs table.
        """
        return f"""
        CREATE DATABASE IF NOT EXISTS {schema};
        USE {schema};

        CREATE TABLE IF NOT EXISTS logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            level VARCHAR(50),
            message TEXT,
            metadata JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_timestamp (timestamp DESC),
            INDEX idx_level (level)
        );
        """

    def _create_database(self):
        """
        Create the database if it doesn't exist.

        This method connects without specifying a database to create the target database.
        """
        temp_conn = mysql.connector.connect(
            user=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            auth_plugin="mysql_native_password",
        )

        try:
            cursor = temp_conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.dbname}")
            self.logger.info(f"Created database: {self.dbname}")
            cursor.close()
        finally:
            temp_conn.close()

    def close_connection(self) -> None:
        """
        Close the database cursor and connection.
        """
        if self.cursor:
            self.cursor.close()
            self.cursor = None
        if self.connection and self.connection.is_connected():
            self.connection.close()
            self.connection = None
        self.logger.info("MySQL connection closed")


@dataclass
class MySQL(MySQLBase):
    """
    Direct MySQL connection without pooling.

    This implementation creates a dedicated connection to the MySQL database.
    Suitable for simple applications or scripts that don't require connection pooling.

    :param dbname: Database name.
    :param user: Database username.
    :param password: Database password.
    :param host: Database host.
    :param port: Database port.
    """

    def connect(self) -> None:
        """
        Establish a direct connection to the MySQL database.

        If the database does not exist, attempts to create it and then reconnect.

        :raises mysql.connector.Error: If connecting fails.
        """
        if self.connection and self.connection.is_connected():
            if not self.cursor:
                self.cursor = self.connection.cursor()
            return

        try:
            self.connection = mysql.connector.connect(
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port,
                database=self.dbname,
                auth_plugin="mysql_native_password",
                allow_local_infile=True,
            )
            self.cursor = self.connection.cursor()
            self.logger.info(f"Connected to MySQL database: {self.dbname}")
        except Error as e:
            if "1049" in str(e) or "Unknown database" in str(e):
                self.logger.info(f"Database {self.dbname} does not exist, creating...")
                self._create_database()
                self.connect()  # Retry after database creation
            else:
                raise


@dataclass
class MySQLPool:
    """
    Async MySQL connection pool using aiomysql.

    This provides a high-performance async connection pool for MySQL,
    suitable for FastAPI and other async Python applications.

    Pool handles connection acquisition internally - users just call fetch/execute methods.

    :param dbname: Database name.
    :param user: Database username.
    :param password: Database password.
    :param host: Database host.
    :param port: Database port.
    :param min_size: Minimum number of connections in the pool (default: 5).
    :param max_size: Maximum number of connections in the pool (default: 10).
    """

    dbname: str
    user: str
    password: str
    host: str
    port: int = 3306
    min_size: int = 5
    max_size: int = 10

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
            import aiomysql

            self.pool = await aiomysql.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.dbname,
                minsize=self.min_size,
                maxsize=self.max_size,
                autocommit=True,
            )
            self.logger.info(
                f"Created aiomysql pool for {self.dbname} (min={self.min_size}, max={self.max_size})"
            )
        except Exception as e:
            self.logger.error(f"Failed to create aiomysql pool: {e}")
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
            self.logger.info("Closed aiomysql connection pool")

    async def fetch_one(self, query: str, params: dict = None, as_dict: bool = True):
        """
        Fetch single row from database.

        Pool handles connection acquisition internally.

        :param query: SQL query (use %(name)s for named parameters).
        :param params: Dictionary of query parameters.
        :param as_dict: If True, return dict. If False, return tuple.
        :return: Single row as dict (default) or tuple, or None if no results.
        """
        if not self.pool:
            raise RuntimeError("Pool not connected. Call await pool.connect() first.")

        async with self.pool.acquire() as conn:
            cursor_class = aiomysql.DictCursor if as_dict else None
            async with conn.cursor(cursor_class) as cursor:
                await cursor.execute(query, params or {})
                return await cursor.fetchone()

    async def fetch_all(self, query: str, params: dict = None, as_dict: bool = True):
        """
        Fetch all rows from database.

        Pool handles connection acquisition internally.

        :param query: SQL query (use %(name)s for named parameters).
        :param params: Dictionary of query parameters.
        :param as_dict: If True, return list of dicts. If False, return list of tuples.
        :return: List of dicts (default) or tuples.
        """
        if not self.pool:
            raise RuntimeError("Pool not connected. Call await pool.connect() first.")

        async with self.pool.acquire() as conn:
            cursor_class = aiomysql.DictCursor if as_dict else None
            async with conn.cursor(cursor_class) as cursor:
                await cursor.execute(query, params or {})
                return await cursor.fetchall()

    async def execute(self, query: str, params: dict = None):
        """
        Execute query without returning results (INSERT, UPDATE, DELETE).

        Pool handles connection acquisition internally.

        :param query: SQL query (use %(name)s for named parameters).
        :param params: Dictionary of query parameters.
        :return: Number of affected rows.
        """
        if not self.pool:
            raise RuntimeError("Pool not connected. Call await pool.connect() first.")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                result = await cursor.execute(query, params or {})
                await conn.commit()
                return result

    async def execute_many(self, query: str, params_list: list):
        """
        Execute query with multiple parameter sets (batch operation).

        :param query: SQL query (use %(name)s for named parameters).
        :param params_list: List of parameter dictionaries.
        """
        if not self.pool:
            raise RuntimeError("Pool not connected. Call await pool.connect() first.")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.executemany(query, params_list)
                await conn.commit()
