"""
MySQL implementation of the SQL base class.
Provides both direct connections and connection pooling.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import mysql.connector
from mysql.connector import pooling, Error
from .sql import SQL


@dataclass
class MySQLBase(SQL):
    """
    Base class for MySQL operations, inheriting from SQL.

    This class provides core methods for executing queries and transactions.
    It does not automatically close connections, allowing the application
    to manage the connection lifecycle when required.
    """

    db_type = "mysql"

    def read_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
        """
        Execute a read-only SQL query and fetch all rows.

        :param query: The SELECT SQL query.
        :param params: Optional dictionary of query parameters.
        :return: A list of tuples representing the query results.
        :raises RuntimeError: If query execution fails.
        """
        if self.connection is None or self.cursor is None:
            self.logger.info("Database connection not established, reconnecting...")
            self.connect()

        try:
            self.cursor.execute(query, params or {})
            return self.cursor.fetchall()
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
class MySQLPool(MySQLBase):
    """
    MySQL connection using a connection pool.

    This implementation acquires connections from a MySQL pool,
    ensuring efficient resource management. Connections are returned
    to the pool rather than closed, allowing for reuse.

    Suitable for production applications with multiple concurrent database operations.

    :param dbname: Database name.
    :param user: Database username.
    :param password: Database password.
    :param host: Database host.
    :param port: Database port.
    :param pool_name: The name of the connection pool (default: mysql_pool).
    :param pool_size: Number of connections in the pool (default: 5).
    """

    pool_name: str = "mysql_pool"
    pool_size: int = 5

    def connect(self) -> None:
        """
        Acquire a connection from the pool.

        If the pool does not exist, it is created. If the database doesn't exist,
        it will be created automatically.

        :raises RuntimeError: If acquiring a connection fails.
        """
        # Create pool if it doesn't exist
        if not self.pool:
            cnx_config = {
                "user": self.user,
                "password": self.password,
                "host": self.host,
                "port": self.port,
                "database": self.dbname,
                "allow_local_infile": True,
                "pool_name": self.pool_name,
                "pool_size": self.pool_size,
                "pool_reset_session": True,
                "auth_plugin": "mysql_native_password",
            }

            try:
                self.pool = pooling.MySQLConnectionPool(**cnx_config)
                self.logger.info(
                    f"Created connection pool '{self.pool_name}' with size {self.pool_size}"
                )
            except Error as e:
                if "1049" in str(e) or "Unknown database" in str(e):
                    self.logger.info(f"Database {self.dbname} does not exist, creating...")
                    self._create_database()
                    # Retry pool creation
                    self.pool = pooling.MySQLConnectionPool(**cnx_config)
                else:
                    raise

        # Acquire connection from pool if not already connected
        if not self.connection or not self.connection.is_connected() or self.cursor is None:
            try:
                self.connection = self.pool.get_connection()
                self.cursor = self.connection.cursor()

                # Log connection status
                open_connections = self.get_open_connections()
                self.logger.debug(
                    f"Acquired connection from pool. Open connections: {open_connections}"
                )
            except Error as e:
                raise RuntimeError(f"Error acquiring pooled connection: {e}")

    def close_connection(self) -> None:
        """
        Return the connection to the pool without closing it.

        This allows the connection to be reused by other operations.
        """
        if self.cursor:
            self.cursor.close()
            self.cursor = None

        # Connection is automatically returned to pool when it goes out of scope
        # But we can explicitly set it to None to release the reference
        if self.connection:
            self.connection = None
            self.logger.debug("Returned connection to pool")

    def close_pool(self) -> None:
        """
        Close all connections in the pool.

        This should only be called when shutting down the application.
        """
        if self.pool:
            # Close all connections in the pool
            # Note: mysql-connector-python doesn't have a direct closeall method
            # Connections will be closed when the pool is garbage collected
            self.pool = None
            self.logger.info(f"Closed connection pool '{self.pool_name}'")
