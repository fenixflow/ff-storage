"""
Integration tests for connection resilience and monitoring features.

Tests the production-ready features including:
- Connection retry logic
- Circuit breaker functionality
- Pool exhaustion handling
- Query timeout detection
- Metrics collection
- Health checks
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import psycopg2

from ff_storage.db.connections.postgres import PostgresPool, Postgres
from ff_storage.exceptions import (
    ConnectionFailure,
    ConnectionPoolExhausted,
    QueryTimeout,
    CircuitBreakerOpen,
)
from ff_storage.health import HealthStatus
from ff_storage.utils.retry import CircuitState
from ff_storage.utils.metrics import MetricsCollector


@pytest.fixture
def pool_config():
    """Test pool configuration."""
    return {
        "dbname": "test_db",
        "user": "test_user",
        "password": "test_pass",
        "host": "localhost",
        "port": 5432,
        "min_size": 5,
        "max_size": 10,
        "query_timeout": 1000,  # 1 second
        "collect_metrics": True,
    }


@pytest.fixture
def metrics_collector():
    """Test metrics collector."""
    return MetricsCollector()


class TestConnectionResilience:
    """Test connection resilience features."""

    @pytest.mark.asyncio
    async def test_connection_retry_on_failure(self, pool_config):
        """Test connection retries on transient failures."""
        pool = PostgresPool(**pool_config)

        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            # Simulate transient failures then success
            mock_create.side_effect = [
                ConnectionError("Connection refused"),
                ConnectionError("Connection refused"),
                AsyncMock(),  # Success on third try
            ]

            # Should succeed after retries
            await pool.connect()

            assert mock_create.call_count == 3
            assert pool.pool is not None

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_repeated_failures(self, pool_config):
        """Test circuit breaker opens after threshold failures."""
        pool = PostgresPool(**pool_config)

        # Access the circuit breaker
        circuit_breaker = pool._circuit_breaker

        # Simulate repeated failures
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = ConnectionError("Persistent failure")

            # First attempt should fail normally
            with pytest.raises(ConnectionFailure):
                await pool.connect()

            # Force circuit breaker to open by simulating multiple failures
            for _ in range(4):
                try:
                    await circuit_breaker.async_call(mock_create)
                except Exception:
                    pass  # Expected failures to trip circuit breaker

            # Circuit should be open now
            assert circuit_breaker.state == CircuitState.OPEN

            # Next attempt should fail immediately with CircuitBreakerOpen
            with pytest.raises(CircuitBreakerOpen) as exc_info:
                await circuit_breaker.async_call(mock_create)

            assert "postgres_pool_test_db" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_pool_exhaustion_handling(self, pool_config):
        """Test handling of connection pool exhaustion."""
        pool = PostgresPool(**pool_config)

        # Mock pool that's exhausted
        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock(side_effect=asyncio.TimeoutError("Pool exhausted"))
        pool.pool = mock_pool

        # Should raise ConnectionPoolExhausted
        with pytest.raises(ConnectionPoolExhausted) as exc_info:
            await pool.fetch_one("SELECT 1")

        assert "size=10" in str(exc_info.value)
        assert "timeout=10" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_timeout_detection(self, pool_config):
        """Test detection and handling of query timeouts."""
        pool = PostgresPool(**pool_config)

        # Mock pool and connection
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(
            side_effect=Exception("canceling statement due to statement timeout")
        )

        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        pool.pool = mock_pool

        # Should raise QueryTimeout
        with pytest.raises(QueryTimeout) as exc_info:
            await pool.fetch_one("SELECT pg_sleep(10)")

        assert "1.0s" in str(exc_info.value)  # query_timeout / 1000

    @pytest.mark.asyncio
    async def test_pool_warmup_on_connect(self, pool_config):
        """Test connection pool warmup during initialization."""
        pool = PostgresPool(**pool_config)

        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            mock_pool = AsyncMock()

            # Mock connection acquisition for warmup
            mock_conn = AsyncMock()
            mock_conn.fetchval = AsyncMock(return_value=1)
            mock_pool.acquire = AsyncMock()
            mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_create.return_value = mock_pool

            # Connect should trigger warmup
            await pool.connect()

            # Verify warmup queries were executed
            assert mock_conn.fetchval.call_count >= pool.min_size
            mock_conn.fetchval.assert_called_with("SELECT 1")

    @pytest.mark.asyncio
    async def test_metrics_collection(self, pool_config, metrics_collector):
        """Test metrics are collected during operations."""
        # Set global metrics collector
        from ff_storage.utils.metrics import set_global_collector

        set_global_collector(metrics_collector)

        pool = PostgresPool(**pool_config)
        pool._metrics_collector = metrics_collector

        # Mock successful query
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"test": "data"})

        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        pool.pool = mock_pool

        # Execute query
        await pool.fetch_one("SELECT 1")

        # Check metrics were recorded
        query_stats = metrics_collector.get_query_statistics(window_minutes=1)
        assert query_stats["total_queries"] > 0
        assert query_stats["success_rate"] == 100.0

    @pytest.mark.asyncio
    async def test_health_check(self, pool_config):
        """Test health check functionality."""
        pool = PostgresPool(**pool_config)

        # Mock healthy pool
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"health_check": 1})

        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_pool._holders = []  # No active connections
        mock_pool._free = [1, 2, 3, 4, 5]  # 5 free connections
        pool.pool = mock_pool

        # Perform health check
        result = await pool.check_health()

        assert result.status == HealthStatus.HEALTHY
        assert "healthy" in result.message.lower()
        assert result.details["pool_size"] == 10
        assert result.details["utilization_percent"] == 0.0

    @pytest.mark.asyncio
    async def test_health_check_degraded_state(self, pool_config):
        """Test health check detects degraded state."""
        pool = PostgresPool(**pool_config)

        # Mock pool with high utilization
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"health_check": 1})

        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_pool._holders = list(range(9))  # 9 active connections
        mock_pool._free = [1]  # 1 free connection
        pool.pool = mock_pool

        # Perform health check
        result = await pool.check_health()

        assert result.status == HealthStatus.DEGRADED
        assert "high" in result.message.lower()
        assert result.details["utilization_percent"] == 90.0

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_state(self, pool_config):
        """Test health check detects unhealthy state."""
        pool = PostgresPool(**pool_config)

        # Pool not initialized
        result = await pool.check_health()

        assert result.status == HealthStatus.UNHEALTHY
        assert "not initialized" in result.message.lower()
        assert result.error == "Pool is None"

    @pytest.mark.asyncio
    async def test_query_validation(self, pool_config):
        """Test SQL query validation."""
        pool = PostgresPool(**pool_config, validate_queries=True)

        # Mock pool
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"id": 1})

        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        pool.pool = mock_pool

        # Safe query should work
        await pool.fetch_one("SELECT * FROM users WHERE id = $1", 1)

        # Dangerous patterns should be logged as warnings
        # (actual blocking would break legitimate queries, so we just warn)
        with patch.object(pool.logger, "warning") as mock_warning:
            await pool.fetch_one("SELECT * FROM users; DROP TABLE users", 1)
            assert mock_warning.called

    def test_sync_connection_retry(self, pool_config):
        """Test sync connection retry logic."""
        # Remove async-only config
        sync_config = {k: v for k, v in pool_config.items() if k not in ["min_size", "max_size"]}
        conn = Postgres(**sync_config)

        with patch("psycopg2.connect") as mock_connect:
            # Simulate transient failures then success
            mock_connect.side_effect = [
                psycopg2.OperationalError("Connection refused"),
                psycopg2.OperationalError("Connection refused"),
                MagicMock(),  # Success on third try
            ]

            # Should succeed after retries
            conn.connect()

            assert mock_connect.call_count == 3
            assert conn.connection is not None

    @pytest.mark.asyncio
    async def test_concurrent_operations_handling(self, pool_config):
        """Test handling of concurrent operations."""
        pool = PostgresPool(**pool_config)

        # Mock pool
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"count": 1})
        mock_conn.fetch = AsyncMock(return_value=[])

        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        pool.pool = mock_pool

        # Execute multiple concurrent queries
        tasks = [pool.fetch_one(f"SELECT {i}") for i in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should succeed
        assert all(not isinstance(r, Exception) for r in results)
        assert mock_conn.fetchrow.call_count == 20

    @pytest.mark.asyncio
    async def test_pool_metrics_recording(self, pool_config, metrics_collector):
        """Test pool metrics are recorded periodically."""
        from ff_storage.utils.metrics import set_global_collector

        set_global_collector(metrics_collector)

        pool = PostgresPool(**pool_config)
        pool._metrics_collector = metrics_collector

        # Mock pool stats
        mock_pool = AsyncMock()
        mock_pool._size = 10
        mock_pool._holders = list(range(5))
        mock_pool._free = list(range(5))
        mock_pool._queue = AsyncMock()
        mock_pool._queue.qsize = MagicMock(return_value=2)
        pool.pool = mock_pool

        # Record metrics
        pool._record_pool_metrics()

        # Check pool metrics
        pool_stats = metrics_collector.get_pool_statistics()
        assert pool_stats["pool_size"] == 10
        assert pool_stats["active_connections"] == 5
        assert pool_stats["idle_connections"] == 5
        assert pool_stats["waiting_requests"] == 2

    @pytest.mark.asyncio
    async def test_connection_timeout_configuration(self, pool_config):
        """Test connection timeout is properly configured."""
        pool = PostgresPool(**pool_config, connection_timeout=5)

        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            await pool.connect()

            # Verify timeout was passed to create_pool
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["timeout"] == 5
            assert call_kwargs["command_timeout"] == pool.query_timeout / 1000
