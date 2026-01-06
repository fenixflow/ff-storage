"""
Test async PostgreSQL connection pool using asyncpg.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from ff_storage.db.connections.postgres import PostgresPool
from ff_storage.exceptions import ConnectionPoolExhausted


@pytest.fixture
def pool_config():
    """Pool configuration for testing."""
    return {
        "dbname": "test_db",
        "user": "test_user",
        "password": "test_pass",
        "host": "localhost",
        "port": 5432,
        "min_size": 5,
        "max_size": 10,
    }


@pytest_asyncio.fixture
async def mock_asyncpg_pool():
    """Mock asyncpg pool."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()

    # Create async context manager for pool.acquire()
    async_context = AsyncMock()
    async_context.__aenter__.return_value = mock_conn
    async_context.__aexit__.return_value = None

    mock_pool.acquire.return_value = async_context

    return mock_pool, mock_conn


@pytest.mark.asyncio
async def test_pool_connect(pool_config):
    """Test pool connection creation."""
    pool = PostgresPool(**pool_config)

    with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_pool = AsyncMock()
        mock_create_pool.return_value = mock_pool

        # Mock _warmup_pool to prevent background tasks
        with patch.object(pool, "_warmup_pool", new_callable=AsyncMock):
            await pool.connect()

        mock_create_pool.assert_called_once()
        assert pool.pool is not None


@pytest.mark.asyncio
async def test_pool_connect_already_connected(pool_config):
    """Test that connecting twice doesn't create a new pool."""
    pool = PostgresPool(**pool_config)

    with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_pool = AsyncMock()
        mock_create_pool.return_value = mock_pool

        # Mock _warmup_pool to prevent background tasks
        with patch.object(pool, "_warmup_pool", new_callable=AsyncMock):
            await pool.connect()
            await pool.connect()  # Second call

        # Should only be called once
        mock_create_pool.assert_called_once()


@pytest.mark.asyncio
async def test_pool_disconnect(pool_config):
    """Test pool disconnection."""
    pool = PostgresPool(**pool_config)

    with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_pool = AsyncMock()
        mock_create_pool.return_value = mock_pool

        # Mock _warmup_pool to prevent background tasks
        with patch.object(pool, "_warmup_pool", new_callable=AsyncMock):
            await pool.connect()
            await pool.disconnect()

        mock_pool.close.assert_called_once()
        assert pool.pool is None


@pytest.mark.asyncio
async def test_fetch_one(pool_config, mock_asyncpg_pool):
    """Test fetch_one method."""
    pool = PostgresPool(**pool_config)
    mock_pool, mock_conn = mock_asyncpg_pool

    pool.pool = mock_pool
    mock_conn.fetchrow.return_value = {"id": 1, "name": "test"}

    result = await pool.fetch_one("SELECT * FROM users WHERE id = $1", 1)

    mock_conn.fetchrow.assert_called_once_with("SELECT * FROM users WHERE id = $1", 1)
    assert result == {"id": 1, "name": "test"}


@pytest.mark.asyncio
async def test_fetch_one_no_pool(pool_config):
    """Test fetch_one raises error when pool not connected."""
    pool = PostgresPool(**pool_config)

    with pytest.raises(ConnectionPoolExhausted):
        await pool.fetch_one("SELECT * FROM users")


@pytest.mark.asyncio
async def test_fetch_all(pool_config, mock_asyncpg_pool):
    """Test fetch_all method."""
    pool = PostgresPool(**pool_config)
    mock_pool, mock_conn = mock_asyncpg_pool

    pool.pool = mock_pool
    mock_conn.fetch.return_value = [
        {"id": 1, "name": "test1"},
        {"id": 2, "name": "test2"},
    ]

    result = await pool.fetch_all("SELECT * FROM users WHERE active = $1", True)

    mock_conn.fetch.assert_called_once_with("SELECT * FROM users WHERE active = $1", True)
    assert len(result) == 2
    assert result[0] == {"id": 1, "name": "test1"}


@pytest.mark.asyncio
async def test_fetch_all_no_params(pool_config, mock_asyncpg_pool):
    """Test fetch_all without parameters."""
    pool = PostgresPool(**pool_config)
    mock_pool, mock_conn = mock_asyncpg_pool

    pool.pool = mock_pool
    mock_conn.fetch.return_value = [{"id": 1, "name": "test"}]

    result = await pool.fetch_all("SELECT * FROM users")

    mock_conn.fetch.assert_called_once_with("SELECT * FROM users")
    assert len(result) == 1


@pytest.mark.asyncio
async def test_execute(pool_config, mock_asyncpg_pool):
    """Test execute method."""
    pool = PostgresPool(**pool_config)
    mock_pool, mock_conn = mock_asyncpg_pool

    pool.pool = mock_pool
    mock_conn.execute.return_value = "UPDATE 1"

    result = await pool.execute("UPDATE users SET name = $1 WHERE id = $2", "John", 1)

    mock_conn.execute.assert_called_once_with("UPDATE users SET name = $1 WHERE id = $2", "John", 1)
    assert result == "UPDATE 1"


@pytest.mark.asyncio
async def test_execute_returning(pool_config, mock_asyncpg_pool):
    """Test fetch_one with RETURNING clause (use fetch_one for RETURNING)."""
    pool = PostgresPool(**pool_config)
    mock_pool, mock_conn = mock_asyncpg_pool

    pool.pool = mock_pool
    mock_conn.fetchrow.return_value = {"id": 123}

    result = await pool.fetch_one("INSERT INTO users (name) VALUES ($1) RETURNING id", "John")

    mock_conn.fetchrow.assert_called_once_with(
        "INSERT INTO users (name) VALUES ($1) RETURNING id", "John"
    )
    assert result == {"id": 123}


@pytest.mark.asyncio
async def test_execute_many(pool_config, mock_asyncpg_pool):
    """Test execute_many method."""
    pool = PostgresPool(**pool_config)
    mock_pool, mock_conn = mock_asyncpg_pool

    pool.pool = mock_pool

    params_list = [
        ("Alice", "alice@example.com"),
        ("Bob", "bob@example.com"),
    ]

    await pool.execute_many("INSERT INTO users (name, email) VALUES ($1, $2)", params_list)

    mock_conn.executemany.assert_called_once_with(
        "INSERT INTO users (name, email) VALUES ($1, $2)", params_list
    )


@pytest.mark.asyncio
async def test_execute_many_no_pool(pool_config):
    """Test execute_many raises error when pool not connected."""
    pool = PostgresPool(**pool_config)

    with pytest.raises(ConnectionPoolExhausted):
        await pool.execute_many("INSERT INTO users VALUES ($1)", [(1,), (2,)])


@pytest.mark.asyncio
async def test_pool_lifecycle(pool_config):
    """Test full pool lifecycle: connect -> execute -> disconnect."""
    pool = PostgresPool(**pool_config)

    with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_pool = MagicMock()
        mock_conn = AsyncMock()

        # Create async context manager for pool.acquire()
        async_context = AsyncMock()
        async_context.__aenter__.return_value = mock_conn
        async_context.__aexit__.return_value = None

        mock_pool.acquire.return_value = async_context
        mock_pool.close = AsyncMock()  # close() is async for asyncpg
        mock_conn.fetch.return_value = [{"count": 5}]
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


@pytest.mark.asyncio
async def test_fetch_one_as_dict_default(pool_config, mock_asyncpg_pool):
    """Test fetch_one returns dict by default."""
    pool = PostgresPool(**pool_config)
    mock_pool, mock_conn = mock_asyncpg_pool

    pool.pool = mock_pool
    # Mock asyncpg.Record - it acts like a dict but is different type
    mock_record = MagicMock()
    mock_record.__iter__ = lambda self: iter([("id", 1), ("name", "Alice")])
    mock_conn.fetchrow.return_value = mock_record

    result = await pool.fetch_one("SELECT id, name FROM users WHERE id = $1", 1)

    assert isinstance(result, dict)
    mock_conn.fetchrow.assert_called_once_with("SELECT id, name FROM users WHERE id = $1", 1)


@pytest.mark.asyncio
async def test_fetch_one_as_tuple(pool_config, mock_asyncpg_pool):
    """Test fetch_one returns tuple when as_dict=False."""
    pool = PostgresPool(**pool_config)
    mock_pool, mock_conn = mock_asyncpg_pool

    pool.pool = mock_pool
    mock_record = MagicMock()
    mock_record.__iter__ = lambda self: iter([1, "Alice"])
    mock_conn.fetchrow.return_value = mock_record

    result = await pool.fetch_one("SELECT id, name FROM users WHERE id = $1", 1, as_dict=False)

    assert isinstance(result, tuple)


@pytest.mark.asyncio
async def test_fetch_all_as_dict_default(pool_config, mock_asyncpg_pool):
    """Test fetch_all returns list of dicts by default."""
    pool = PostgresPool(**pool_config)
    mock_pool, mock_conn = mock_asyncpg_pool

    pool.pool = mock_pool
    # Mock asyncpg.Record objects
    mock_record1 = MagicMock()
    mock_record1.__iter__ = lambda self: iter([("id", 1), ("name", "Alice")])
    mock_record2 = MagicMock()
    mock_record2.__iter__ = lambda self: iter([("id", 2), ("name", "Bob")])
    mock_conn.fetch.return_value = [mock_record1, mock_record2]

    results = await pool.fetch_all("SELECT id, name FROM users")

    assert isinstance(results, list)
    assert len(results) == 2
    assert all(isinstance(row, dict) for row in results)


@pytest.mark.asyncio
async def test_fetch_all_as_tuple(pool_config, mock_asyncpg_pool):
    """Test fetch_all returns list of tuples when as_dict=False."""
    pool = PostgresPool(**pool_config)
    mock_pool, mock_conn = mock_asyncpg_pool

    pool.pool = mock_pool
    mock_record1 = MagicMock()
    mock_record1.__iter__ = lambda self: iter([1, "Alice"])
    mock_record2 = MagicMock()
    mock_record2.__iter__ = lambda self: iter([2, "Bob"])
    mock_conn.fetch.return_value = [mock_record1, mock_record2]

    results = await pool.fetch_all("SELECT id, name FROM users", as_dict=False)

    assert isinstance(results, list)
    assert len(results) == 2
    assert all(isinstance(row, tuple) for row in results)


@pytest.mark.asyncio
async def test_fetch_one_none(pool_config, mock_asyncpg_pool):
    """Test fetch_one returns None when no results."""
    pool = PostgresPool(**pool_config)
    mock_pool, mock_conn = mock_asyncpg_pool

    pool.pool = mock_pool
    mock_conn.fetchrow.return_value = None

    result = await pool.fetch_one("SELECT * FROM users WHERE id = $1", 999999)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_all_empty(pool_config, mock_asyncpg_pool):
    """Test fetch_all returns empty list when no results."""
    pool = PostgresPool(**pool_config)
    mock_pool, mock_conn = mock_asyncpg_pool

    pool.pool = mock_pool
    mock_conn.fetch.return_value = []

    results = await pool.fetch_all("SELECT * FROM users WHERE id = $1", 999999)

    assert results == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
