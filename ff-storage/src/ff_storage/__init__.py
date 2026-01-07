"""
ff-storage: Production-ready database and file storage operations for Fenixflow applications.

v3.0.0: Enhanced with resilience, monitoring, caching, and temporal data management!

Features:
- Pydantic ORM with automatic schema generation
- Temporal data strategies (none, copy_on_change, scd2)
- Connection resilience with retry and circuit breakers
- Query result caching with TTL
- Comprehensive metrics collection
- Health check support
- Multi-tenant data isolation
- SQL injection protection
"""

# Version is read from package metadata (pyproject.toml is the single source of truth)
try:
    from importlib.metadata import version

    __version__ = version("ff-storage")
except Exception:
    __version__ = "3.0.0"

# Database exports
from .db import AsyncSchemaManager, MySQL, MySQLPool, Postgres, PostgresPool, SchemaManager

# Exceptions (ENHANCED in v3.0)
from .exceptions import (
    CircuitBreakerOpen,
    ConcurrencyError,
    ConfigurationError,
    ConnectionError,
    ConnectionFailure,
    ConnectionPoolExhausted,
    FFStorageError,
    ObjectNotFound,
    ObjectStorageError,
    QueryError,
    QueryTimeout,
    SQLInjectionAttempt,
    TemporalError,
    TemporalStrategyError,
    TemporalVersionConflict,
    TenantError,
    TenantIsolationError,
    TenantNotConfigured,
)

# Health checks (NEW in v3.0)
from .health import (
    HealthChecker,
    HealthCheckResult,
    HealthStatus,
    check_system_health,
    get_health_checker,
)

# Object storage exports
from .object import AzureBlobObjectStorage, LocalObjectStorage, ObjectStorage, S3ObjectStorage

# Pydantic ORM (NEW in v3.0)
from .pydantic_support.base import PydanticModel
from .pydantic_support.field_metadata import Field
from .pydantic_support.repository import PydanticRepository

# Query Builder (NEW in v4.7)
from .query import (
    AggregateExpression,
    F,
    FieldProxy,
    FilterExpression,
    GroupByClause,
    OrderByClause,
    Query,
    func,
)

# Relationships (NEW in v4.7)
from .relationships import (
    Relationship,
    RelationshipConfig,
    RelationshipLoader,
    RelationshipProxy,
    RelationshipRegistry,
    RelationType,
)

# Temporal strategies (NEW in v3.0)
from .temporal.enums import TemporalStrategyType
from .temporal.registry import get_strategy
from .temporal.repository_base import TemporalRepository
from .temporal.validation import TemporalValidator, ValidationError

# Transactions (NEW in v4.8)
from .transactions import (
    IsolationLevel,
    Savepoint,
    SavepointAlreadyReleased,
    SavepointError,
    SavepointNotFound,
    Transaction,
    TransactionAlreadyStarted,
    TransactionBoundRepository,
    TransactionClosed,
    TransactionError,
    TransactionNotStarted,
    UnitOfWork,
)

# Utilities (NEW in v3.0)
from .utils import (  # Retry utilities; Metrics utilities; Validation utilities
    DATABASE_RETRY,
    NETWORK_RETRY,
    CircuitBreaker,
    MetricsCollector,
    RetryPolicy,
    SQLValidator,
    async_timer,
    exponential_backoff,
    get_global_collector,
    retry,
    retry_async,
    set_global_collector,
    timer,
    validate_identifier,
    validate_query,
)

# ERD Module (NEW in v4.9)
from .erd import (
    ERDBuilder,
    ERDColumn,
    ERDRelationship,
    ERDResponse,
    ERDTable,
    to_mermaid,
    to_mermaid_compact,
)

# Mock Data Generation (NEW in v4.9)
from .mock import (
    DEFAULT_NAME_PATTERNS,
    ExampleExtension,
    FieldMeta,
    GeneratorExtension,
    GeneratorFunc,
    MockFactory,
    NAMED_PATTERNS,
    RelationshipCascadeManager,
    TYPE_GENERATORS,
    ValueGeneratorRegistry,
    get_named_pattern_generator,
    get_pattern_generator,
    get_type_generator,
)

__all__ = [
    # Version
    "__version__",
    # Pydantic ORM
    "PydanticModel",
    "PydanticRepository",
    "Field",
    # Query Builder
    "Query",
    "FilterExpression",
    "FieldProxy",
    "F",
    "OrderByClause",
    "AggregateExpression",
    "GroupByClause",
    "func",
    # Relationships
    "Relationship",
    "RelationshipConfig",
    "RelationshipLoader",
    "RelationshipProxy",
    "RelationshipRegistry",
    "RelationType",
    # Transactions
    "Transaction",
    "Savepoint",
    "IsolationLevel",
    "UnitOfWork",
    "TransactionBoundRepository",
    "TransactionError",
    "TransactionNotStarted",
    "TransactionAlreadyStarted",
    "TransactionClosed",
    "SavepointError",
    "SavepointNotFound",
    "SavepointAlreadyReleased",
    # Temporal
    "TemporalStrategyType",
    "TemporalRepository",
    "TemporalValidator",
    "ValidationError",
    "get_strategy",
    # PostgreSQL
    "Postgres",
    "PostgresPool",
    # MySQL
    "MySQL",
    "MySQLPool",
    # Schema Management
    "SchemaManager",
    "AsyncSchemaManager",
    # Object Storage
    "ObjectStorage",
    "LocalObjectStorage",
    "S3ObjectStorage",
    "AzureBlobObjectStorage",
    # Exceptions
    "FFStorageError",
    "ConnectionError",
    "ConnectionPoolExhausted",
    "ConnectionFailure",
    "CircuitBreakerOpen",
    "QueryError",
    "QueryTimeout",
    "SQLInjectionAttempt",
    "TemporalError",
    "TemporalStrategyError",
    "TemporalVersionConflict",
    "TenantError",
    "TenantIsolationError",
    "TenantNotConfigured",
    "ObjectStorageError",
    "ObjectNotFound",
    "ConfigurationError",
    "ConcurrencyError",
    # Utilities
    "CircuitBreaker",
    "RetryPolicy",
    "exponential_backoff",
    "retry",
    "retry_async",
    "DATABASE_RETRY",
    "NETWORK_RETRY",
    "MetricsCollector",
    "get_global_collector",
    "set_global_collector",
    "timer",
    "async_timer",
    "SQLValidator",
    "validate_query",
    "validate_identifier",
    # Health
    "HealthStatus",
    "HealthCheckResult",
    "HealthChecker",
    "get_health_checker",
    "check_system_health",
    # ERD
    "ERDBuilder",
    "ERDTable",
    "ERDColumn",
    "ERDRelationship",
    "ERDResponse",
    "to_mermaid",
    "to_mermaid_compact",
    # Mock Data Generation
    "MockFactory",
    "ValueGeneratorRegistry",
    "FieldMeta",
    "GeneratorExtension",
    "ExampleExtension",
    "GeneratorFunc",
    "RelationshipCascadeManager",
    "DEFAULT_NAME_PATTERNS",
    "NAMED_PATTERNS",
    "TYPE_GENERATORS",
    "get_pattern_generator",
    "get_named_pattern_generator",
    "get_type_generator",
]
