"""
ff-storage utility modules.

This package provides utilities for retry logic, metrics collection,
SQL validation, and other cross-cutting concerns.
"""

from .metrics import (
    AsyncTimerContext,
    ConnectionPoolMetrics,
    MetricsCollector,
    OperationMetric,
    QueryMetric,
    TimerContext,
    async_timer,
    get_global_collector,
    set_global_collector,
    timer,
)
from .postgres import (
    build_column_list,
    build_insert_query,
    build_update_set_clause,
    build_where_clause,
    quote_identifier,
)
from .retry import (
    DATABASE_RETRY,
    DEFAULT_RETRY,
    NETWORK_RETRY,
    CircuitBreaker,
    CircuitState,
    RetryPolicy,
    exponential_backoff,
    retry,
    retry_async,
)
from .validation import (
    SQLValidator,
    get_validator,
    sanitize_like_pattern,
    set_validator,
    validate_identifier,
    validate_query,
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
    # PostgreSQL utilities
    "quote_identifier",
    "build_column_list",
    "build_insert_query",
    "build_update_set_clause",
    "build_where_clause",
]
