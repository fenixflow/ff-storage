"""
Test async MySQL connection pool using aiomysql.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from ff_storage.db.connections.mysql import MySQLPool

# Mark all tests in this module as requiring MySQL
pytestmark = pytest.mark.mysql


@pytest.fixture
def pool_config():
    """Pool configuration for testing."""
    return {
        "dbname": "test_db",
        "user": "test_user",
        "password": "test_pass",
        "host": "localhost",
        "port": 3306,
        "min_size": 5,
        "max_size": 10,
    }


@pytest_asyncio.fixture
async def mock_aiomysql_pool():
    """Mock aiomysql pool."""
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = AsyncMock()

    # Create async context manager for pool.acquire()
    pool_context = AsyncMock()
    pool_context.__aenter__.return_value = mock_conn
    pool_context.__aexit__.return_value = None
    mock_pool.acquire.return_value = pool_context

    # Create async context manager for conn.cursor()
    cursor_context = AsyncMock()
    cursor_context.__aenter__.return_value = mock_cursor
    cursor_context.__aexit__.return_value = None
    mock_conn.cursor.return_value = cursor_context
    mock_conn.commit = AsyncMock()

    return mock_pool, mock_conn, mock_cursor


@pytest.mark.asyncio
async def test_pool_connect(pool_config):
    """Test pool connection creation."""
    pool = MySQLPool(**pool_config)

    with patch("aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_pool = AsyncMock()
        mock_create_pool.return_value = mock_pool
        await pool.connect()

        mock_create_pool.assert_called_once()
        assert pool.pool is not None


@pytest.mark.asyncio
async def test_pool_connect_already_connected(pool_config):
    """Test that connecting twice doesn't create a new pool."""
    pool = MySQLPool(**pool_config)

    with patch("aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_pool = AsyncMock()
        mock_create_pool.return_value = mock_pool
        await pool.connect()
        await pool.connect()  # Second call

        # Should only be called once
        mock_create_pool.assert_called_once()


@pytest.mark.asyncio
async def test_pool_disconnect(pool_config):
    """Test pool disconnection."""
    pool = MySQLPool(**pool_config)

    with patch("aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_pool = AsyncMock()
        # close() is not async in aiomysql, but wait_closed() is
        mock_pool.close = MagicMock()
        mock_pool.wait_closed = AsyncMock()
        mock_create_pool.return_value = mock_pool
        await pool.connect()
        await pool.disconnect()

        mock_pool.close.assert_called_once()
        mock_pool.wait_closed.assert_called_once()
        assert pool.pool is None


@pytest.mark.asyncio
async def test_fetch_one(pool_config, mock_aiomysql_pool):
    """Test fetch_one method."""
    pool = MySQLPool(**pool_config)
    mock_pool, mock_conn, mock_cursor = mock_aiomysql_pool

    pool.pool = mock_pool
    mock_cursor.fetchone.return_value = {"id": 1, "name": "test"}

    result = await pool.fetch_one("SELECT * FROM users WHERE id = %(id)s", {"id": 1})

    mock_cursor.execute.assert_called_once_with("SELECT * FROM users WHERE id = %(id)s", {"id": 1})
    mock_cursor.fetchone.assert_called_once()
    assert result == {"id": 1, "name": "test"}


@pytest.mark.asyncio
async def test_fetch_one_no_params(pool_config, mock_aiomysql_pool):
    """Test fetch_one without parameters."""
    pool = MySQLPool(**pool_config)
    mock_pool, mock_conn, mock_cursor = mock_aiomysql_pool

    pool.pool = mock_pool
    mock_cursor.fetchone.return_value = {"id": 1}

    result = await pool.fetch_one("SELECT * FROM users LIMIT 1")

    mock_cursor.execute.assert_called_once_with("SELECT * FROM users LIMIT 1", {})
    assert result == {"id": 1}


@pytest.mark.asyncio
async def test_fetch_one_no_pool(pool_config):
    """Test fetch_one raises error when pool not connected."""
    pool = MySQLPool(**pool_config)

    with pytest.raises(RuntimeError, match="Pool not connected"):
        await pool.fetch_one("SELECT * FROM users")


@pytest.mark.asyncio
async def test_fetch_all(pool_config, mock_aiomysql_pool):
    """Test fetch_all method."""
    pool = MySQLPool(**pool_config)
    mock_pool, mock_conn, mock_cursor = mock_aiomysql_pool

    pool.pool = mock_pool
    mock_cursor.fetchall.return_value = [
        {"id": 1, "name": "test1"},
        {"id": 2, "name": "test2"},
    ]

    result = await pool.fetch_all("SELECT * FROM users WHERE active = %(active)s", {"active": True})

    mock_cursor.execute.assert_called_once_with(
        "SELECT * FROM users WHERE active = %(active)s", {"active": True}
    )
    mock_cursor.fetchall.assert_called_once()
    assert len(result) == 2
    assert result[0] == {"id": 1, "name": "test1"}


@pytest.mark.asyncio
async def test_fetch_all_no_params(pool_config, mock_aiomysql_pool):
    """Test fetch_all without parameters."""
    pool = MySQLPool(**pool_config)
    mock_pool, mock_conn, mock_cursor = mock_aiomysql_pool

    pool.pool = mock_pool
    mock_cursor.fetchall.return_value = [{"id": 1, "name": "test"}]

    result = await pool.fetch_all("SELECT * FROM users")

    mock_cursor.execute.assert_called_once_with("SELECT * FROM users", {})
    assert len(result) == 1


@pytest.mark.asyncio
async def test_execute(pool_config, mock_aiomysql_pool):
    """Test execute method."""
    pool = MySQLPool(**pool_config)
    mock_pool, mock_conn, mock_cursor = mock_aiomysql_pool

    pool.pool = mock_pool
    mock_cursor.execute.return_value = 1  # Number of affected rows

    result = await pool.execute(
        "UPDATE users SET name = %(name)s WHERE id = %(id)s",
        {"name": "John", "id": 1},
    )

    mock_cursor.execute.assert_called_once_with(
        "UPDATE users SET name = %(name)s WHERE id = %(id)s",
        {"name": "John", "id": 1},
    )
    mock_conn.commit.assert_called_once()
    assert result == 1


@pytest.mark.asyncio
async def test_execute_no_params(pool_config, mock_aiomysql_pool):
    """Test execute without parameters."""
    pool = MySQLPool(**pool_config)
    mock_pool, mock_conn, mock_cursor = mock_aiomysql_pool

    pool.pool = mock_pool
    mock_cursor.execute.return_value = 5

    result = await pool.execute("DELETE FROM expired_sessions")

    mock_cursor.execute.assert_called_once_with("DELETE FROM expired_sessions", {})
    mock_conn.commit.assert_called_once()
    assert result == 5


@pytest.mark.asyncio
async def test_execute_no_pool(pool_config):
    """Test execute raises error when pool not connected."""
    pool = MySQLPool(**pool_config)

    with pytest.raises(RuntimeError, match="Pool not connected"):
        await pool.execute("UPDATE users SET active = 1")


@pytest.mark.asyncio
async def test_execute_many(pool_config, mock_aiomysql_pool):
    """Test execute_many method."""
    pool = MySQLPool(**pool_config)
    mock_pool, mock_conn, mock_cursor = mock_aiomysql_pool

    pool.pool = mock_pool

    params_list = [
        {"name": "Alice", "email": "alice@example.com"},
        {"name": "Bob", "email": "bob@example.com"},
    ]

    await pool.execute_many(
        "INSERT INTO users (name, email) VALUES (%(name)s, %(email)s)", params_list
    )

    mock_cursor.executemany.assert_called_once_with(
        "INSERT INTO users (name, email) VALUES (%(name)s, %(email)s)", params_list
    )
    mock_conn.commit.assert_called_once()


@pytest.mark.asyncio
async def test_execute_many_no_pool(pool_config):
    """Test execute_many raises error when pool not connected."""
    pool = MySQLPool(**pool_config)

    with pytest.raises(RuntimeError, match="Pool not connected"):
        await pool.execute_many("INSERT INTO users VALUES (%(id)s)", [{"id": 1}, {"id": 2}])


@pytest.mark.asyncio
async def test_pool_lifecycle(pool_config):
    """Test full pool lifecycle: connect -> execute -> disconnect."""
    pool = MySQLPool(**pool_config)

    with patch("aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = AsyncMock()

        # Create async context manager for pool.acquire()
        pool_context = AsyncMock()
        pool_context.__aenter__.return_value = mock_conn
        pool_context.__aexit__.return_value = None
        mock_pool.acquire.return_value = pool_context

        # Create async context manager for conn.cursor()
        cursor_context = AsyncMock()
        cursor_context.__aenter__.return_value = mock_cursor
        cursor_context.__aexit__.return_value = None
        mock_conn.cursor.return_value = cursor_context

        mock_cursor.fetchall.return_value = [{"count": 5}]
        mock_pool.close = MagicMock()
        mock_pool.wait_closed = AsyncMock()
        mock_create_pool.return_value = mock_pool

        # Connect
        await pool.connect()
        assert pool.pool is not None

        # Execute query
        result = await pool.fetch_all("SELECT COUNT(*) as count FROM users")
        assert result == [{"count": 5}]

        # Disconnect
        await pool.disconnect()
        assert pool.pool is None
        mock_pool.close.assert_called_once()
        mock_pool.wait_closed.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_one_as_dict_default(pool_config, mock_aiomysql_pool):
    """Test fetch_one returns dict by default."""
    pool = MySQLPool(**pool_config)
    mock_pool, mock_conn, mock_cursor = mock_aiomysql_pool

    pool.pool = mock_pool
    mock_cursor.fetchone.return_value = {"id": 1, "name": "Alice"}

    result = await pool.fetch_one("SELECT id, name FROM users WHERE id = %(id)s", {"id": 1})

    assert isinstance(result, dict)
    assert result == {"id": 1, "name": "Alice"}


@pytest.mark.asyncio
async def test_fetch_one_as_tuple(pool_config, mock_aiomysql_pool):
    """Test fetch_one returns tuple when as_dict=False."""
    pool = MySQLPool(**pool_config)
    mock_pool, mock_conn, mock_cursor = mock_aiomysql_pool

    pool.pool = mock_pool
    mock_cursor.fetchone.return_value = (1, "Alice")

    result = await pool.fetch_one(
        "SELECT id, name FROM users WHERE id = %(id)s", {"id": 1}, as_dict=False
    )

    assert isinstance(result, tuple)
    assert result == (1, "Alice")


@pytest.mark.asyncio
async def test_fetch_all_as_dict_default(pool_config, mock_aiomysql_pool):
    """Test fetch_all returns list of dicts by default."""
    pool = MySQLPool(**pool_config)
    mock_pool, mock_conn, mock_cursor = mock_aiomysql_pool

    pool.pool = mock_pool
    mock_cursor.fetchall.return_value = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]

    results = await pool.fetch_all("SELECT id, name FROM users")

    assert isinstance(results, list)
    assert len(results) == 2
    assert all(isinstance(row, dict) for row in results)


@pytest.mark.asyncio
async def test_fetch_all_as_tuple(pool_config, mock_aiomysql_pool):
    """Test fetch_all returns list of tuples when as_dict=False."""
    pool = MySQLPool(**pool_config)
    mock_pool, mock_conn, mock_cursor = mock_aiomysql_pool

    pool.pool = mock_pool
    mock_cursor.fetchall.return_value = [(1, "Alice"), (2, "Bob")]

    results = await pool.fetch_all("SELECT id, name FROM users", as_dict=False)

    assert isinstance(results, list)
    assert len(results) == 2
    assert all(isinstance(row, tuple) for row in results)


@pytest.mark.asyncio
async def test_fetch_one_none(pool_config, mock_aiomysql_pool):
    """Test fetch_one returns None when no results."""
    pool = MySQLPool(**pool_config)
    mock_pool, mock_conn, mock_cursor = mock_aiomysql_pool

    pool.pool = mock_pool
    mock_cursor.fetchone.return_value = None

    result = await pool.fetch_one("SELECT * FROM users WHERE id = %(id)s", {"id": 999999})

    assert result is None


@pytest.mark.asyncio
async def test_fetch_all_empty(pool_config, mock_aiomysql_pool):
    """Test fetch_all returns empty list when no results."""
    pool = MySQLPool(**pool_config)
    mock_pool, mock_conn, mock_cursor = mock_aiomysql_pool

    pool.pool = mock_pool
    mock_cursor.fetchall.return_value = []

    results = await pool.fetch_all("SELECT * FROM users WHERE id = %(id)s", {"id": 999999})

    assert results == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
