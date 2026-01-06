"""
Metrics collection for monitoring and observability.

This module provides utilities for collecting performance metrics,
query statistics, and resource usage information.
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Deque, Dict, List, Optional


class MetricType(Enum):
    """Types of metrics that can be collected."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class QueryMetric:
    """Metrics for a single query execution."""

    query: str
    duration: float
    timestamp: datetime
    rows_affected: Optional[int] = None
    success: bool = True
    error: Optional[str] = None
    connection_id: Optional[str] = None
    tenant_id: Optional[str] = None

    @property
    def is_slow(self, threshold: float = 1.0) -> bool:
        """Check if query is considered slow."""
        return self.duration > threshold


@dataclass
class ConnectionPoolMetrics:
    """Metrics for database connection pool."""

    pool_size: int
    active_connections: int
    idle_connections: int
    waiting_requests: int
    total_connections_created: int
    total_connections_closed: int
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def utilization(self) -> float:
        """Calculate pool utilization percentage."""
        if self.pool_size == 0:
            return 0.0
        return (self.active_connections / self.pool_size) * 100

    @property
    def is_exhausted(self) -> bool:
        """Check if pool is exhausted."""
        return self.active_connections >= self.pool_size and self.waiting_requests > 0


@dataclass
class OperationMetric:
    """Generic operation metric."""

    operation: str
    duration: float
    timestamp: datetime
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MetricsCollector:
    """
    Central metrics collection and aggregation.

    Collects various metrics and provides aggregated statistics.
    """

    def __init__(
        self,
        max_history: int = 10000,
        slow_query_threshold: float = 1.0,
        enable_detailed_logging: bool = False,
    ):
        """
        Initialize metrics collector.

        Args:
            max_history: Maximum number of metrics to keep in history
            slow_query_threshold: Threshold for slow query detection (seconds)
            enable_detailed_logging: Enable detailed metric logging
        """
        self.max_history = max_history
        self.slow_query_threshold = slow_query_threshold
        self.enable_detailed_logging = enable_detailed_logging

        # Thread-safe collections
        self._lock = threading.RLock()

        # Query metrics
        self.query_metrics: Deque[QueryMetric] = deque(maxlen=max_history)
        self.slow_queries: Deque[QueryMetric] = deque(maxlen=100)

        # Connection pool metrics
        self.pool_metrics: Deque[ConnectionPoolMetrics] = deque(maxlen=1000)

        # Operation metrics
        self.operation_metrics: Dict[str, Deque[OperationMetric]] = {}

        # Counters
        self.counters: Dict[str, int] = {}

        # Gauges (current values)
        self.gauges: Dict[str, float] = {}

        # Timing statistics
        self.timers: Dict[str, List[float]] = {}

        self.logger = logging.getLogger(__name__)

    def record_query(
        self,
        query: str,
        duration: float,
        rows_affected: Optional[int] = None,
        success: bool = True,
        error: Optional[str] = None,
        connection_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ):
        """Record query execution metrics."""
        metric = QueryMetric(
            query=query,
            duration=duration,
            timestamp=datetime.now(),
            rows_affected=rows_affected,
            success=success,
            error=error,
            connection_id=connection_id,
            tenant_id=tenant_id,
        )

        with self._lock:
            self.query_metrics.append(metric)

            # Track slow queries separately
            if duration > self.slow_query_threshold:
                self.slow_queries.append(metric)
                if self.enable_detailed_logging:
                    self.logger.warning(f"Slow query detected ({duration:.2f}s): {query[:100]}...")

            # Update counters
            if success:
                self.increment("queries.success")
            else:
                self.increment("queries.failed")

    def record_pool_metrics(
        self,
        pool_size: int,
        active: int,
        idle: int,
        waiting: int,
        total_created: int,
        total_closed: int,
    ):
        """Record connection pool metrics."""
        metric = ConnectionPoolMetrics(
            pool_size=pool_size,
            active_connections=active,
            idle_connections=idle,
            waiting_requests=waiting,
            total_connections_created=total_created,
            total_connections_closed=total_closed,
        )

        with self._lock:
            self.pool_metrics.append(metric)

            # Update gauges
            self.set_gauge("pool.size", pool_size)
            self.set_gauge("pool.active", active)
            self.set_gauge("pool.idle", idle)
            self.set_gauge("pool.waiting", waiting)
            self.set_gauge("pool.utilization", metric.utilization)

            # Alert on pool exhaustion
            if metric.is_exhausted and self.enable_detailed_logging:
                self.logger.warning(
                    f"Connection pool exhausted: {active}/{pool_size} active, {waiting} waiting"
                )

    def record_operation(
        self,
        operation: str,
        duration: float,
        success: bool = True,
        error: Optional[str] = None,
        **metadata,
    ):
        """Record generic operation metrics."""
        metric = OperationMetric(
            operation=operation,
            duration=duration,
            timestamp=datetime.now(),
            success=success,
            error=error,
            metadata=metadata,
        )

        with self._lock:
            if operation not in self.operation_metrics:
                self.operation_metrics[operation] = deque(maxlen=self.max_history)
            self.operation_metrics[operation].append(metric)

            # Update timer
            self.record_timing(f"operation.{operation}", duration)

            # Update counters
            counter_key = f"operation.{operation}.{'success' if success else 'failed'}"
            self.increment(counter_key)

    def increment(self, key: str, value: int = 1):
        """Increment a counter."""
        with self._lock:
            self.counters[key] = self.counters.get(key, 0) + value

    def decrement(self, key: str, value: int = 1):
        """Decrement a counter."""
        self.increment(key, -value)

    def set_gauge(self, key: str, value: float):
        """Set a gauge value."""
        with self._lock:
            self.gauges[key] = value

    def record_timing(self, key: str, duration: float):
        """Record timing information."""
        with self._lock:
            if key not in self.timers:
                self.timers[key] = []
            self.timers[key].append(duration)

            # Keep only recent timings to prevent memory growth
            if len(self.timers[key]) > 1000:
                self.timers[key] = self.timers[key][-1000:]

    def get_query_statistics(self, window_minutes: int = 60) -> Dict[str, Any]:
        """Get aggregated query statistics."""
        with self._lock:
            cutoff = datetime.now() - timedelta(minutes=window_minutes)
            recent_queries = [q for q in self.query_metrics if q.timestamp > cutoff]

            if not recent_queries:
                return {
                    "total_queries": 0,
                    "success_rate": 0.0,
                    "avg_duration": 0.0,
                    "slow_queries": 0,
                }

            successful = [q for q in recent_queries if q.success]
            durations = [q.duration for q in recent_queries]

            return {
                "total_queries": len(recent_queries),
                "successful_queries": len(successful),
                "failed_queries": len(recent_queries) - len(successful),
                "success_rate": (len(successful) / len(recent_queries)) * 100,
                "avg_duration": sum(durations) / len(durations),
                "min_duration": min(durations),
                "max_duration": max(durations),
                "slow_queries": len(
                    [q for q in recent_queries if q.duration > self.slow_query_threshold]
                ),
                "window_minutes": window_minutes,
            }

    def get_pool_statistics(self) -> Dict[str, Any]:
        """Get current connection pool statistics."""
        with self._lock:
            if not self.pool_metrics:
                return {"current_utilization": 0.0, "avg_utilization": 0.0, "exhaustion_count": 0}

            latest = self.pool_metrics[-1]
            recent = list(self.pool_metrics)[-100:]  # Last 100 samples

            exhaustion_count = sum(1 for m in recent if m.is_exhausted)
            avg_utilization = sum(m.utilization for m in recent) / len(recent)

            return {
                "pool_size": latest.pool_size,
                "active_connections": latest.active_connections,
                "idle_connections": latest.idle_connections,
                "waiting_requests": latest.waiting_requests,
                "current_utilization": latest.utilization,
                "avg_utilization": avg_utilization,
                "exhaustion_count": exhaustion_count,
                "total_connections_created": latest.total_connections_created,
                "total_connections_closed": latest.total_connections_closed,
            }

    def get_timing_statistics(self, key: str) -> Dict[str, float]:
        """Get timing statistics for a specific key."""
        with self._lock:
            timings = self.timers.get(key, [])
            if not timings:
                return {
                    "count": 0,
                    "mean": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                    "p50": 0.0,
                    "p95": 0.0,
                    "p99": 0.0,
                }

            sorted_timings = sorted(timings)
            count = len(sorted_timings)

            def percentile(p):
                k = (count - 1) * p
                f = int(k)
                c = k - f
                if f + 1 < count:
                    return sorted_timings[f] * (1 - c) + sorted_timings[f + 1] * c
                return sorted_timings[f]

            return {
                "count": count,
                "mean": sum(sorted_timings) / count,
                "min": sorted_timings[0],
                "max": sorted_timings[-1],
                "p50": percentile(0.50),
                "p95": percentile(0.95),
                "p99": percentile(0.99),
            }

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary."""
        with self._lock:
            return {
                "timestamp": datetime.now().isoformat(),
                "queries": self.get_query_statistics(),
                "pool": self.get_pool_statistics(),
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "timers": {key: self.get_timing_statistics(key) for key in self.timers},
            }

    def reset(self):
        """Reset all metrics."""
        with self._lock:
            self.query_metrics.clear()
            self.slow_queries.clear()
            self.pool_metrics.clear()
            self.operation_metrics.clear()
            self.counters.clear()
            self.gauges.clear()
            self.timers.clear()


class TimerContext:
    """Context manager for timing operations."""

    def __init__(self, collector: MetricsCollector, operation: str):
        self.collector = collector
        self.operation = operation
        self.start_time = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.perf_counter() - self.start_time
        success = exc_type is None
        error = str(exc_val) if exc_val else None
        self.collector.record_operation(self.operation, duration, success=success, error=error)


class AsyncTimerContext:
    """Async context manager for timing operations."""

    def __init__(self, collector: MetricsCollector, operation: str):
        self.collector = collector
        self.operation = operation
        self.start_time = None

    async def __aenter__(self):
        self.start_time = time.perf_counter()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration = time.perf_counter() - self.start_time
        success = exc_type is None
        error = str(exc_val) if exc_val else None
        self.collector.record_operation(self.operation, duration, success=success, error=error)


# Global metrics collector instance (can be replaced with custom instance)
_global_collector = MetricsCollector()


def get_global_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    return _global_collector


def set_global_collector(collector: MetricsCollector):
    """Set the global metrics collector instance."""
    global _global_collector
    _global_collector = collector


def timer(operation: str) -> TimerContext:
    """Create a timer context for an operation."""
    return TimerContext(get_global_collector(), operation)


def async_timer(operation: str) -> AsyncTimerContext:
    """Create an async timer context for an operation."""
    return AsyncTimerContext(get_global_collector(), operation)
