"""
PostgreSQL implementation of the SQL base class.
Provides both direct connections and connection pooling.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import psycopg2
from psycopg2 import pool, OperationalError, DatabaseError
from .sql import SQL


@dataclass
class PostgresBase(SQL):
    """
    Base class for PostgreSQL operations, inheriting from SQL.

    This class provides core methods for executing queries and transactions.
    It does not automatically close connections, allowing the application
    to manage the connection lifecycle when required.
    """

    db_type = "postgres"

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
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
        except DatabaseError as e:
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
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise RuntimeError(f"Execution failed: {e}")

    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
        """
        Execute a query that includes a RETURNING statement and fetch the result.

        This method is specifically for queries where PostgreSQL needs to return values
        after an INSERT, UPDATE, or DELETE operation.

        :param query: The SQL query containing RETURNING.
        :param params: Optional dictionary of query parameters.
        :return: A list of tuples with the returned values.
        :raises RuntimeError: If the query execution fails.
        """
        if not self.connection:
            self.connect()

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                result = cursor.fetchall() if "RETURNING" in query.upper() else []
                self.connection.commit()
                return result
        except DatabaseError as e:
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
            with self.connection.cursor() as cursor:
                cursor.executemany(query, params_list)
                self.connection.commit()
        except DatabaseError as e:
            self.connection.rollback()
            raise RuntimeError(f"Batch execution failed: {e}")

    def table_exists(self, table_name: str, schema: Optional[str] = None) -> bool:
        """
        Check if a table exists in the database.

        :param table_name: Name of the table.
        :param schema: Optional schema name (default: public).
        :return: True if table exists, False otherwise.
        """
        schema = schema or "public"
        query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = %(schema)s
                AND table_name = %(table)s
            )
        """
        result = self.read_query(query, {"schema": schema, "table": table_name})
        return result[0][0] if result else False

    def get_table_columns(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get column information for a table.

        :param table_name: Name of the table.
        :param schema: Optional schema name (default: public).
        :return: List of column information dictionaries.
        """
        schema = schema or "public"
        query = """
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length
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
            }
            for row in results
        ]

    @staticmethod
    def get_create_logs_table_sql(schema: str) -> str:
        """
        Return SQL needed to create the schema and logs table in PostgreSQL.

        :param schema: The schema name for the logs table.
        :return: SQL string for creating schema and logs table.
        """
        return f"""
        CREATE SCHEMA IF NOT EXISTS {schema};

        CREATE TABLE IF NOT EXISTS {schema}.logs (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            level VARCHAR(50),
            message TEXT,
            metadata JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_{schema}_logs_timestamp
        ON {schema}.logs(timestamp DESC);

        CREATE INDEX IF NOT EXISTS idx_{schema}_logs_level
        ON {schema}.logs(level);
        """

    def _create_database(self):
        """
        Create the database if it doesn't exist.

        This method connects to the 'postgres' database to create the target database.
        """
        temp_conn = psycopg2.connect(
            dbname="postgres",
            user=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
        )
        temp_conn.autocommit = True

        try:
            with temp_conn.cursor() as cursor:
                # Check if database exists
                cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (self.dbname,))
                if not cursor.fetchone():
                    cursor.execute(f"CREATE DATABASE {self.dbname}")
                    self.logger.info(f"Created database: {self.dbname}")
        finally:
            temp_conn.close()


@dataclass
class Postgres(PostgresBase):
    """
    Direct PostgreSQL connection without pooling.

    This implementation creates a dedicated connection to the PostgreSQL database.
    Suitable for simple applications or scripts that don't require connection pooling.

    :param dbname: Database name.
    :param user: Database username.
    :param password: Database password.
    :param host: Database host.
    :param port: Database port.
    """

    def connect(self) -> None:
        """
        Establish a direct connection to the PostgreSQL database.

        If the database does not exist, attempts to create it and then reconnect.

        :raises psycopg2.OperationalError: If connecting fails.
        """
        if self.connection:
            return  # Connection is already established

        try:
            self.connection = psycopg2.connect(
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port,
            )
            self.logger.info(f"Connected to PostgreSQL database: {self.dbname}")
        except OperationalError as e:
            if "does not exist" in str(e):
                self.logger.info(f"Database {self.dbname} does not exist, creating...")
                self._create_database()
                self.connect()
            else:
                raise


@dataclass
class PostgresPool(PostgresBase):
    """
    PostgreSQL connection using a connection pool.

    This implementation acquires connections from a PostgreSQL pool,
    ensuring efficient resource management. Connections are returned
    to the pool rather than closed, allowing for reuse.

    Suitable for production applications with multiple concurrent database operations.

    :param dbname: Database name.
    :param user: Database username.
    :param password: Database password.
    :param host: Database host.
    :param port: Database port.
    :param pool_name: The name of the connection pool (default: postgres_pool).
    :param pool_size: Maximum number of connections in the pool (default: 10).
    """

    pool_name: str = "postgres_pool"
    pool_size: int = 10

    def connect(self) -> None:
        """
        Acquire a connection from the pool.

        If the pool does not exist, it is created. If the database doesn't exist,
        it will be created automatically.

        :raises RuntimeError: If acquiring a connection fails.
        """
        # Create pool if it doesn't exist
        if not hasattr(self, "pool") or self.pool is None:
            try:
                self.pool = pool.SimpleConnectionPool(
                    minconn=1,
                    maxconn=self.pool_size,
                    dbname=self.dbname,
                    user=self.user,
                    password=self.password,
                    host=self.host,
                    port=self.port,
                )
                self.logger.info(
                    f"Created connection pool '{self.pool_name}' with size {self.pool_size}"
                )
            except OperationalError as e:
                if "does not exist" in str(e):
                    self.logger.info(f"Database {self.dbname} does not exist, creating...")
                    self._create_database()
                    # Retry pool creation
                    self.pool = pool.SimpleConnectionPool(
                        minconn=1,
                        maxconn=self.pool_size,
                        dbname=self.dbname,
                        user=self.user,
                        password=self.password,
                        host=self.host,
                        port=self.port,
                    )
                else:
                    raise

        # Acquire connection from pool if not already connected
        if not self.connection:
            try:
                self.connection = self.pool.getconn()
                self.logger.debug(f"Acquired connection from pool: {self.connection}")
            except OperationalError as e:
                raise RuntimeError(f"Error acquiring pooled connection: {e}")

    def close_connection(self) -> None:
        """
        Return the connection to the pool instead of closing it.

        This allows the connection to be reused by other operations.
        """
        if self.connection and hasattr(self, "pool") and self.pool:
            self.pool.putconn(self.connection)
            self.connection = None
            self.logger.debug("Returned connection to pool")

    def close_pool(self) -> None:
        """
        Close all connections in the pool.

        This should only be called when shutting down the application.
        """
        if hasattr(self, "pool") and self.pool:
            self.pool.closeall()
            self.pool = None
            self.logger.info(f"Closed connection pool '{self.pool_name}'")
