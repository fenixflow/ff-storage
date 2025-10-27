"""
PostgreSQL implementation of the SQL base class.
Provides both direct connections and async connection pooling with enhanced resilience.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2 import DatabaseError, OperationalError

from ...exceptions import (
    ConnectionFailure,
    ConnectionPoolExhausted,
    QueryTimeout,
)
from ...health import HealthCheckResult, HealthStatus
from ...utils.metrics import async_timer, get_global_collector, timer
from ...utils.retry import (
    CircuitBreaker,
    exponential_backoff,
    retry,
    retry_async,
)
from ...utils.validation import validate_query
from ..sql import SQL


@dataclass
class PostgresBase(SQL):
    """
    Base class for PostgreSQL operations, inheriting from SQL.

    This class provides core methods for executing queries and transactions
    with enhanced resilience, monitoring, and security features.
    """

    db_type = "postgres"

    # Additional configuration
    query_timeout: int = 30000  # 30 seconds in milliseconds
    idle_timeout: int = 60000  # 60 seconds in milliseconds
    validate_queries: bool = True  # Enable query validation
    collect_metrics: bool = True  # Enable metrics collection

    # Internal
    _metrics_collector: Optional[Any] = field(default=None, init=False)
    _circuit_breaker: Optional[CircuitBreaker] = field(default=None, init=False)

    def __post_init__(self):
        """Initialize metrics and circuit breaker after dataclass init."""
        if self.collect_metrics:
            self._metrics_collector = get_global_collector()

        # Create circuit breaker for this connection
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            expected_exception=(DatabaseError, OperationalError),
            name=f"postgres_{self.dbname}",
        )

    def read_query(
        self, query: str, params: Optional[Dict[str, Any]] = None, as_dict: bool = True
    ) -> List[Any]:
        """
        Execute a read-only SQL query and fetch all rows with enhanced monitoring.

        :param query: The SELECT SQL query.
        :param params: Optional dictionary of query parameters.
        :param as_dict: If True, return list of dicts. If False, return list of tuples.
        :return: A list of dicts (default) or tuples representing the query results.
        :raises ConnectionFailure: If connection fails.
        :raises QueryTimeout: If query exceeds timeout.
        """
        # Validate query if enabled
        if self.validate_queries:
            try:
                validate_query(query, params)
            except Exception as e:
                self.logger.warning(f"Query validation failed: {e}")

        if not self.connection:
            self.connect()

        start_time = time.perf_counter()
        rows_affected = 0
        success = False
        error = None

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                rows_affected = len(results) if results else 0

                # Convert to dicts if requested
                if as_dict and cursor.description:
                    columns = [col[0] for col in cursor.description]
                    results = [dict(zip(columns, row)) for row in results]

                success = True
                return results

        except DatabaseError as e:
            error = str(e)
            self.logger.error(f"Database query error: {e}", exc_info=True)
            if "timeout" in str(e).lower():
                raise QueryTimeout(query, self.query_timeout / 1000)
            return []

        finally:
            # Record metrics
            if self.collect_metrics and self._metrics_collector:
                duration = time.perf_counter() - start_time
                self._metrics_collector.record_query(
                    query=query,
                    duration=duration,
                    rows_affected=rows_affected,
                    success=success,
                    error=error,
                    connection_id=f"{self.host}:{self.port}/{self.dbname}",
                )

    @retry(max_attempts=3, delay=exponential_backoff(base_delay=0.5), exceptions=(DatabaseError,))
    def execute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Execute a non-returning SQL statement with retry logic and monitoring.

        :param query: The SQL statement.
        :param params: Optional dictionary of query parameters.
        :param context: Optional context for validation (e.g., trusted_source=True).
        :raises ConnectionFailure: If connection fails.
        :raises QueryTimeout: If query exceeds timeout.
        """
        # Validate query if enabled
        if self.validate_queries:
            try:
                validate_query(query, params, context)
            except Exception as e:
                self.logger.warning(f"Query validation failed: {e}")

        if not self.connection:
            self.connect()

        with timer("postgres.execute"):
            try:
                with self.connection.cursor() as cursor:
                    cursor.execute(query, params)
                    cursor.rowcount  # Available if needed, not currently used
                    self.connection.commit()

                    # Record metrics
                    if self.collect_metrics and self._metrics_collector:
                        self._metrics_collector.increment("postgres.execute.success")

            except Exception as e:
                self.connection.rollback()
                if self.collect_metrics and self._metrics_collector:
                    self._metrics_collector.increment("postgres.execute.failed")

                if "timeout" in str(e).lower():
                    raise QueryTimeout(query, self.query_timeout / 1000)
                raise ConnectionFailure(self.host, self.port, self.dbname, 1, str(e))

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

    @retry(
        max_attempts=3, delay=exponential_backoff(base_delay=1.0), exceptions=(OperationalError,)
    )
    def connect(self) -> None:
        """
        Establish a direct connection with retry logic and timeout configuration.

        If the database does not exist, attempts to create it and then reconnect.

        :raises ConnectionFailure: If connecting fails after retries.
        """
        if self.connection:
            return  # Connection is already established

        try:
            # Use circuit breaker for connection attempts
            def _connect():
                return psycopg2.connect(
                    dbname=self.dbname,
                    user=self.user,
                    password=self.password,
                    host=self.host,
                    port=self.port,
                    connect_timeout=10,  # 10 second connection timeout
                    options=f"-c statement_timeout={self.query_timeout} "
                    f"-c idle_in_transaction_session_timeout={self.idle_timeout}",
                )

            self.connection = self._circuit_breaker.call(_connect)

            # Set autocommit for DDL operations
            self.connection.autocommit = False

            self.logger.info(f"Connected to PostgreSQL database: {self.dbname}")

            # Record successful connection
            if self.collect_metrics and self._metrics_collector:
                self._metrics_collector.increment("postgres.connections.success")

        except OperationalError as e:
            if "does not exist" in str(e):
                self.logger.info(f"Database {self.dbname} does not exist, creating...")
                self._create_database()
                self.connect()
            else:
                if self.collect_metrics and self._metrics_collector:
                    self._metrics_collector.increment("postgres.connections.failed")
                raise ConnectionFailure(self.host, self.port, self.dbname, 3, str(e))


@dataclass
class PostgresPool:
    """
    Async PostgreSQL connection pool with enhanced resilience and monitoring.

    This provides a high-performance async connection pool for PostgreSQL,
    suitable for FastAPI and other async Python applications.

    Features:
    - Automatic reconnection with exponential backoff
    - Circuit breaker protection
    - Query timeout configuration
    - Metrics collection
    - Health check support
    - Pool warmup on startup

    :param dbname: Database name.
    :param user: Database username.
    :param password: Database password.
    :param host: Database host.
    :param port: Database port.
    :param min_size: Minimum number of connections in the pool (default: 10).
    :param max_size: Maximum number of connections in the pool (default: 20).
    :param query_timeout: Query timeout in milliseconds (default: 30000).
    :param pool_recycle: Time in seconds to recycle connections (default: 3600).
    :param validate_queries: Enable query validation (default: True).
    :param collect_metrics: Enable metrics collection (default: True).
    """

    dbname: str
    user: str
    password: str
    host: str
    port: int = 5432
    min_size: int = 10
    max_size: int = 20

    # Timeouts and configuration
    query_timeout: int = 30000  # 30 seconds in milliseconds
    pool_recycle: int = 3600  # 1 hour
    connection_timeout: int = 10  # 10 seconds
    validate_queries: bool = True
    collect_metrics: bool = True
    max_inactive_connection_lifetime: float = 300.0  # 5 minutes

    # Pool instance
    pool: Optional[Any] = None

    # Monitoring
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    _metrics_collector: Optional[Any] = field(default=None, init=False)
    _circuit_breaker: Optional[CircuitBreaker] = field(default=None, init=False)
    _last_pool_check: float = field(default=0, init=False)

    def __post_init__(self):
        """Initialize metrics and circuit breaker."""
        if self.collect_metrics:
            self._metrics_collector = get_global_collector()

        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            expected_exception=Exception,
            name=f"postgres_pool_{self.dbname}",
        )

    @retry_async(max_attempts=3, delay=exponential_backoff(base_delay=1.0), exceptions=(Exception,))
    async def connect(self) -> None:
        """
        Create async connection pool with retry logic and pool warmup.

        Call once at application startup (e.g., FastAPI startup event).

        :raises ConnectionFailure: If pool creation fails after retries.
        """
        if self.pool:
            return  # Pool already created

        try:
            import asyncpg

            # Create pool with circuit breaker protection
            async def _create_pool():
                return await asyncpg.create_pool(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=self.dbname,
                    min_size=self.min_size,
                    max_size=self.max_size,
                    timeout=self.connection_timeout,
                    command_timeout=self.query_timeout / 1000,  # Convert to seconds
                    max_inactive_connection_lifetime=self.max_inactive_connection_lifetime,
                    server_settings={
                        "jit": "off",  # Disable JIT for more predictable performance
                        "statement_timeout": str(self.query_timeout),
                        "idle_in_transaction_session_timeout": str(self.query_timeout * 2),
                    },
                )

            self.pool = await self._circuit_breaker.async_call(_create_pool)

            self.logger.info(
                f"Created asyncpg pool for {self.dbname} "
                f"(min={self.min_size}, max={self.max_size}, timeout={self.query_timeout}ms)"
            )

            # Warm up the pool by acquiring minimum connections
            await self._warmup_pool()

            # Record metrics
            if self.collect_metrics and self._metrics_collector:
                self._metrics_collector.increment("postgres.pool.created")
                self._record_pool_metrics()

        except Exception as e:
            self.logger.error(f"Failed to create asyncpg pool: {e}", exc_info=True)
            if self.collect_metrics and self._metrics_collector:
                self._metrics_collector.increment("postgres.pool.creation_failed")
            raise ConnectionFailure(self.host, self.port, self.dbname, 3, str(e))

    async def _warmup_pool(self):
        """Warm up the connection pool by pre-establishing minimum connections."""
        self.logger.info(f"Warming up connection pool with {self.min_size} connections...")
        warmup_tasks = []

        async def test_connection():
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")

        # Create tasks to warm up to min_size
        for _ in range(self.min_size):
            warmup_tasks.append(test_connection())

        # Execute warmup with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*warmup_tasks, return_exceptions=True), timeout=30
            )
            self.logger.info("Pool warmup completed successfully")
        except asyncio.TimeoutError:
            self.logger.warning("Pool warmup timed out, continuing with partial warmup")

    def _record_pool_metrics(self):
        """Record connection pool metrics."""
        if not self.pool or not self.collect_metrics or not self._metrics_collector:
            return

        try:
            # Record pool statistics
            self._metrics_collector.record_pool_metrics(
                pool_size=self.pool._size if hasattr(self.pool, "_size") else self.max_size,
                active=len(self.pool._holders) if hasattr(self.pool, "_holders") else 0,
                idle=len(self.pool._free) if hasattr(self.pool, "_free") else 0,
                waiting=self.pool._queue.qsize() if hasattr(self.pool, "_queue") else 0,
                total_created=(
                    self.pool._created_connections
                    if hasattr(self.pool, "_created_connections")
                    else 0
                ),
                total_closed=(
                    self.pool._closed_connections
                    if hasattr(self.pool, "_closed_connections")
                    else 0
                ),
            )
        except Exception as e:
            self.logger.debug(f"Failed to record pool metrics: {e}")

    async def disconnect(self) -> None:
        """
        Close the connection pool.

        Call once at application shutdown (e.g., FastAPI shutdown event).
        """
        if self.pool:
            await self.pool.close()
            self.pool = None
            self.logger.info("Closed asyncpg connection pool")

    @retry_async(max_attempts=2, delay=exponential_backoff(base_delay=0.5), exceptions=(Exception,))
    async def fetch_one(self, query: str, *args, as_dict: bool = True):
        """
        Fetch single row with monitoring and retry logic.

        :param query: SQL query (use $1, $2 for parameters).
        :param args: Query parameters.
        :param as_dict: If True, return dict. If False, return tuple.
        :return: Single row as dict (default) or tuple, or None if no results.
        :raises ConnectionPoolExhausted: If pool has no available connections.
        :raises QueryTimeout: If query exceeds timeout.
        """
        if not self.pool:
            raise ConnectionPoolExhausted(self.max_size, self.connection_timeout)

        # Validate query if enabled
        if self.validate_queries:
            try:
                validate_query(query, args)
            except Exception as e:
                self.logger.warning(f"Query validation failed: {e}")

        # Record metrics periodically
        if time.time() - self._last_pool_check > 10:  # Every 10 seconds
            self._record_pool_metrics()
            self._last_pool_check = time.time()

        start_time = time.perf_counter()
        success = False
        error = None

        try:
            async with self.pool.acquire(timeout=self.connection_timeout) as conn:
                result = await conn.fetchrow(query, *args)

                success = True

                if result is None:
                    return None
                if as_dict:
                    return dict(result)
                else:
                    return tuple(result)

        except asyncio.TimeoutError:
            error = "Pool acquisition timeout"
            raise ConnectionPoolExhausted(self.max_size, self.connection_timeout)
        except Exception as e:
            error = str(e)
            if "timeout" in str(e).lower():
                raise QueryTimeout(query, self.query_timeout / 1000)
            raise
        finally:
            # Record query metrics
            if self.collect_metrics and self._metrics_collector:
                duration = time.perf_counter() - start_time
                self._metrics_collector.record_query(
                    query=query,
                    duration=duration,
                    rows_affected=1 if success and result else 0,
                    success=success,
                    error=error,
                    connection_id=f"pool_{self.host}:{self.port}/{self.dbname}",
                )

    @retry_async(max_attempts=2, delay=exponential_backoff(base_delay=0.5), exceptions=(Exception,))
    async def fetch_all(self, query: str, *args, as_dict: bool = True):
        """
        Fetch all rows with monitoring and retry logic.

        :param query: SQL query (use $1, $2 for parameters).
        :param args: Query parameters.
        :param as_dict: If True, return list of dicts. If False, return list of tuples.
        :return: List of dicts (default) or tuples.
        :raises ConnectionPoolExhausted: If pool has no available connections.
        :raises QueryTimeout: If query exceeds timeout.
        """
        if not self.pool:
            raise ConnectionPoolExhausted(self.max_size, self.connection_timeout)

        # Validate query if enabled
        if self.validate_queries:
            try:
                validate_query(query, args)
            except Exception as e:
                self.logger.warning(f"Query validation failed: {e}")

        start_time = time.perf_counter()
        success = False
        error = None
        rows_affected = 0

        try:
            async with async_timer("postgres_pool.fetch_all"):
                async with self.pool.acquire(timeout=self.connection_timeout) as conn:
                    results = await conn.fetch(query, *args)

                    rows_affected = len(results)
                    success = True

                    if as_dict:
                        return [dict(record) for record in results]
                    else:
                        return [tuple(record) for record in results]

        except asyncio.TimeoutError:
            error = "Pool acquisition timeout"
            raise ConnectionPoolExhausted(self.max_size, self.connection_timeout)
        except Exception as e:
            error = str(e)
            if "timeout" in str(e).lower():
                raise QueryTimeout(query, self.query_timeout / 1000)
            raise
        finally:
            # Record query metrics
            if self.collect_metrics and self._metrics_collector:
                duration = time.perf_counter() - start_time
                self._metrics_collector.record_query(
                    query=query,
                    duration=duration,
                    rows_affected=rows_affected,
                    success=success,
                    error=error,
                    connection_id=f"pool_{self.host}:{self.port}/{self.dbname}",
                )

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
            raise ConnectionPoolExhausted(self.max_size, self.connection_timeout)

        async with self.pool.acquire(timeout=self.connection_timeout) as conn:
            await conn.executemany(query, args_list)

    def acquire(self, timeout: Optional[float] = None):
        """
        Acquire a connection from the pool.

        This method provides compatibility for temporal strategies that expect
        to acquire connections directly. Returns a context manager for the
        underlying asyncpg pool.

        :param timeout: Optional timeout in seconds (defaults to connection_timeout).
        :return: Context manager that yields an asyncpg connection.

        Usage:
            async with db_pool.acquire() as conn:
                result = await conn.fetchrow(query, *args)
        """
        if not self.pool:
            raise ConnectionPoolExhausted(self.max_size, self.connection_timeout)

        timeout = timeout or self.connection_timeout
        return self.pool.acquire(timeout=timeout)

    async def check_health(self) -> HealthCheckResult:
        """
        Perform health check on the connection pool.

        :return: HealthCheckResult with pool status and metrics.
        """
        start_time = time.perf_counter()

        try:
            if not self.pool:
                return HealthCheckResult(
                    name=f"postgres_pool_{self.dbname}",
                    status=HealthStatus.UNHEALTHY,
                    message="Connection pool not initialized",
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                    error="Pool is None",
                )

            # Try a simple query with timeout
            result = await asyncio.wait_for(
                self.fetch_one("SELECT 1 as health_check", as_dict=True), timeout=5.0
            )

            if result and result.get("health_check") == 1:
                # Get pool statistics
                details = {
                    "pool_size": self.max_size,
                    "min_size": self.min_size,
                    "circuit_breaker_state": self._circuit_breaker.state.value,
                }

                # Try to get actual pool stats
                if hasattr(self.pool, "_size"):
                    details["actual_size"] = self.pool._size
                if hasattr(self.pool, "_free"):
                    details["free_connections"] = len(self.pool._free)
                if hasattr(self.pool, "_holders"):
                    details["used_connections"] = len(self.pool._holders)

                    # Calculate utilization
                    used = len(self.pool._holders)
                    size = self.max_size
                    utilization = (used / size) * 100 if size > 0 else 0
                    details["utilization_percent"] = round(utilization, 2)

                    # Determine status based on utilization
                    if utilization > 90:
                        status = HealthStatus.DEGRADED
                        message = f"Pool utilization high: {utilization:.1f}%"
                    elif self._circuit_breaker.is_open:
                        status = HealthStatus.DEGRADED
                        message = "Circuit breaker is open"
                    else:
                        status = HealthStatus.HEALTHY
                        message = "Database pool healthy"
                else:
                    status = HealthStatus.HEALTHY
                    message = "Database pool healthy"

                return HealthCheckResult(
                    name=f"postgres_pool_{self.dbname}",
                    status=status,
                    message=message,
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                    details=details,
                )
            else:
                return HealthCheckResult(
                    name=f"postgres_pool_{self.dbname}",
                    status=HealthStatus.UNHEALTHY,
                    message="Health check query returned unexpected result",
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                    error=f"Unexpected result: {result}",
                )

        except asyncio.TimeoutError:
            return HealthCheckResult(
                name=f"postgres_pool_{self.dbname}",
                status=HealthStatus.UNHEALTHY,
                message="Health check query timed out",
                duration_ms=(time.perf_counter() - start_time) * 1000,
                error="Query timeout after 5 seconds",
            )
        except Exception as e:
            return HealthCheckResult(
                name=f"postgres_pool_{self.dbname}",
                status=HealthStatus.UNHEALTHY,
                message="Database health check failed",
                duration_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )
