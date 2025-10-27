# Temporal Strategies API Reference

Complete documentation for ff-storage's temporal data management strategies.

## Table of Contents

- [Overview](#overview)
- [Strategy Types](#strategy-types)
- [None Strategy](#none-strategy)
- [Copy-on-Change Strategy](#copy-on-change-strategy)
- [SCD2 Strategy](#scd2-strategy)
- [Strategy Selection Guide](#strategy-selection-guide)
- [API Methods by Strategy](#api-methods-by-strategy)

## Overview

Temporal strategies determine how ff-storage tracks changes to your data over time.

```python
class Product(PydanticModel):
    __temporal_strategy__ = "copy_on_change"  # Choose strategy

    name: str
    price: Decimal
```

## Strategy Types

| Strategy | Description | Use Case | Storage Overhead |
|----------|-------------|----------|------------------|
| `"none"` | No history tracking | Current state only | Minimal |
| `"copy_on_change"` | Field-level audit trail | Compliance, debugging | Medium |
| `"scd2"` | Immutable versions | Time travel, analytics | High |

## None Strategy

Standard CRUD with no temporal tracking beyond `created_at` and `updated_at`.

### Features

- ✅ Direct INSERT/UPDATE/DELETE
- ✅ Soft delete support
- ✅ Multi-tenant isolation
- ✅ Lowest storage overhead
- ❌ No audit trail
- ❌ No time travel

### Model Configuration

```python
class User(PydanticModel):
    __table_name__ = "users"
    __temporal_strategy__ = "none"
    __soft_delete__ = True  # Optional
    __multi_tenant__ = True  # Optional

    email: str
    name: str
```

### Injected Fields

```python
# Always injected
id: UUID
created_at: datetime
updated_at: datetime
created_by: Optional[UUID]
updated_by: Optional[UUID]

# If multi_tenant=True
tenant_id: UUID

# If soft_delete=True
deleted_at: Optional[datetime]
deleted_by: Optional[UUID]
```

### Operations

```python
repo = PydanticRepository(User, db_pool, tenant_id=tenant_id)

# Create
user = await repo.create(User(email="john@example.com", name="John"))

# Update - direct modification
updated = await repo.update(user.id, User(email="john@example.com", name="John Doe"))

# Delete - soft or hard based on configuration
await repo.delete(user.id)

# Restore (if soft_delete=True)
restored = await repo.restore(user.id)
```

### Database Impact

```sql
-- Single table
CREATE TABLE users (
    id UUID PRIMARY KEY,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    tenant_id UUID,  -- if multi-tenant
    deleted_at TIMESTAMP,  -- if soft delete
    -- user fields
    email VARCHAR(255),
    name VARCHAR(255)
);
```

## Copy-on-Change Strategy

Tracks field-level changes in an audit table.

### Features

- ✅ Complete audit trail
- ✅ Field-level change tracking
- ✅ Change attribution (who, when)
- ✅ Row-level locking
- ✅ Efficient storage (only changes)
- ❌ No time travel to specific dates

### Model Configuration

```python
class Product(PydanticModel):
    __table_name__ = "products"
    __temporal_strategy__ = "copy_on_change"
    __soft_delete__ = True
    __multi_tenant__ = True

    name: str
    price: Decimal
    description: str
```

### Injected Fields

Same as `none` strategy - audit data stored in separate table.

### Operations

```python
repo = PydanticRepository(Product, db_pool, tenant_id=tenant_id)

# Create - no audit entry (initial state)
product = await repo.create(
    Product(name="Widget", price=Decimal("99.99")),
    user_id=user_id
)

# Update - creates audit entries for changed fields
await repo.update(
    product.id,
    Product(name="Super Widget", price=Decimal("149.99")),
    user_id=user_id
)
# Creates 2 audit entries: name change, price change

# Get audit history
history = await repo.get_audit_history(product.id)
for entry in history:
    print(f"{entry.field_name}: {entry.old_value} → {entry.new_value}")
    print(f"Changed by {entry.changed_by} at {entry.changed_at}")

# Get field-specific history
price_history = await repo.get_field_history(product.id, "price")
```

### Audit Entry Structure

```python
class AuditEntry:
    audit_id: UUID
    record_id: UUID  # ID of main record
    field_name: str  # Field that changed
    old_value: Any  # Previous value (JSON)
    new_value: Any  # New value (JSON)
    operation: str  # "UPDATE" or "DELETE"
    changed_at: datetime
    changed_by: UUID
    tenant_id: UUID  # If multi-tenant
```

### Database Impact

```sql
-- Main table (current state)
CREATE TABLE products (
    id UUID PRIMARY KEY,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    name VARCHAR(255),
    price DECIMAL(10,2),
    description TEXT
);

-- Audit table (change history)
CREATE TABLE products_audit (
    audit_id UUID PRIMARY KEY,
    record_id UUID REFERENCES products(id),
    field_name VARCHAR(255),
    old_value JSONB,
    new_value JSONB,
    operation VARCHAR(10),
    changed_at TIMESTAMP,
    changed_by UUID,
    tenant_id UUID,
    INDEX idx_record_id (record_id),
    INDEX idx_changed_at (changed_at DESC)
);
```

### Querying Audit Data

```python
# Get all changes for a record
history = await repo.get_audit_history(product_id)

# Get changes by user
user_changes = [h for h in history if h.changed_by == user_id]

# Get changes in date range
recent_changes = [
    h for h in history
    if h.changed_at >= datetime(2024, 1, 1)
]

# Reconstruct state at a point in time (approximate)
def get_state_at(record_id, target_date):
    current = await repo.get(record_id)
    history = await repo.get_audit_history(record_id)

    # Apply changes in reverse chronological order
    for change in reversed(history):
        if change.changed_at <= target_date:
            break
        # Revert change
        setattr(current, change.field_name, change.old_value)

    return current
```

## SCD2 Strategy

Slowly Changing Dimension Type 2 - creates immutable versions.

### Features

- ✅ Complete version history
- ✅ Time travel to any date
- ✅ Immutable records
- ✅ Version comparison
- ✅ Regulatory compliance
- ❌ Higher storage usage
- ❌ More complex queries

### Model Configuration

```python
class Contract(PydanticModel):
    __table_name__ = "contracts"
    __temporal_strategy__ = "scd2"
    __soft_delete__ = True
    __multi_tenant__ = True

    customer_id: UUID
    terms: str
    value: Decimal
    status: str
```

### Injected Fields

```python
# SCD2-specific fields
version: int  # Version number (1, 2, 3, ...)
valid_from: datetime  # When version became active
valid_to: Optional[datetime]  # When version ended (NULL = current)
is_current: bool  # True for current version only

# Plus all standard fields
id: UUID  # Same across all versions
created_at: datetime
updated_at: datetime
tenant_id: UUID  # If multi-tenant
deleted_at: Optional[datetime]  # If soft delete
```

### Operations

```python
repo = PydanticRepository(Contract, db_pool, tenant_id=tenant_id)

# Create - version 1
contract = await repo.create(
    Contract(customer_id=customer_id, terms="Standard", value=Decimal("10000")),
    user_id=user_id
)
assert contract.version == 1
assert contract.is_current == True

# Update - creates version 2, marks version 1 as historical
updated = await repo.update(
    contract.id,
    Contract(customer_id=customer_id, terms="Premium", value=Decimal("15000")),
    user_id=user_id
)
assert updated.version == 2
assert updated.is_current == True

# Get current version (default)
current = await repo.get(contract.id)
assert current.version == 2

# Time travel - get version at specific date
past_date = datetime(2024, 1, 1)
historical = await repo.get(contract.id, as_of=past_date)
assert historical.version == 1

# Get all versions
versions = await repo.get_version_history(contract.id)
assert len(versions) == 2

# Get specific version
v1 = await repo.get_version(contract.id, version=1)
assert v1.terms == "Standard"

# Compare versions
diff = await repo.compare_versions(contract.id, version1=1, version2=2)
# Returns: {"terms": {"old": "Standard", "new": "Premium", "changed": True}, ...}
```

### Database Impact

```sql
-- Single table with all versions
CREATE TABLE contracts (
    -- Identity (same across versions)
    id UUID,

    -- Versioning
    version INT,
    valid_from TIMESTAMP,
    valid_to TIMESTAMP,  -- NULL for current
    is_current BOOLEAN,

    -- Standard fields
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    tenant_id UUID,

    -- Business fields (versioned)
    customer_id UUID,
    terms TEXT,
    value DECIMAL(10,2),
    status VARCHAR(50),

    -- Constraints
    PRIMARY KEY (id, version),
    INDEX idx_current (id, is_current),
    INDEX idx_temporal (id, valid_from, valid_to)
);
```

### Time Travel Queries

```python
# Get state at specific time
async def get_at_time(repo, record_id, target_time):
    return await repo.get(record_id, as_of=target_time)

# Get all records as they were on a date
async def get_all_at_time(repo, target_time):
    return await repo.list(as_of=target_time)

# Track changes over time
async def get_changes_between(repo, record_id, start_date, end_date):
    versions = await repo.get_version_history(record_id)
    return [
        v for v in versions
        if start_date <= v.valid_from <= end_date
    ]

# Find when a field changed
async def find_change_date(repo, record_id, field_name, target_value):
    versions = await repo.get_version_history(record_id)
    for v in versions:
        if getattr(v, field_name) == target_value:
            return v.valid_from
    return None
```

### Version Management

```python
# Prevent version explosion with change detection
async def smart_update(repo, record_id, new_data, user_id):
    current = await repo.get(record_id)

    # Only create new version if data actually changed
    if has_changes(current, new_data):
        return await repo.update(record_id, new_data, user_id)
    return current

# Archive old versions
async def archive_old_versions(repo, record_id, keep_versions=10):
    versions = await repo.get_version_history(record_id)
    if len(versions) > keep_versions:
        # Move old versions to archive table
        to_archive = versions[:-keep_versions]
        # Implementation depends on your archival strategy
```

## Strategy Selection Guide

### Decision Tree

```python
def select_strategy(requirements):
    if not requirements.needs_history:
        return "none"

    if requirements.needs_time_travel:
        return "scd2"

    if requirements.needs_audit_trail:
        return "copy_on_change"

    return "none"
```

### Comparison Matrix

| Feature | None | Copy-on-Change | SCD2 |
|---------|------|----------------|------|
| **Storage Overhead** | Low | Medium | High |
| **Query Complexity** | Simple | Medium | Complex |
| **Audit Trail** | ❌ | ✅ Field-level | ✅ Full record |
| **Time Travel** | ❌ | ❌ | ✅ |
| **Change Attribution** | Last only | ✅ All changes | ✅ All versions |
| **Rollback Capability** | ❌ | Manual | ✅ Automatic |
| **Compliance** | Basic | Good | Excellent |
| **Performance** | Best | Good | Good with indexes |

### Use Case Examples

#### Use "none" when:
- You only need current state
- Audit trail not required
- Maximum performance needed
- Storage cost is a concern

```python
class SessionData(PydanticModel):
    __temporal_strategy__ = "none"

    session_id: str
    user_data: dict
    expires_at: datetime
```

#### Use "copy_on_change" when:
- Need audit trail for compliance
- Want to track who changed what
- Need to debug data issues
- Storage efficiency matters

```python
class Customer(PydanticModel):
    __temporal_strategy__ = "copy_on_change"

    email: str
    name: str
    credit_limit: Decimal
    risk_score: float
```

#### Use "scd2" when:
- Need point-in-time reporting
- Regulatory requirements for immutability
- Complex analytics on historical data
- Legal/contractual versioning

```python
class RegulatoryFiling(PydanticModel):
    __temporal_strategy__ = "scd2"

    filing_id: str
    company_id: UUID
    filing_data: dict
    status: str
    approval_date: Optional[datetime]
```

## API Methods by Strategy

### Common Methods (All Strategies)

```python
# CRUD
await repo.create(model, user_id=None)
await repo.update(id, model, user_id=None)
await repo.delete(id, user_id=None)
await repo.get(id, **kwargs)
await repo.list(filters=None, limit=100, offset=0, **kwargs)
await repo.count(filters=None, **kwargs)

# Batch operations
await repo.create_many(models, user_id=None, batch_size=100)
await repo.get_many(ids, **kwargs)

# Soft delete (if enabled)
await repo.restore(id)
```

### Copy-on-Change Specific

```python
# Audit trail
await repo.get_audit_history(record_id) -> List[AuditEntry]
await repo.get_field_history(record_id, field_name) -> List[AuditEntry]

# Analysis
await repo.get_change_frequency(record_id, field_name=None)
await repo.get_most_changed_fields(record_id, limit=10)
await repo.get_changes_by_user(user_id, start_date=None, end_date=None)
```

### SCD2 Specific

```python
# Version management
await repo.get_version_history(id) -> List[T]
await repo.get_version(id, version: int) -> Optional[T]
await repo.get_current_version(id) -> Optional[T]

# Time travel
await repo.get(id, as_of=datetime) -> Optional[T]
await repo.list(as_of=datetime) -> List[T]

# Comparison
await repo.compare_versions(id, version1: int, version2: int) -> Dict
await repo.get_version_diff(id, version1: int, version2: int) -> Dict

# Analysis
await repo.get_version_count(id) -> int
await repo.get_version_timeline(id) -> List[Dict]
```

## Advanced Patterns

### Hybrid Strategies

```python
# Use different strategies for different models
class User(PydanticModel):
    __temporal_strategy__ = "copy_on_change"  # Audit trail
    email: str
    name: str

class UserSession(PydanticModel):
    __temporal_strategy__ = "none"  # No history needed
    user_id: UUID
    token: str

class Contract(PydanticModel):
    __temporal_strategy__ = "scd2"  # Full versioning
    terms: str
    value: Decimal
```

### Strategy Migration

```python
# Migrate from none to copy_on_change
async def migrate_to_audit(old_table, new_model):
    # 1. Create audit table
    await db.execute(new_model.get_auxiliary_tables_sql()[0])

    # 2. Update model
    new_model.__temporal_strategy__ = "copy_on_change"

    # 3. Future changes will be tracked

# Migrate from copy_on_change to scd2
async def migrate_to_scd2(old_model, new_model):
    # 1. Add SCD2 fields to existing records
    await db.execute("""
        ALTER TABLE products
        ADD COLUMN version INT DEFAULT 1,
        ADD COLUMN valid_from TIMESTAMP DEFAULT NOW(),
        ADD COLUMN valid_to TIMESTAMP,
        ADD COLUMN is_current BOOLEAN DEFAULT true
    """)

    # 2. Rebuild historical versions from audit trail
    # (Complex process - see migration guide)
```

### Custom Strategy Implementation

```python
from ff_storage.temporal.strategies.base import TemporalStrategy
from ff_storage.temporal.registry import register_strategy

@register_strategy("custom")
class CustomStrategy(TemporalStrategy):
    def get_temporal_fields(self):
        return {
            "custom_version": (int, 1),
            "custom_timestamp": (datetime, "NOW()")
        }

    async def create(self, data, db_pool, tenant_id=None, user_id=None):
        # Custom create logic
        pass

    async def update(self, id, data, db_pool, tenant_id=None, user_id=None):
        # Custom update logic
        pass
```

## Performance Optimization

### Indexes for Each Strategy

```python
# None strategy
class UserNone(PydanticModel):
    __temporal_strategy__ = "none"

    email: str = Field(db_index=True)  # Frequent lookups
    created_at: datetime  # Auto-indexed

# Copy-on-change strategy
# Audit table automatically gets indexes on:
# - record_id (for history lookups)
# - changed_at (for time-based queries)
# - changed_by (for user activity reports)

# SCD2 strategy
# Automatic indexes on:
# - (id, is_current) for current version lookups
# - (id, valid_from, valid_to) for time travel
# - (id, version) for specific version access
```

### Query Optimization

```python
# Efficient current-only queries for SCD2
async def get_all_current(repo):
    # Uses is_current index
    return await repo.list(filters={"is_current": True})

# Batch history retrieval
async def get_histories(repo, record_ids):
    # Single query instead of N queries
    histories = {}
    for chunk in chunks(record_ids, 100):
        results = await repo.get_many_histories(chunk)
        histories.update(results)
    return histories
```

## Error Handling

```python
from ff_storage.exceptions import (
    TemporalStrategyError,
    VersionConflictError,
    AuditTrailError
)

try:
    await repo.update(id, data)
except VersionConflictError as e:
    # SCD2: Concurrent update created conflicting version
    # Retry with latest version
    current = await repo.get(id)
    await repo.update(id, merge_data(current, data))
except AuditTrailError as e:
    # Copy-on-change: Failed to write audit entry
    # Handle based on audit criticality
    logger.error(f"Audit write failed: {e}")
```