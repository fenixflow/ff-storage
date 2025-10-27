"""
Health check utilities for monitoring system status.

This module provides health check functions for database connections,
storage backends, and overall system health.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .utils.metrics import get_global_collector


class HealthStatus(Enum):
    """Health check status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    name: str
    status: HealthStatus
    message: str
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def is_healthy(self) -> bool:
        """Check if result indicates healthy status."""
        return self.status == HealthStatus.HEALTHY

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
            "error": self.error,
        }


class HealthChecker:
    """
    Comprehensive health checking for ff-storage components.

    Performs health checks on database connections, storage backends,
    and collects system metrics.
    """

    def __init__(self):
        """Initialize health checker."""
        self.checks: Dict[str, Callable] = {}
        self.async_checks: Dict[str, Callable] = {}
        self.metrics_collector = get_global_collector()

    def register_check(self, name: str, check_func: Callable, is_async: bool = False):
        """
        Register a health check function.

        Args:
            name: Name of the health check
            check_func: Function that performs the check
            is_async: Whether the function is async
        """
        if is_async:
            self.async_checks[name] = check_func
        else:
            self.checks[name] = check_func

    async def check_database_pool(self, pool: Any, name: str = "database") -> HealthCheckResult:
        """
        Check database connection pool health.

        Args:
            pool: Database connection pool (PostgresPool, MySQLPool, etc.)
            name: Name for the health check

        Returns:
            Health check result
        """
        start_time = time.perf_counter()

        try:
            # Check if pool is connected
            if not hasattr(pool, "pool") or pool.pool is None:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message="Connection pool not initialized",
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                    error="Pool is None",
                )

            # Try a simple query
            result = await pool.fetch_one("SELECT 1 as health_check")
            if result and result.get("health_check") == 1:
                # Get pool statistics if available
                details = {}
                if hasattr(pool.pool, "size"):
                    details["pool_size"] = pool.pool.size
                if hasattr(pool.pool, "free"):
                    details["free_connections"] = len(pool.pool.free)
                if hasattr(pool.pool, "used"):
                    details["used_connections"] = len(pool.pool.used)

                # Calculate utilization
                if details.get("pool_size"):
                    used = details.get("used_connections", 0)
                    size = details["pool_size"]
                    utilization = (used / size) * 100 if size > 0 else 0
                    details["utilization_percent"] = round(utilization, 2)

                    # Determine status based on utilization
                    if utilization > 90:
                        status = HealthStatus.DEGRADED
                        message = f"Pool utilization high: {utilization:.1f}%"
                    else:
                        status = HealthStatus.HEALTHY
                        message = "Database connection healthy"
                else:
                    status = HealthStatus.HEALTHY
                    message = "Database connection healthy"

                return HealthCheckResult(
                    name=name,
                    status=status,
                    message=message,
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                    details=details,
                )
            else:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message="Health check query returned unexpected result",
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                    error=f"Unexpected result: {result}",
                )

        except Exception as e:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="Database health check failed",
                duration_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    async def check_object_storage(
        self, storage: Any, name: str = "object_storage"
    ) -> HealthCheckResult:
        """
        Check object storage health.

        Args:
            storage: Object storage instance
            name: Name for the health check

        Returns:
            Health check result
        """
        start_time = time.perf_counter()

        try:
            # Try to write and read a small test object
            test_path = ".health_check/test_" + str(int(time.time()))
            test_data = b"health_check_test"

            # Write test object
            await storage.write(test_path, test_data)

            # Read it back
            read_data = await storage.read(test_path)

            # Clean up
            try:
                await storage.delete(test_path)
            except Exception:
                pass  # Ignore cleanup errors

            if read_data == test_data:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    message="Object storage read/write successful",
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                    details={"storage_type": storage.__class__.__name__},
                )
            else:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message="Object storage data mismatch",
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                    error="Written data doesn't match read data",
                )

        except Exception as e:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="Object storage health check failed",
                duration_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    async def check_metrics(self, name: str = "metrics") -> HealthCheckResult:
        """
        Check metrics collection health.

        Returns:
            Health check result
        """
        start_time = time.perf_counter()

        try:
            metrics = self.metrics_collector.get_all_metrics()

            # Check for recent query activity
            query_stats = metrics.get("queries", {})
            pool_stats = metrics.get("pool", {})

            details = {
                "total_queries": query_stats.get("total_queries", 0),
                "success_rate": query_stats.get("success_rate", 0),
                "pool_utilization": pool_stats.get("current_utilization", 0),
            }

            # Determine status based on metrics
            if query_stats.get("success_rate", 100) < 95:
                status = HealthStatus.DEGRADED
                message = f"Query success rate low: {query_stats['success_rate']:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = "Metrics collection working"

            return HealthCheckResult(
                name=name,
                status=status,
                message=message,
                duration_ms=(time.perf_counter() - start_time) * 1000,
                details=details,
            )

        except Exception as e:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="Metrics health check failed",
                duration_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    async def run_all_checks(self) -> Dict[str, Any]:
        """
        Run all registered health checks.

        Returns:
            Dictionary with overall status and individual check results
        """
        results: List[HealthCheckResult] = []

        # Run sync checks
        for name, check_func in self.checks.items():
            try:
                result = check_func()
                if not isinstance(result, HealthCheckResult):
                    # Convert simple boolean to HealthCheckResult
                    result = HealthCheckResult(
                        name=name,
                        status=HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY,
                        message="Check passed" if result else "Check failed",
                        duration_ms=0,
                    )
                results.append(result)
            except Exception as e:
                results.append(
                    HealthCheckResult(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        message="Check raised exception",
                        duration_ms=0,
                        error=str(e),
                    )
                )

        # Run async checks
        async_tasks = []
        for name, check_func in self.async_checks.items():
            async_tasks.append(self._run_async_check(name, check_func))

        if async_tasks:
            async_results = await asyncio.gather(*async_tasks, return_exceptions=True)
            for result in async_results:
                if isinstance(result, Exception):
                    results.append(
                        HealthCheckResult(
                            name="unknown",
                            status=HealthStatus.UNHEALTHY,
                            message="Check raised exception",
                            duration_ms=0,
                            error=str(result),
                        )
                    )
                else:
                    results.append(result)

        # Determine overall status
        unhealthy_count = sum(1 for r in results if r.status == HealthStatus.UNHEALTHY)
        degraded_count = sum(1 for r in results if r.status == HealthStatus.DEGRADED)

        if unhealthy_count > 0:
            overall_status = HealthStatus.UNHEALTHY
            overall_message = f"{unhealthy_count} checks unhealthy"
        elif degraded_count > 0:
            overall_status = HealthStatus.DEGRADED
            overall_message = f"{degraded_count} checks degraded"
        else:
            overall_status = HealthStatus.HEALTHY
            overall_message = "All checks healthy"

        return {
            "status": overall_status.value,
            "message": overall_message,
            "timestamp": datetime.now().isoformat(),
            "checks": [r.to_dict() for r in results],
            "summary": {
                "total": len(results),
                "healthy": sum(1 for r in results if r.status == HealthStatus.HEALTHY),
                "degraded": degraded_count,
                "unhealthy": unhealthy_count,
            },
        }

    async def _run_async_check(self, name: str, check_func: Callable) -> HealthCheckResult:
        """Run an async health check with error handling."""
        try:
            result = await check_func()
            if not isinstance(result, HealthCheckResult):
                # Convert simple boolean to HealthCheckResult
                result = HealthCheckResult(
                    name=name,
                    status=HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY,
                    message="Check passed" if result else "Check failed",
                    duration_ms=0,
                )
            return result
        except Exception as e:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="Check raised exception",
                duration_ms=0,
                error=str(e),
            )


# Global health checker instance
_global_health_checker = HealthChecker()


def get_health_checker() -> HealthChecker:
    """Get the global health checker instance."""
    return _global_health_checker


def register_health_check(name: str, check_func: Callable, is_async: bool = False):
    """Register a health check with the global health checker."""
    get_health_checker().register_check(name, check_func, is_async)


async def check_system_health() -> Dict[str, Any]:
    """Run all registered health checks and return results."""
    return await get_health_checker().run_all_checks()


# Convenience functions for common health checks
async def check_postgres_health(pool: Any) -> HealthCheckResult:
    """Check PostgreSQL pool health."""
    return await get_health_checker().check_database_pool(pool, "postgres")


async def check_mysql_health(pool: Any) -> HealthCheckResult:
    """Check MySQL pool health."""
    return await get_health_checker().check_database_pool(pool, "mysql")


async def check_sqlserver_health(pool: Any) -> HealthCheckResult:
    """Check SQL Server pool health."""
    return await get_health_checker().check_database_pool(pool, "sqlserver")


async def check_s3_health(storage: Any) -> HealthCheckResult:
    """Check S3 storage health."""
    return await get_health_checker().check_object_storage(storage, "s3")


async def check_local_storage_health(storage: Any) -> HealthCheckResult:
    """Check local storage health."""
    return await get_health_checker().check_object_storage(storage, "local_storage")
