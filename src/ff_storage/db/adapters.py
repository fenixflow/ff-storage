"""
Database adapter abstraction for multi-backend support.

This module provides adapters that abstract the differences between
PostgreSQL, MySQL, and SQL Server connection pools, allowing ff-storage
to work seamlessly with different databases.
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union


class DatabaseAdapter(ABC):
    """
    Abstract base class for database adapters.

    Each adapter handles database-specific behaviors:
    - Parameter styles ($1 vs %(name)s vs ?)
    - RETURNING clause alternatives
    - Query builder selection
    """

    @abstractmethod
    def get_query_builder(self):
        """Return appropriate query builder for this database."""
        pass

    @abstractmethod
    def get_param_style(self) -> str:
        """
        Return parameter style for this database.

        Returns:
            'positional': $1, $2 (PostgreSQL)
            'named': %(name)s (MySQL)
            'qmark': ? (SQL Server)
        """
        pass

    @abstractmethod
    async def execute_with_returning(
        self, pool, query: str, params: Union[List, Dict], table: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a query with RETURNING-like behavior.

        Each database handles this differently:
        - PostgreSQL: Native RETURNING clause
        - MySQL: LAST_INSERT_ID() or separate SELECT
        - SQL Server: OUTPUT clause

        Args:
            pool: Database connection pool
            query: SQL query (may contain RETURNING clause)
            params: Query parameters
            table: Table name (needed for MySQL fallback)

        Returns:
            Dict of the returned/inserted row or None
        """
        pass

    @abstractmethod
    def convert_params(
        self, query: str, params: Union[List, Dict]
    ) -> tuple[str, Union[List, Dict]]:
        """
        Convert query and parameters to database-specific format.

        Args:
            query: SQL query with positional parameters ($1, $2)
            params: List of parameter values

        Returns:
            Tuple of (converted_query, converted_params)
        """
        pass


class PostgresAdapter(DatabaseAdapter):
    """Adapter for PostgreSQL using asyncpg."""

    def get_query_builder(self):
        """Return PostgreSQL query builder."""
        from ff_storage.db.query_builder import PostgresQueryBuilder

        return PostgresQueryBuilder()

    def get_param_style(self) -> str:
        """PostgreSQL uses positional parameters ($1, $2, etc.)."""
        return "positional"

    async def execute_with_returning(
        self, pool, query: str, params: Union[List, Dict], table: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Execute with native RETURNING support."""
        async with pool.acquire() as conn:
            if isinstance(params, dict):
                # Convert dict to list for asyncpg
                params = list(params.values())

            row = await conn.fetchrow(query, *params)
            return dict(row) if row else None

    def convert_params(
        self, query: str, params: Union[List, Dict]
    ) -> tuple[str, Union[List, Dict]]:
        """PostgreSQL doesn't need conversion (already uses $1, $2)."""
        return query, params


class MySQLAdapter(DatabaseAdapter):
    """Adapter for MySQL using aiomysql."""

    def get_query_builder(self):
        """Return MySQL query builder."""
        from ff_storage.db.query_builder import MySQLQueryBuilder

        return MySQLQueryBuilder()

    def get_param_style(self) -> str:
        """MySQL uses named parameters (%(name)s format)."""
        return "named"

    async def execute_with_returning(
        self, pool, query: str, params: Union[List, Dict], table: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute with LAST_INSERT_ID fallback for RETURNING.

        MySQL doesn't support RETURNING clause, so we:
        1. Execute the INSERT/UPDATE
        2. Get LAST_INSERT_ID() for inserts
        3. Execute a SELECT to get the full row
        """
        # Convert query and params to MySQL format
        query, params = self.convert_params(query, params)

        # Remove RETURNING clause if present
        if "RETURNING" in query.upper():
            query = re.sub(r"\s+RETURNING\s+\*\s*$", "", query, flags=re.IGNORECASE)

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Execute the main query
                await cursor.execute(query, params)

                # For INSERT, get the last insert ID
                if query.strip().upper().startswith("INSERT"):
                    last_id = cursor.lastrowid
                    if last_id and table:
                        # Fetch the inserted row
                        await cursor.execute(
                            f"SELECT * FROM {table} WHERE id = %(id)s", {"id": last_id}
                        )
                        row = await cursor.fetchone()
                        return row
                # For UPDATE/DELETE with RETURNING, we'd need the ID beforehand
                # This is a limitation that should be documented

                return None

    def convert_params(
        self, query: str, params: Union[List, Dict]
    ) -> tuple[str, Union[List, Dict]]:
        """Convert positional parameters to named for MySQL."""
        if isinstance(params, dict):
            # Already in correct format
            return query, params

        # Convert $1, $2 to %(p1)s, %(p2)s
        converted_params = {}
        for i, value in enumerate(params, 1):
            param_name = f"p{i}"
            query = query.replace(f"${i}", f"%({param_name})s")
            converted_params[param_name] = value

        return query, converted_params


class SQLServerAdapter(DatabaseAdapter):
    """Adapter for SQL Server using aioodbc."""

    def get_query_builder(self):
        """Return SQL Server query builder."""
        from ff_storage.db.query_builder import SQLServerQueryBuilder

        return SQLServerQueryBuilder()

    def get_param_style(self) -> str:
        """SQL Server uses question mark placeholders (?)."""
        return "qmark"

    async def execute_with_returning(
        self, pool, query: str, params: Union[List, Dict], table: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Execute with OUTPUT clause instead of RETURNING."""
        # Convert RETURNING to OUTPUT
        query = self.convert_returning_clause(query)

        # Convert params to SQL Server format
        query, params = self.convert_params(query, params)

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)

                # If OUTPUT clause present, fetch the result
                if "OUTPUT" in query.upper():
                    row = await cursor.fetchone()
                    if row and cursor.description:
                        columns = [col[0] for col in cursor.description]
                        return dict(zip(columns, row))

                return None

    def convert_params(
        self, query: str, params: Union[List, Dict]
    ) -> tuple[str, Union[List, Dict]]:
        """Convert positional parameters to question marks for SQL Server."""
        if isinstance(params, dict):
            params = list(params.values())

        # Replace $1, $2 with ?
        for i in range(len(params), 0, -1):
            query = query.replace(f"${i}", "?")

        return query, params

    def convert_returning_clause(self, query: str) -> str:
        """Convert PostgreSQL RETURNING clause to SQL Server OUTPUT."""
        # Pattern to match RETURNING clause
        returning_pattern = r"\s+RETURNING\s+\*\s*$"

        if "INSERT" in query.upper():
            # For INSERT, place OUTPUT before VALUES
            query = re.sub(
                r"(VALUES\s*\([^)]+\))\s+RETURNING\s+\*",
                r"OUTPUT INSERTED.* \1",
                query,
                flags=re.IGNORECASE,
            )
        elif "UPDATE" in query.upper():
            # For UPDATE, place OUTPUT after SET clause
            query = re.sub(returning_pattern, " OUTPUT INSERTED.*", query, flags=re.IGNORECASE)
        elif "DELETE" in query.upper():
            # For DELETE, place OUTPUT after DELETE FROM
            query = re.sub(returning_pattern, " OUTPUT DELETED.*", query, flags=re.IGNORECASE)

        return query


def detect_adapter(pool) -> DatabaseAdapter:
    """
    Automatically detect database type from pool and return appropriate adapter.

    Handles both raw driver pools (asyncpg, aiomysql, aioodbc) and wrapper
    classes (PostgresPool, MySQLPool) that have a .pool attribute.

    Args:
        pool: Database connection pool (raw or wrapped)

    Returns:
        Appropriate DatabaseAdapter instance

    Raises:
        ValueError: If pool type cannot be determined
    """
    # Unwrap wrapper classes (PostgresPool, MySQLPool, etc.)
    # These wrappers have a .pool attribute containing the actual driver pool
    actual_pool = pool
    if hasattr(pool, "pool") and pool.pool is not None:
        actual_pool = pool.pool

    # Get module name from the actual pool
    pool_module = (
        actual_pool.__module__ if hasattr(actual_pool, "__module__") else str(type(actual_pool))
    )

    # Check for raw driver pools (after unwrapping or direct usage)
    if "asyncpg" in pool_module:
        return PostgresAdapter()
    elif "aiomysql" in pool_module:
        return MySQLAdapter()
    elif "aioodbc" in pool_module:
        return SQLServerAdapter()
    # Check for wrapper classes (before connect() when .pool is None)
    elif "ff_storage.db.connections.postgres" in pool_module:
        return PostgresAdapter()
    elif "ff_storage.db.connections.mysql" in pool_module:
        return MySQLAdapter()
    else:
        raise ValueError(
            f"Unsupported database pool type: {pool_module}. "
            f"Supported: asyncpg, aiomysql, aioodbc, PostgresPool, MySQLPool"
        )
