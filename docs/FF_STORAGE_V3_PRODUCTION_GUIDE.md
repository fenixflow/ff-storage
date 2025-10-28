# ff-storage v3.3.0 Production Deployment Guide

## Overview

ff-storage v3.3.0 is production-ready with comprehensive resilience, monitoring, and caching features. This guide covers deployment best practices, configuration recommendations, and monitoring setup for POC and production environments.

> **🔥 v3.3.0 Update**: Critical schema sync bug fix. If using schema sync (v2.0+), upgrade immediately to eliminate false positives causing unnecessary index recreation.

## Quick Start for POC

### 1. Installation

```bash
# Install with all dependencies
pip install -e "./ff-storage[dev]"

# Or from GitLab
pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-storage
```

### 2. Basic Configuration

```python
from ff_storage import PostgresPool, TemporalRepository, PydanticModel
from ff_storage.temporal.registry import get_strategy
from ff_storage.temporal.enums import TemporalStrategyType

# Define your model
class Product(PydanticModel):
    __table_name__ = "products"
    __temporal_strategy__ = "copy_on_change"  # Audit trail
    __multi_tenant__ = True

    name: str
    price: float
    description: str

# Setup database pool with production features
db_pool = PostgresPool(
    dbname="fenix_poc",
    user="fenix_user",
    password="secure_password",
    host="localhost",
    port=5432,
    min_size=10,
    max_size=20,
    query_timeout=30000,  # 30 seconds
    collect_metrics=True,  # Enable monitoring
)

# Initialize pool at startup
await db_pool.connect()

# Create repository with caching
strategy = get_strategy(TemporalStrategyType.COPY_ON_CHANGE, Product)
repo = TemporalRepository(
    Product,
    db_pool,
    strategy,
    tenant_id=tenant_id,
    cache_enabled=True,
    cache_ttl=300,  # 5 minute cache
)

# Use repository
product = await repo.create(
    Product(name="Widget", price=99.99, description="A great widget"),
    user_id=current_user.id
)
```

## Production Configuration

### Database Connection Pool

```python
# Production-optimized configuration
db_pool = PostgresPool(
    # Connection settings
    dbname=os.environ["DB_NAME"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    host=os.environ["DB_HOST"],
    port=int(os.environ.get("DB_PORT", 5432)),

    # Pool sizing (adjust based on expected concurrency)
    min_size=20,  # Minimum connections to maintain
    max_size=50,  # Maximum connections allowed

    # Timeouts (in milliseconds)
    query_timeout=30000,  # 30 seconds for queries
    connection_timeout=10,  # 10 seconds to acquire connection
    pool_recycle=3600,  # Recycle connections after 1 hour
    max_inactive_connection_lifetime=300.0,  # 5 minutes idle timeout

    # Features
    validate_queries=True,  # SQL injection protection
    collect_metrics=True,   # Enable monitoring
)
```

### FastAPI Integration

```python
from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager

app = FastAPI()

# Global pool instance
db_pool: Optional[PostgresPool] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage pool lifecycle."""
    global db_pool

    # Startup
    db_pool = PostgresPool(**config)
    await db_pool.connect()

    # Register health check
    from ff_storage.health import register_health_check
    register_health_check(
        "database",
        lambda: db_pool.check_health(),
        is_async=True
    )

    yield

    # Shutdown
    await db_pool.disconnect()

app = FastAPI(lifespan=lifespan)

# Dependency injection
async def get_db_pool() -> PostgresPool:
    if not db_pool:
        raise RuntimeError("Database pool not initialized")
    return db_pool

# Health endpoint
@app.get("/health")
async def health_check(pool: PostgresPool = Depends(get_db_pool)):
    result = await pool.check_health()
    return {
        "status": result.status.value,
        "database": result.to_dict()
    }
```

## Monitoring Setup

### 1. Metrics Collection

```python
from ff_storage.utils.metrics import get_global_collector

# Get metrics
collector = get_global_collector()
metrics = collector.get_all_metrics()

# Expose metrics endpoint
@app.get("/metrics")
async def get_metrics():
    return {
        "queries": collector.get_query_statistics(window_minutes=5),
        "pool": collector.get_pool_statistics(),
        "operations": {
            op: collector.get_timing_statistics(f"operation.{op}")
            for op in ["create", "update", "delete", "get"]
        }
    }
```

### 2. Prometheus Integration

```python
# prometheus_exporter.py
from prometheus_client import Gauge, Counter, Histogram
from ff_storage.utils.metrics import get_global_collector

# Define Prometheus metrics
query_duration = Histogram('ff_storage_query_duration_seconds', 'Query execution time')
query_total = Counter('ff_storage_queries_total', 'Total queries executed', ['status'])
pool_utilization = Gauge('ff_storage_pool_utilization', 'Connection pool utilization %')

def export_metrics():
    """Export metrics to Prometheus."""
    collector = get_global_collector()
    stats = collector.get_all_metrics()

    # Update Prometheus metrics
    pool_utilization.set(stats['pool']['current_utilization'])

    for query in collector.query_metrics:
        query_duration.observe(query.duration)
        query_total.labels(status='success' if query.success else 'failed').inc()
```

### 3. Logging Configuration

```python
import logging
import sys

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/var/log/ff-storage.log')
    ]
)

# Enable detailed logging for debugging
logging.getLogger('ff_storage').setLevel(logging.DEBUG)
```

## Error Handling

### Resilience Configuration

```python
from ff_storage.exceptions import (
    ConnectionPoolExhausted,
    QueryTimeout,
    TenantIsolationError,
    TemporalStrategyError
)

# Handle specific errors
try:
    product = await repo.get(product_id)
except ConnectionPoolExhausted as e:
    # Pool is exhausted, consider scaling
    logger.error(f"Pool exhausted: {e}")
    raise HTTPException(503, "Service temporarily unavailable")
except QueryTimeout as e:
    # Query took too long
    logger.warning(f"Query timeout: {e}")
    raise HTTPException(504, "Request timeout")
except TenantIsolationError as e:
    # Security violation
    logger.error(f"Tenant violation: {e}")
    raise HTTPException(403, "Access denied")
except TemporalStrategyError as e:
    # Data operation failed
    logger.error(f"Temporal error: {e}")
    raise HTTPException(500, "Internal error")
```

### Circuit Breaker Status

```python
# Monitor circuit breaker status
@app.get("/circuit-breakers")
async def circuit_breaker_status(pool: PostgresPool = Depends(get_db_pool)):
    return {
        "database": {
            "state": pool._circuit_breaker.state.value,
            "failure_count": pool._circuit_breaker.failure_count,
            "is_open": pool._circuit_breaker.is_open
        }
    }
```

## Performance Optimization

### 1. Caching Strategy

```python
# Configure caching per repository
repo = TemporalRepository(
    Model,
    db_pool,
    strategy,
    tenant_id=tenant_id,
    cache_enabled=True,
    cache_ttl=300,  # 5 minutes for frequently accessed data
)

# Invalidate cache when needed
await repo.invalidate_cache()  # Clear all
await repo.invalidate_cache("list")  # Clear list queries only
```

### 2. Batch Operations

```python
# Efficient batch operations
products = [Product(...) for _ in range(1000)]

# Create in batches
created = await repo.create_many(
    products,
    user_id=user_id,
    batch_size=100  # Process 100 at a time
)

# Batch fetch
ids = [p.id for p in created]
products_map = await repo.get_many(ids)
```

### 3. Query Optimization

```python
# Use indexes for temporal queries
CREATE INDEX idx_products_tenant_valid ON products(tenant_id, valid_to)
WHERE valid_to IS NULL;  -- Current records only

# For copy_on_change audit queries
CREATE INDEX idx_products_audit_record ON products_audit(record_id, changed_at);
```

## Security Best Practices

### 1. SQL Injection Protection

```python
# Validation is automatic but can be customized
from ff_storage.utils.validation import SQLValidator

validator = SQLValidator(
    strict_mode=True,
    allow_comments=False,
    custom_dangerous_patterns=[
        (r'\bEXEC\b', 'EXEC command not allowed'),
    ]
)

# Set custom validator
from ff_storage.utils import set_validator
set_validator(validator)
```

### 2. Tenant Isolation

```python
# Enable Row Level Security (PostgreSQL)
async def enable_rls(pool: PostgresPool, table: str):
    await pool.execute(f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;

        CREATE POLICY tenant_isolation ON {table}
            FOR ALL
            USING (tenant_id = current_setting('app.tenant_id')::uuid);
    """)

# Set tenant context for each request
async def set_tenant_context(pool: PostgresPool, tenant_id: UUID):
    await pool.execute(
        "SET LOCAL app.tenant_id = $1",
        str(tenant_id)
    )
```

## Deployment Checklist

### Pre-Production

- [ ] **Load Testing**: Test with expected traffic volume
  ```bash
  # Using locust
  locust -f load_tests.py --host=http://localhost:8000
  ```

- [ ] **Connection Pool Tuning**: Adjust based on load test results
  ```python
  # Monitor pool metrics during load test
  pool_stats = collector.get_pool_statistics()
  if pool_stats['exhaustion_count'] > 0:
      # Increase max_size
  ```

- [ ] **Database Indexes**: Create necessary indexes
  ```sql
  -- Temporal queries
  CREATE INDEX idx_temporal ON products(id, valid_from, valid_to);

  -- Multi-tenant queries
  CREATE INDEX idx_tenant ON products(tenant_id, deleted_at);
  ```

- [ ] **Security Audit**: Run security scan
  ```bash
  # Check for SQL injection vulnerabilities
  sqlmap -u "http://localhost:8000/api/products" --batch
  ```

### Production Deployment

1. **Environment Variables**
   ```bash
   export DB_HOST=prod-db.internal
   export DB_NAME=fenix_production
   export DB_USER=fenix_app
   export DB_PASSWORD=$(vault read -field=password secret/db)
   export METRICS_ENABLED=true
   export CACHE_TTL=300
   ```

2. **Health Checks**
   ```yaml
   # kubernetes/deployment.yaml
   livenessProbe:
     httpGet:
       path: /health
       port: 8000
     initialDelaySeconds: 30
     periodSeconds: 10

   readinessProbe:
     httpGet:
       path: /health
       port: 8000
     initialDelaySeconds: 5
     periodSeconds: 5
   ```

3. **Monitoring Alerts**
   ```yaml
   # prometheus/alerts.yaml
   - alert: HighQueryLatency
     expr: ff_storage_query_duration_seconds > 1
     for: 5m
     annotations:
       summary: "High query latency detected"

   - alert: ConnectionPoolExhausted
     expr: ff_storage_pool_utilization > 90
     for: 2m
     annotations:
       summary: "Connection pool near exhaustion"
   ```

4. **Backup Strategy**
   ```bash
   # Backup before deployment
   pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME > backup_$(date +%Y%m%d).sql

   # For temporal data, include audit tables
   pg_dump -t '*_audit' -t '*_versions' ...
   ```

## Troubleshooting

### Common Issues

1. **Pool Exhaustion**
   - Symptom: `ConnectionPoolExhausted` errors
   - Solution: Increase `max_size` or optimize query patterns

2. **Slow Queries**
   - Symptom: `QueryTimeout` errors
   - Solution: Add indexes, optimize queries, increase `query_timeout`

3. **Circuit Breaker Open**
   - Symptom: `CircuitBreakerOpen` errors
   - Solution: Check database health, reset circuit breaker if needed

4. **Cache Invalidation**
   - Symptom: Stale data being returned
   - Solution: Reduce `cache_ttl` or invalidate on updates

### Debug Mode

```python
# Enable debug logging
import logging
logging.getLogger('ff_storage').setLevel(logging.DEBUG)

# Disable caching for debugging
repo = TemporalRepository(..., cache_enabled=False)

# Force circuit breaker reset
pool._circuit_breaker.reset()
```

## Support

For POC support and questions:
- Review integration tests in `tests/integration/`
- Check examples in `docs/examples/`
- Consult the main documentation in `docs/README.md`

The system is ready for POC deployment with all production features enabled. Monitor metrics closely during initial deployment and adjust configuration based on actual usage patterns.