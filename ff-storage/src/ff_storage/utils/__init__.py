"""
ff-storage utility modules.

This package provides utilities for retry logic, metrics collection,
SQL validation, and other cross-cutting concerns.
"""

from .retry import (
    CircuitBreaker,
    CircuitState,
    RetryPolicy,
    exponential_backoff,
    retry,
    retry_async,
    DEFAULT_RETRY,
    DATABASE_RETRY,
    NETWORK_RETRY,
)

from .metrics import (
    MetricsCollector,
    QueryMetric,
    ConnectionPoolMetrics,
    OperationMetric,
    TimerContext,
    AsyncTimerContext,
    get_global_collector,
    set_global_collector,
    timer,
    async_timer,
)

from .validation import (
    SQLValidator,
    get_validator,
    set_validator,
    validate_query,
    validate_identifier,
    sanitize_like_pattern,
)

__all__ = [
    # Retry utilities
    "CircuitBreaker",
    "CircuitState",
    "RetryPolicy",
    "exponential_backoff",
    "retry",
    "retry_async",
    "DEFAULT_RETRY",
    "DATABASE_RETRY",
    "NETWORK_RETRY",
    # Metrics utilities
    "MetricsCollector",
    "QueryMetric",
    "ConnectionPoolMetrics",
    "OperationMetric",
    "TimerContext",
    "AsyncTimerContext",
    "get_global_collector",
    "set_global_collector",
    "timer",
    "async_timer",
    # Validation utilities
    "SQLValidator",
    "get_validator",
    "set_validator",
    "validate_query",
    "validate_identifier",
    "sanitize_like_pattern",
]
