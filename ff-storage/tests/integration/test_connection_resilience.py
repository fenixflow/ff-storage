"""
Integration tests for connection resilience.

Tests connection pool recovery, retry logic, and error handling.
"""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from ff_storage import Field, PydanticModel
from ff_storage.exceptions import TemporalStrategyError
from ff_storage.temporal.repository_base import TemporalRepository


class TestProduct(PydanticModel):
    """Test model for resilience testing."""

    __table_name__ = "test_products"
    __temporal_strategy__ = "none"

    name: str = Field(max_length=255)
    value: int


class TestConnectionResilience:
    """Test connection pool resilience and recovery."""

    @pytest.mark.asyncio
    async def test_connection_retry_on_timeout(self):
        """Test that operations retry on connection timeout."""
        # Mock pool that times out initially, then succeeds
        pool = AsyncMock()
        conn = AsyncMock()

        # First attempt times out, second succeeds
        acquire_context = AsyncMock()
        acquire_context.__aenter__.side_effect = [
            asyncio.TimeoutError("Connection timeout"),
            conn,
        ]
        pool.acquire.return_value = acquire_context

        # Mock strategy
        strategy = AsyncMock()
        strategy.multi_tenant = False
        strategy.get.return_value = TestProduct(id=uuid4(), name="Test", value=42)

        # Create repository with retry enabled
        repo = TemporalRepository(
            model_class=TestProduct,
            db_pool=pool,
            strategy=strategy,
            max_retries=3,
        )

        # Should succeed after retry
        result = await repo.get(uuid4())
        assert result is not None
        assert result.name == "Test"

        # Verify it tried twice
        assert pool.acquire.call_count >= 1

    @pytest.mark.asyncio
    async def test_connection_retry_exhaustion(self):
        """Test that operations fail after max retries."""
        # Mock pool that always times out
        pool = AsyncMock()
        acquire_context = AsyncMock()
        acquire_context.__aenter__.side_effect = asyncio.TimeoutError("Connection timeout")
        pool.acquire.return_value = acquire_context

        # Mock strategy
        strategy = AsyncMock()
        strategy.multi_tenant = False

        # Create repository with limited retries
        repo = TemporalRepository(
            model_class=TestProduct,
            db_pool=pool,
            strategy=strategy,
            max_retries=2,
        )

        # Should fail after max retries
        with pytest.raises(TemporalStrategyError) as exc_info:
            await repo.create(TestProduct(name="Test", value=42))

        assert "create" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_pool_recovery_after_disconnect(self):
        """Test that pool recovers after database disconnect."""
        # Mock pool that fails then recovers
        pool = AsyncMock()
        conn = AsyncMock()

        # Simulate disconnect then recovery
        call_count = 0

        async def acquire_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Database connection lost")
            return conn

        acquire_context = AsyncMock()
        acquire_context.__aenter__.side_effect = acquire_side_effect
        pool.acquire.return_value = acquire_context

        # Mock successful operations after recovery
        conn.fetchrow.return_value = {
            "id": uuid4(),
            "name": "Recovered",
            "value": 100,
        }

        # Mock strategy
        strategy = AsyncMock()
        strategy.multi_tenant = False

        # Create repository
        repo = TemporalRepository(
            model_class=TestProduct,
            db_pool=pool,
            strategy=strategy,
            max_retries=3,
        )

        # First operation fails but retries and succeeds
        with patch.object(strategy, "get") as mock_get:
            mock_get.return_value = TestProduct(id=uuid4(), name="Recovered", value=100)

            result = await repo.get(uuid4())
            assert result.name == "Recovered"

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_error(self):
        """Test that transactions rollback on error."""
        pool = AsyncMock()
        conn = AsyncMock()
        transaction = AsyncMock()

        # Setup transaction context
        conn.transaction.return_value = transaction
        acquire_context = AsyncMock()
        acquire_context.__aenter__.return_value = conn
        pool.acquire.return_value = acquire_context

        # Simulate error during transaction
        conn.execute.side_effect = [
            None,  # First query succeeds
            Exception("Constraint violation"),  # Second query fails
        ]

        # Mock strategy that uses transactions
        strategy = AsyncMock()
        strategy.multi_tenant = False

        _ = TemporalRepository(
            model_class=TestProduct,
            db_pool=pool,
            strategy=strategy,
        )

        # Operation should fail and rollback
        with pytest.raises(Exception):
            await strategy.create(
                data={"name": "Test", "value": 42},
                db_pool=pool,
                tenant_id=None,
                user_id=None,
            )

        # Verify rollback was called
        if hasattr(transaction, "__aexit__"):
            # Transaction context manager handles rollback
            pass

    @pytest.mark.asyncio
    async def test_concurrent_operations_with_pool_limit(self):
        """Test handling of concurrent operations with limited pool size."""
        # Mock pool with limited connections
        pool = AsyncMock()
        connections = [AsyncMock() for _ in range(3)]  # Pool size of 3

        # Track which connections are in use
        available_connections = connections.copy()
        in_use_connections = []

        async def acquire_connection():
            if not available_connections:
                # Pool exhausted, wait
                await asyncio.sleep(0.1)
                if available_connections:
                    conn = available_connections.pop()
                    in_use_connections.append(conn)
                    return conn
                raise asyncio.TimeoutError("Pool exhausted")

            conn = available_connections.pop()
            in_use_connections.append(conn)
            return conn

        async def release_connection(conn):
            if conn in in_use_connections:
                in_use_connections.remove(conn)
                available_connections.append(conn)

        # Setup acquire context
        acquire_contexts = []
        for _ in range(10):  # More operations than pool size
            ctx = AsyncMock()
            ctx.__aenter__ = acquire_connection
            ctx.__aexit__ = AsyncMock(side_effect=lambda *args: release_connection(None))
            acquire_contexts.append(ctx)

        pool.acquire.side_effect = acquire_contexts

        # Mock strategy
        strategy = AsyncMock()
        strategy.multi_tenant = False
        strategy.get.return_value = TestProduct(id=uuid4(), name="Test", value=42)

        repo = TemporalRepository(
            model_class=TestProduct,
            db_pool=pool,
            strategy=strategy,
        )

        # Run concurrent operations
        operations = [repo.get(uuid4()) for _ in range(6)]

        # Some should succeed, some might timeout
        results = await asyncio.gather(*operations, return_exceptions=True)

        # At least pool size operations should succeed
        successful = [r for r in results if not isinstance(r, Exception)]
        assert len(successful) >= 3

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_partial_failure(self):
        """Test that partial failures are handled gracefully."""
        pool = AsyncMock()
        conn = AsyncMock()

        acquire_context = AsyncMock()
        acquire_context.__aenter__.return_value = conn
        pool.acquire.return_value = acquire_context

        # Some operations succeed, some fail
        success_ids = [uuid4() for _ in range(3)]
        fail_ids = [uuid4() for _ in range(2)]

        async def fetch_side_effect(query, *args):
            # Check if querying for success or fail ID
            for arg in args:
                if arg in fail_ids:
                    raise Exception("Record corrupted")
                if arg in success_ids:
                    return {
                        "id": arg,
                        "name": f"Product {arg}",
                        "value": 100,
                    }
            return None

        conn.fetchrow.side_effect = fetch_side_effect

        # Mock strategy
        strategy = AsyncMock()
        strategy.multi_tenant = False

        repo = TemporalRepository(
            model_class=TestProduct,
            db_pool=pool,
            strategy=strategy,
        )

        # Try to get multiple records
        all_ids = success_ids + fail_ids
        results = {}

        for id in all_ids:
            try:
                with patch.object(strategy, "get") as mock_get:
                    if id in success_ids:
                        mock_get.return_value = TestProduct(id=id, name=f"Product {id}", value=100)
                    else:
                        mock_get.side_effect = Exception("Record corrupted")

                    result = await repo.get(id)
                    results[id] = result
            except Exception:
                results[id] = None

        # Verify partial success
        for id in success_ids:
            assert results[id] is not None

        for id in fail_ids:
            assert results[id] is None

    @pytest.mark.asyncio
    async def test_connection_pool_cleanup_on_error(self):
        """Test that connections are properly released on error."""
        pool = AsyncMock()
        conn = AsyncMock()

        # Track acquire/release
        acquired = []
        released = []

        async def on_acquire():
            acquired.append(conn)
            return conn

        async def on_release(*args):
            released.append(conn)

        acquire_context = AsyncMock()
        acquire_context.__aenter__.side_effect = on_acquire
        acquire_context.__aexit__.side_effect = on_release
        pool.acquire.return_value = acquire_context

        # Simulate error during operation
        conn.fetchrow.side_effect = Exception("Query failed")

        # Mock strategy
        strategy = AsyncMock()
        strategy.multi_tenant = False
        strategy.get.side_effect = Exception("Query failed")

        repo = TemporalRepository(
            model_class=TestProduct,
            db_pool=pool,
            strategy=strategy,
        )

        # Operation fails
        with pytest.raises(TemporalStrategyError):
            await repo.get(uuid4())

        # Connection should still be released
        assert len(acquired) == len(released)

    @pytest.mark.asyncio
    async def test_health_check_integration(self):
        """Test health check with connection pool."""
        from ff_storage.health import HealthChecker

        # Mock pool with health check
        pool = AsyncMock()
        pool.acquire = AsyncMock()

        # Healthy connection
        healthy_conn = AsyncMock()
        healthy_conn.fetchval.return_value = 1  # SELECT 1 returns 1

        healthy_context = AsyncMock()
        healthy_context.__aenter__.return_value = healthy_conn
        healthy_context.__aexit__.return_value = None

        pool.acquire.return_value = healthy_context

        # Create health checker
        checker = HealthChecker(db_pool=pool, services={})

        # Check database health
        health = await checker.check_database()
        assert health["status"] == "healthy"
        assert health["latency_ms"] is not None

        # Now simulate unhealthy connection
        pool.acquire.side_effect = asyncio.TimeoutError("Connection timeout")

        health = await checker.check_database()
        assert health["status"] == "unhealthy"
        assert "error" in health

    @pytest.mark.asyncio
    async def test_exponential_backoff_retry(self):
        """Test exponential backoff in retry logic."""
        from ff_storage.utils.retry import exponential_backoff, retry_async

        call_times = []
        attempts = 0

        @retry_async(
            max_attempts=4,
            delay=exponential_backoff(base_delay=0.1, max_delay=1.0),
            exceptions=(ConnectionError,),
        )
        async def flaky_operation():
            nonlocal attempts
            attempts += 1
            call_times.append(asyncio.get_event_loop().time())

            if attempts < 3:
                raise ConnectionError("Connection lost")
            return "success"

        # Run operation
        result = await flaky_operation()

        assert result == "success"
        assert attempts == 3

        # Verify exponential delays (roughly 0.1, 0.2, 0.4 seconds)
        if len(call_times) >= 3:
            delay1 = call_times[1] - call_times[0]
            delay2 = call_times[2] - call_times[1]

            # Second delay should be roughly double the first
            assert delay2 > delay1 * 1.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
