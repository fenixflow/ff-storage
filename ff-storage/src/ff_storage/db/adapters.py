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

    Args:
        pool: Database connection pool

    Returns:
        Appropriate DatabaseAdapter instance

    Raises:
        ValueError: If pool type cannot be determined
    """
    pool_module = pool.__module__ if hasattr(pool, "__module__") else str(type(pool))

    if "asyncpg" in pool_module:
        return PostgresAdapter()
    elif "aiomysql" in pool_module:
        return MySQLAdapter()
    elif "aioodbc" in pool_module:
        return SQLServerAdapter()
    else:
        raise ValueError(
            f"Unsupported database pool type: {pool_module}. Supported: asyncpg, aiomysql, aioodbc"
        )


class UniversalPool:
    """
    Universal pool wrapper that abstracts database differences.

    This wrapper:
    - Auto-detects database type
    - Converts parameters to correct format
    - Handles RETURNING clause differences
    - Preserves original pool interface for compatibility
    """

    def __init__(self, pool):
        """
        Initialize universal pool wrapper.

        Args:
            pool: Original database connection pool
        """
        self.pool = pool
        self.adapter = detect_adapter(pool)

    def acquire(self):
        """
        Preserve original acquire() interface for compatibility.

        This allows UniversalPool to be used as drop-in replacement.
        """
        return self.pool.acquire()

    async def execute_with_returning(
        self, query: str, params: Union[List, Dict], table: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute query with RETURNING-like behavior across all databases.

        Args:
            query: SQL query (may contain RETURNING clause)
            params: Query parameters (list or dict)
            table: Table name (needed for MySQL)

        Returns:
            Dict of returned row or None
        """
        return await self.adapter.execute_with_returning(self.pool, query, params, table)

    async def fetch_all(self, query: str, params: Union[List, Dict]) -> List[Dict[str, Any]]:
        """
        Fetch all rows from query.

        Args:
            query: SELECT query
            params: Query parameters

        Returns:
            List of row dicts
        """
        query, params = self.adapter.convert_params(query, params)

        if self.adapter.get_param_style() == "positional":
            # PostgreSQL
            async with self.pool.acquire() as conn:
                if isinstance(params, list):
                    rows = await conn.fetch(query, *params)
                else:
                    rows = await conn.fetch(query, *list(params.values()))
                return [dict(row) for row in rows]
        elif self.adapter.get_param_style() == "named":
            # MySQL
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, params)
                    rows = await cursor.fetchall()
                    return rows
        else:
            # SQL Server
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, params)
                    rows = await cursor.fetchall()
                    if rows and cursor.description:
                        columns = [col[0] for col in cursor.description]
                        return [dict(zip(columns, row)) for row in rows]
                    return []

    async def fetch_one(self, query: str, params: Union[List, Dict]) -> Optional[Dict[str, Any]]:
        """
        Fetch single row from query.

        Args:
            query: SELECT query
            params: Query parameters

        Returns:
            Row dict or None
        """
        query, params = self.adapter.convert_params(query, params)

        if self.adapter.get_param_style() == "positional":
            # PostgreSQL
            async with self.pool.acquire() as conn:
                if isinstance(params, list):
                    row = await conn.fetchrow(query, *params)
                else:
                    row = await conn.fetchrow(query, *list(params.values()))
                return dict(row) if row else None
        elif self.adapter.get_param_style() == "named":
            # MySQL
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, params)
                    row = await cursor.fetchone()
                    return row
        else:
            # SQL Server
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, params)
                    row = await cursor.fetchone()
                    if row and cursor.description:
                        columns = [col[0] for col in cursor.description]
                        return dict(zip(columns, row))
                    return None
