"""
Unit tests for database adapter abstraction.

These tests ensure that ff-storage can work with different database backends
(PostgreSQL, MySQL, SQL Server) through a unified adapter interface.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

from ff_storage.db.adapters import (
    PostgresAdapter,
    MySQLAdapter,
    SQLServerAdapter,
    detect_adapter,
    UniversalPool,
)
from ff_storage.db.query_builder import (
    PostgresQueryBuilder,
    MySQLQueryBuilder,
    SQLServerQueryBuilder,
)


class TestDatabaseAdapterDetection:
    """Test automatic detection of database type from pool."""

    def test_detect_postgres_pool(self):
        """Test detection of PostgreSQL asyncpg pool."""
        # Mock asyncpg pool
        pool = MagicMock()
        pool.__module__ = "asyncpg.pool"

        adapter = detect_adapter(pool)
        assert isinstance(adapter, PostgresAdapter)
        assert isinstance(adapter.get_query_builder(), PostgresQueryBuilder)

    def test_detect_mysql_pool(self):
        """Test detection of MySQL aiomysql pool."""
        # Mock aiomysql pool
        pool = MagicMock()
        pool.__module__ = "aiomysql.pool"

        adapter = detect_adapter(pool)
        assert isinstance(adapter, MySQLAdapter)
        assert isinstance(adapter.get_query_builder(), MySQLQueryBuilder)

    def test_detect_sqlserver_pool(self):
        """Test detection of SQL Server aioodbc pool."""
        # Mock aioodbc pool
        pool = MagicMock()
        pool.__module__ = "aioodbc.pool"

        adapter = detect_adapter(pool)
        assert isinstance(adapter, SQLServerAdapter)
        assert isinstance(adapter.get_query_builder(), SQLServerQueryBuilder)

    def test_detect_unknown_pool_raises(self):
        """Test that unknown pool type raises appropriate error."""
        pool = MagicMock()
        pool.__module__ = "unknown.pool"

        with pytest.raises(ValueError, match="Unsupported database pool"):
            detect_adapter(pool)


class TestPostgresAdapter:
    """Test PostgreSQL adapter functionality."""

    def test_param_style(self):
        """Test PostgreSQL uses positional parameters."""
        adapter = PostgresAdapter()
        assert adapter.get_param_style() == "positional"  # $1, $2, etc.

    @pytest.mark.asyncio
    async def test_execute_with_returning(self):
        """Test PostgreSQL RETURNING clause execution."""
        adapter = PostgresAdapter()
        pool = MagicMock()  # Use regular MagicMock for pool
        conn = AsyncMock()

        # Configure pool.acquire() to return an async context manager
        acquire_cm = MagicMock()
        acquire_cm.__aenter__ = AsyncMock(return_value=conn)
        acquire_cm.__aexit__ = AsyncMock(return_value=None)
        pool.acquire.return_value = acquire_cm

        query = "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING *"
        params = ["John", "john@test.com"]

        expected_row = {"id": uuid4(), "name": "John", "email": "john@test.com"}
        conn.fetchrow.return_value = expected_row

        result = await adapter.execute_with_returning(pool, query, params)

        assert result == expected_row
        conn.fetchrow.assert_called_once_with(query, *params)

    def test_convert_params(self):
        """Test PostgreSQL parameter conversion (no-op for positional)."""
        adapter = PostgresAdapter()
        query = "SELECT * FROM users WHERE id = $1 AND name = $2"
        params = [123, "John"]

        converted_query, converted_params = adapter.convert_params(query, params)

        assert converted_query == query  # No conversion needed
        assert converted_params == params


class TestMySQLAdapter:
    """Test MySQL adapter functionality."""

    def test_param_style(self):
        """Test MySQL uses named parameters."""
        adapter = MySQLAdapter()
        assert adapter.get_param_style() == "named"  # %(name)s format

    @pytest.mark.asyncio
    async def test_execute_with_returning(self):
        """Test MySQL INSERT with LAST_INSERT_ID fallback."""
        adapter = MySQLAdapter()
        pool = MagicMock()  # Use regular MagicMock for pool
        conn = MagicMock()
        cursor = AsyncMock()

        # Configure pool.acquire() to return an async context manager
        acquire_cm = MagicMock()
        acquire_cm.__aenter__ = AsyncMock(return_value=conn)
        acquire_cm.__aexit__ = AsyncMock(return_value=None)
        pool.acquire.return_value = acquire_cm

        # Configure conn.cursor() to return an async context manager
        cursor_cm = MagicMock()
        cursor_cm.__aenter__ = AsyncMock(return_value=cursor)
        cursor_cm.__aexit__ = AsyncMock(return_value=None)
        conn.cursor.return_value = cursor_cm

        query = "INSERT INTO users (name, email) VALUES (%(p1)s, %(p2)s)"
        params = {"p1": "John", "p2": "john@test.com"}

        # MySQL doesn't support RETURNING, use LAST_INSERT_ID
        new_id = 42
        cursor.lastrowid = new_id
        cursor.fetchone.return_value = {"id": new_id, "name": "John", "email": "john@test.com"}

        result = await adapter.execute_with_returning(pool, query, params, table="users")

        assert result["id"] == new_id
        # Should execute INSERT, then SELECT by ID
        assert cursor.execute.call_count == 2

    def test_convert_params_positional_to_named(self):
        """Test conversion from positional to named parameters for MySQL."""
        adapter = MySQLAdapter()
        query = "SELECT * FROM users WHERE id = $1 AND name = $2"
        params = [123, "John"]

        converted_query, converted_params = adapter.convert_params(query, params)

        assert converted_query == "SELECT * FROM users WHERE id = %(p1)s AND name = %(p2)s"
        assert converted_params == {"p1": 123, "p2": "John"}


class TestSQLServerAdapter:
    """Test SQL Server adapter functionality."""

    def test_param_style(self):
        """Test SQL Server uses placeholder parameters."""
        adapter = SQLServerAdapter()
        assert adapter.get_param_style() == "qmark"  # ? placeholders

    @pytest.mark.asyncio
    async def test_execute_with_returning(self):
        """Test SQL Server OUTPUT clause execution."""
        adapter = SQLServerAdapter()
        pool = MagicMock()  # Use regular MagicMock for pool
        conn = MagicMock()
        cursor = MagicMock()

        # Configure pool.acquire() to return an async context manager
        acquire_cm = MagicMock()
        acquire_cm.__aenter__ = AsyncMock(return_value=conn)
        acquire_cm.__aexit__ = AsyncMock(return_value=None)
        pool.acquire.return_value = acquire_cm

        # Configure conn.cursor() to return an async context manager
        cursor_cm = MagicMock()
        cursor_cm.__aenter__ = AsyncMock(return_value=cursor)
        cursor_cm.__aexit__ = AsyncMock(return_value=None)
        conn.cursor.return_value = cursor_cm

        # SQL Server uses OUTPUT instead of RETURNING
        query = "INSERT INTO users (name, email) OUTPUT INSERTED.* VALUES (?, ?)"
        params = ["John", "john@test.com"]

        expected_row = {"id": uuid4(), "name": "John", "email": "john@test.com"}
        # SQL Server cursor returns tuples, not dicts
        cursor.fetchone = AsyncMock(
            return_value=(expected_row["id"], expected_row["name"], expected_row["email"])
        )
        cursor.description = [("id",), ("name",), ("email",)]
        cursor.execute = AsyncMock()

        result = await adapter.execute_with_returning(pool, query, params)

        assert result == expected_row
        cursor.execute.assert_called_once_with(query, params)

    def test_convert_params_positional_to_qmark(self):
        """Test conversion from positional to qmark parameters for SQL Server."""
        adapter = SQLServerAdapter()
        query = "SELECT * FROM users WHERE id = $1 AND name = $2"
        params = [123, "John"]

        converted_query, converted_params = adapter.convert_params(query, params)

        assert converted_query == "SELECT * FROM users WHERE id = ? AND name = ?"
        assert converted_params == [123, "John"]

    def test_convert_returning_to_output(self):
        """Test conversion of RETURNING clause to OUTPUT for SQL Server."""
        adapter = SQLServerAdapter()
        query = """
            UPDATE users
            SET name = ?, email = ?
            WHERE id = ?
            RETURNING *
        """

        converted = adapter.convert_returning_clause(query)

        assert "OUTPUT INSERTED.*" in converted
        assert "RETURNING" not in converted


class TestUniversalPool:
    """Test universal pool wrapper that abstracts database differences."""

    @pytest.mark.asyncio
    async def test_postgres_pool_operations(self):
        """Test operations with PostgreSQL pool."""
        # Mock asyncpg pool
        base_pool = MagicMock()
        base_pool.__module__ = "asyncpg.pool"
        conn = AsyncMock()

        # Configure pool.acquire() to return an async context manager
        acquire_cm = MagicMock()
        acquire_cm.__aenter__ = AsyncMock(return_value=conn)
        acquire_cm.__aexit__ = AsyncMock(return_value=None)
        base_pool.acquire.return_value = acquire_cm

        pool = UniversalPool(base_pool)

        # Test INSERT with RETURNING
        query = "INSERT INTO users (name) VALUES ($1) RETURNING *"
        params = ["John"]
        expected = {"id": uuid4(), "name": "John"}
        conn.fetchrow.return_value = expected

        result = await pool.execute_with_returning(query, params)
        assert result == expected

        # Test SELECT
        conn.fetch.return_value = [expected]
        results = await pool.fetch_all("SELECT * FROM users", [])
        assert results == [expected]

    @pytest.mark.asyncio
    async def test_mysql_pool_operations(self):
        """Test operations with MySQL pool."""
        # Mock aiomysql pool
        base_pool = MagicMock()
        base_pool.__module__ = "aiomysql.pool"
        conn = MagicMock()
        cursor = AsyncMock()

        # Configure pool.acquire() to return an async context manager
        acquire_cm = MagicMock()
        acquire_cm.__aenter__ = AsyncMock(return_value=conn)
        acquire_cm.__aexit__ = AsyncMock(return_value=None)
        base_pool.acquire.return_value = acquire_cm

        # Configure conn.cursor() to return an async context manager
        cursor_cm = MagicMock()
        cursor_cm.__aenter__ = AsyncMock(return_value=cursor)
        cursor_cm.__aexit__ = AsyncMock(return_value=None)
        conn.cursor.return_value = cursor_cm

        pool = UniversalPool(base_pool)

        # Test INSERT (MySQL doesn't support RETURNING)
        query = "INSERT INTO users (name) VALUES ($1)"
        params = ["John"]
        cursor.lastrowid = 42
        cursor.fetchone.return_value = {"id": 42, "name": "John"}

        result = await pool.execute_with_returning(query, params, table="users")
        assert result["id"] == 42

        # Query should be converted to MySQL format
        call_args = cursor.execute.call_args_list[0]
        assert "%(p1)s" in call_args[0][0]  # Named parameter

    @pytest.mark.asyncio
    async def test_sqlserver_pool_operations(self):
        """Test operations with SQL Server pool."""
        # Mock aioodbc pool
        base_pool = MagicMock()
        base_pool.__module__ = "aioodbc.pool"
        conn = MagicMock()
        cursor = MagicMock()

        # Configure pool.acquire() to return an async context manager
        acquire_cm = MagicMock()
        acquire_cm.__aenter__ = AsyncMock(return_value=conn)
        acquire_cm.__aexit__ = AsyncMock(return_value=None)
        base_pool.acquire.return_value = acquire_cm

        # Configure conn.cursor() to return an async context manager
        cursor_cm = MagicMock()
        cursor_cm.__aenter__ = AsyncMock(return_value=cursor)
        cursor_cm.__aexit__ = AsyncMock(return_value=None)
        conn.cursor.return_value = cursor_cm

        pool = UniversalPool(base_pool)

        # Test UPDATE with RETURNING (converted to OUTPUT)
        query = "UPDATE users SET name = $1 WHERE id = $2 RETURNING *"
        params = ["Jane", 42]
        expected = {"id": 42, "name": "Jane"}
        # SQL Server cursor returns tuples, not dicts
        cursor.fetchone = AsyncMock(return_value=(expected["id"], expected["name"]))
        cursor.description = [("id",), ("name",)]
        cursor.execute = AsyncMock()

        result = await pool.execute_with_returning(query, params)
        assert result == expected

        # Query should be converted to SQL Server format
        call_args = cursor.execute.call_args_list[0]
        executed_query = call_args[0][0]
        assert "?" in executed_query  # Placeholder parameter
        assert "OUTPUT" in executed_query  # OUTPUT clause instead of RETURNING

    @pytest.mark.asyncio
    async def test_universal_pool_preserves_original_interface(self):
        """Test that UniversalPool preserves the original pool's acquire() interface."""
        base_pool = MagicMock()
        base_pool.__module__ = "asyncpg.pool"

        # Configure pool.acquire() to return an async context manager
        conn = AsyncMock()
        acquire_cm = MagicMock()
        acquire_cm.__aenter__ = AsyncMock(return_value=conn)
        acquire_cm.__aexit__ = AsyncMock(return_value=None)
        base_pool.acquire.return_value = acquire_cm

        pool = UniversalPool(base_pool)

        # Should still have acquire() method for compatibility
        assert hasattr(pool, "acquire")

        # Test that acquire returns a connection
        async with pool.acquire() as test_conn:
            assert test_conn is conn


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
