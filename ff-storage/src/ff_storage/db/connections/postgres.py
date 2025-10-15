"""
PostgreSQL implementation of the SQL base class.
Provides both direct connections and async connection pooling.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2 import DatabaseError, OperationalError

from ..sql import SQL


@dataclass
class PostgresBase(SQL):
    """
    Base class for PostgreSQL operations, inheriting from SQL.

    This class provides core methods for executing queries and transactions.
    It does not automatically close connections, allowing the application
    to manage the connection lifecycle when required.
    """

    db_type = "postgres"

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
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()

                # Convert to dicts if requested
                if as_dict and cursor.description:
                    columns = [col[0] for col in cursor.description]
                    return [dict(zip(columns, row)) for row in results]

                return results
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
class PostgresPool:
    """
    Async PostgreSQL connection pool using asyncpg.

    This provides a high-performance async connection pool for PostgreSQL,
    suitable for FastAPI and other async Python applications.

    Pool handles connection acquisition internally - users just call fetch/execute methods.

    :param dbname: Database name.
    :param user: Database username.
    :param password: Database password.
    :param host: Database host.
    :param port: Database port.
    :param min_size: Minimum number of connections in the pool (default: 10).
    :param max_size: Maximum number of connections in the pool (default: 20).
    """

    dbname: str
    user: str
    password: str
    host: str
    port: int = 5432
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
            import asyncpg

            self.pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.dbname,
                min_size=self.min_size,
                max_size=self.max_size,
            )
            self.logger.info(
                f"Created asyncpg pool for {self.dbname} (min={self.min_size}, max={self.max_size})"
            )
        except Exception as e:
            self.logger.error(f"Failed to create asyncpg pool: {e}")
            raise RuntimeError(f"Error creating async pool: {e}")

    async def disconnect(self) -> None:
        """
        Close the connection pool.

        Call once at application shutdown (e.g., FastAPI shutdown event).
        """
        if self.pool:
            await self.pool.close()
            self.pool = None
            self.logger.info("Closed asyncpg connection pool")

    async def fetch_one(self, query: str, *args, as_dict: bool = True):
        """
        Fetch single row from database.

        Pool handles connection acquisition internally.

        :param query: SQL query (use $1, $2 for parameters).
        :param args: Query parameters.
        :param as_dict: If True, return dict. If False, return tuple.
        :return: Single row as dict (default) or tuple, or None if no results.
        """
        if not self.pool:
            raise RuntimeError("Pool not connected. Call await pool.connect() first.")

        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(query, *args)
            if result is None:
                return None
            if as_dict:
                return dict(result)
            else:
                return tuple(result)

    async def fetch_all(self, query: str, *args, as_dict: bool = True):
        """
        Fetch all rows from database.

        Pool handles connection acquisition internally.

        :param query: SQL query (use $1, $2 for parameters).
        :param args: Query parameters.
        :param as_dict: If True, return list of dicts. If False, return list of tuples.
        :return: List of dicts (default) or tuples.
        """
        if not self.pool:
            raise RuntimeError("Pool not connected. Call await pool.connect() first.")

        async with self.pool.acquire() as conn:
            results = await conn.fetch(query, *args)
            if as_dict:
                return [dict(record) for record in results]
            else:
                return [tuple(record) for record in results]

    async def execute(self, query: str, *args):
        """
        Execute query without returning results (INSERT, UPDATE, DELETE).

        Pool handles connection acquisition internally.

        :param query: SQL query (use $1, $2 for parameters).
        :param args: Query parameters.
        :return: Status string (e.g., "INSERT 0 1").
        """
        if not self.pool:
            raise RuntimeError("Pool not connected. Call await pool.connect() first.")

        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def execute_many(self, query: str, args_list: list):
        """
        Execute query with multiple parameter sets (batch operation).

        :param query: SQL query (use $1, $2 for parameters).
        :param args_list: List of argument tuples.
        """
        if not self.pool:
            raise RuntimeError("Pool not connected. Call await pool.connect() first.")

        async with self.pool.acquire() as conn:
            await conn.executemany(query, args_list)
