"""
Custom exceptions for ff-storage package.

This module provides specific exception classes for better error handling
and debugging in production environments.
"""

from typing import Any, Dict, Optional


class FFStorageError(Exception):
    """Base exception for all ff-storage errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConnectionError(FFStorageError):
    """Base exception for database connection errors."""

    pass


class ConnectionPoolExhausted(ConnectionError):
    """Raised when connection pool has no available connections."""

    def __init__(self, pool_size: int, timeout: float):
        message = f"Connection pool exhausted (size={pool_size}, timeout={timeout}s)"
        super().__init__(message, {"pool_size": pool_size, "timeout": timeout})


class ConnectionFailure(ConnectionError):
    """Raised when unable to establish database connection."""

    def __init__(self, host: str, port: int, database: str, attempts: int, error: str):
        message = (
            f"Failed to connect to {host}:{port}/{database} after {attempts} attempts: {error}"
        )
        super().__init__(
            message,
            {
                "host": host,
                "port": port,
                "database": database,
                "attempts": attempts,
                "original_error": error,
            },
        )


class CircuitBreakerOpen(ConnectionError):
    """Raised when circuit breaker is open due to repeated failures."""

    def __init__(self, service: str, failure_count: int, reset_timeout: float):
        message = f"Circuit breaker open for {service} (failures={failure_count}, reset_in={reset_timeout}s)"
        super().__init__(
            message,
            {"service": service, "failure_count": failure_count, "reset_timeout": reset_timeout},
        )


class QueryError(FFStorageError):
    """Base exception for query execution errors."""

    pass


class QueryTimeout(QueryError):
    """Raised when a query exceeds the timeout limit."""

    def __init__(self, query: str, timeout: float):
        # Truncate query for readability
        query_preview = query[:200] + "..." if len(query) > 200 else query
        message = f"Query exceeded timeout of {timeout}s: {query_preview}"
        super().__init__(message, {"query": query, "timeout": timeout})


class ValidationError(FFStorageError):
    """Raised when input validation fails."""

    pass


class SQLInjectionAttempt(ValidationError):
    """Raised when potential SQL injection is detected."""

    def __init__(self, query: str, pattern: str):
        message = f"Potential SQL injection detected (pattern: {pattern})"
        super().__init__(message, {"query": query, "pattern": pattern})


class TemporalError(FFStorageError):
    """Base exception for temporal strategy errors."""

    pass


class TemporalStrategyError(TemporalError):
    """Raised when temporal strategy operations fail."""

    def __init__(self, strategy: str, operation: str, error: str):
        message = f"Temporal strategy '{strategy}' failed during {operation}: {error}"
        super().__init__(
            message, {"strategy": strategy, "operation": operation, "original_error": error}
        )


class TemporalVersionConflict(TemporalError):
    """Raised when there's a version conflict in temporal data."""

    def __init__(self, record_id: str, expected_version: int, actual_version: int):
        message = f"Version conflict for record {record_id}: expected v{expected_version}, found v{actual_version}"
        super().__init__(
            message,
            {
                "record_id": record_id,
                "expected_version": expected_version,
                "actual_version": actual_version,
            },
        )


class TenantError(FFStorageError):
    """Base exception for multi-tenant errors."""

    pass


class TenantIsolationError(TenantError):
    """Raised when tenant isolation is violated."""

    def __init__(self, requested_tenant: str, actual_tenant: str, operation: str):
        message = f"Tenant isolation violation: {operation} requested for tenant {requested_tenant} but record belongs to {actual_tenant}"
        super().__init__(
            message,
            {
                "requested_tenant": requested_tenant,
                "actual_tenant": actual_tenant,
                "operation": operation,
            },
        )


class TenantNotConfigured(TenantError):
    """Raised when tenant is required but not configured."""

    def __init__(self, model_class: str):
        message = f"Model {model_class} requires tenant_id but none was provided"
        super().__init__(message, {"model_class": model_class})


class ObjectStorageError(FFStorageError):
    """Base exception for object storage errors."""

    pass


class ObjectNotFound(ObjectStorageError):
    """Raised when requested object doesn't exist."""

    def __init__(self, path: str, storage_type: str):
        message = f"Object not found at path '{path}' in {storage_type} storage"
        super().__init__(message, {"path": path, "storage_type": storage_type})


class StorageQuotaExceeded(ObjectStorageError):
    """Raised when storage quota is exceeded."""

    def __init__(self, used: int, limit: int):
        message = f"Storage quota exceeded: used {used} bytes, limit {limit} bytes"
        super().__init__(message, {"used": used, "limit": limit})


class StreamingError(ObjectStorageError):
    """Raised when streaming operations fail."""

    def __init__(self, path: str, operation: str, error: str):
        message = f"Streaming {operation} failed for '{path}': {error}"
        super().__init__(message, {"path": path, "operation": operation, "original_error": error})


class ConfigurationError(FFStorageError):
    """Raised when configuration is invalid."""

    def __init__(self, component: str, issue: str):
        message = f"Configuration error in {component}: {issue}"
        super().__init__(message, {"component": component, "issue": issue})


class MigrationError(FFStorageError):
    """Raised when database migration fails."""

    def __init__(self, version: str, operation: str, error: str):
        message = f"Migration {version} failed during {operation}: {error}"
        super().__init__(
            message, {"version": version, "operation": operation, "original_error": error}
        )


class ResourceExhausted(FFStorageError):
    """Raised when a resource limit is reached."""

    def __init__(self, resource: str, limit: Any, current: Any):
        message = f"Resource '{resource}' exhausted: current={current}, limit={limit}"
        super().__init__(message, {"resource": resource, "limit": limit, "current": current})


class ConcurrencyError(FFStorageError):
    """Raised when concurrent operations conflict."""

    def __init__(self, operation: str, resource: str):
        message = f"Concurrent {operation} conflict on resource '{resource}'"
        super().__init__(message, {"operation": operation, "resource": resource})


class RateLimitExceeded(FFStorageError):
    """Raised when rate limit is exceeded."""

    def __init__(self, operation: str, limit: int, window: int):
        message = f"Rate limit exceeded for {operation}: {limit} requests per {window}s"
        super().__init__(message, {"operation": operation, "limit": limit, "window": window})
