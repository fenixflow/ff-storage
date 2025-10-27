# Temporal Strategy Selection Guide

Choose the right temporal strategy for your data management needs.

## Quick Decision Matrix

| Use Case | Strategy | Why? |
|----------|----------|------|
| Static lookup tables (countries, statuses) | **none** | No history needed |
| User profiles, product catalogs | **copy_on_change** | Field-level audit, moderate updates |
| Contracts, regulations, financial records | **scd2** | Immutable versions, time-travel queries |
| Real-time metrics, cache tables | **none** | High churn, history not valuable |
| Configuration settings | **copy_on_change** | Track who changed what when |
| Legal documents, compliance data | **scd2** | Regulatory requirements, point-in-time reporting |

## Decision Flowchart

```
Do you need history?
├─ No → **none**
└─ Yes → How do you query history?
    ├─ "Who changed field X?" → **copy_on_change**
    ├─ "Show me record at time T" → **scd2**
    └─ "Track every change" → copy_on_change or scd2
        └─ High update rate (>100/sec per row)? → **scd2**
        └─ Moderate update rate → **copy_on_change**
```

## Strategy Deep Dive

### None Strategy

**Best for**: Static data, lookup tables, high-churn data

```python
class Country(PydanticModel):
    __temporal_strategy__ = "none"

    code: str = Field(max_length=2)
    name: str = Field(max_length=255)
```

**Fields Added**: None (beyond id, created_at, updated_at, created_by)
**Auxiliary Tables**: None
**Storage Overhead**: None
**Write Performance**: Fastest (direct UPDATE)
**Read Performance**: Fastest (no joins, no filtering)

**When to Use**:
- Lookup tables (countries, currencies, statuses)
- Cache tables
- Temporary data
- High-churn data where history adds no value

**Trade-offs**:
- No audit trail
- Can't answer "who changed what when"
- Can't restore deleted records (unless soft_delete=True)

---

### Copy-on-Change Strategy

**Best for**: User-facing data with moderate update rates

```python
class UserProfile(PydanticModel):
    __temporal_strategy__ = "copy_on_change"

    email: str
    name: str
    preferences: dict  # JSONB
```

**Fields Added**: None (audit table is separate)
**Auxiliary Tables**: `{table}_audit` (field-level changes)
**Storage Overhead**: ~1 audit row per changed field per update
**Write Performance**: Good (<100 updates/sec per row)
**Read Performance**: Excellent (main table unchanged)

**Audit Table Structure**:
```sql
CREATE TABLE user_profiles_audit (
    audit_id UUID PRIMARY KEY,
    record_id UUID,  -- FK to main table
    field_name VARCHAR(255),
    old_value JSONB,
    new_value JSONB,
    operation VARCHAR(10),  -- INSERT, UPDATE, DELETE
    changed_at TIMESTAMPTZ,
    changed_by UUID,
    transaction_id UUID  -- Groups multi-field updates
);
```

**Concurrency**:
- Uses `SELECT ... FOR UPDATE` during diff computation
- Holds row lock for ~10-50ms (depending on field count)
- Acceptable for <100 updates/sec per row
- Higher rates may cause lock contention

**When to Use**:
- User profiles (name, email, preferences)
- Product catalogs (price, description, stock)
- Configuration settings
- Any data where you need to know "who changed X to Y when"

**Query Patterns**:
```python
# Get full history
history = await repo.get_audit_history(user_id)

# Get field-specific history
email_changes = await repo.get_field_history(user_id, "email")

# Find all changes by user
changes = await AuditQueryHelper.get_changes_by_user(user_id)
```

**Trade-offs**:
- Row-level locking reduces write concurrency
- Can't do "show me record at time T" efficiently
- Audit table grows with every field change

---

### SCD2 Strategy (Slowly Changing Dimension Type 2)

**Best for**: Immutable records, regulatory compliance, time-travel queries

```python
class Contract(PydanticModel):
    __temporal_strategy__ = "scd2"

    contract_number: str
    terms: str
    effective_date: date
```

**Fields Added**:
- `valid_from` (TIMESTAMPTZ)
- `valid_to` (TIMESTAMPTZ, NULL for current)
- `version` (INTEGER, starts at 1)
- `deleted_at`, `deleted_by` (soft delete built-in)

**Auxiliary Tables**: None (all versions in main table)
**Storage Overhead**: 1 full row per version
**Write Performance**: Good (INSERT-heavy, no UPDATE)
**Read Performance**: Good with proper indexes

**Main Table Structure**:
```sql
CREATE TABLE contracts (
    id UUID,  -- Logical ID (same across versions)
    version INTEGER,
    valid_from TIMESTAMPTZ,
    valid_to TIMESTAMPTZ,  -- NULL = current version
    deleted_at TIMESTAMPTZ,
    ...user fields...,
    UNIQUE (id, version)  -- Enforces one row per version
);
```

**When to Use**:
- Regulatory/compliance data (SOX, GDPR)
- Financial records (transactions, contracts)
- Legal documents
- Any data requiring point-in-time reporting
- High update rates where row-level locking is unacceptable

**Query Patterns**:
```python
# Current version
contract = await repo.get(contract_id)

# Time travel
contract_at_signing = await repo.get(contract_id, as_of=datetime(2024, 1, 1))

# Version history
versions = await repo.get_version_history(contract_id)

# Specific version
v2 = await repo.get_version(contract_id, version=2)

# Compare versions
diff = await repo.compare_versions(contract_id, version1=1, version2=2)
```

**Foreign Key Considerations**:
- FKs should point to **logical ID**, not version-specific rows
- Children reference "current version" via `valid_to IS NULL` join
- See [SCD2 Foreign Keys Guide](scd2_foreign_keys.md) for patterns

**Soft Delete Semantics**:
- Deletion creates **new version** with `deleted_at` set
- Preserves immutability (versions never change)
- Time-travel excludes deleted records unless `include_deleted=True`

**Trade-offs**:
- Higher storage overhead (full row per version)
- More complex queries (need temporal filtering)
- FK relationships require careful design

---

## Performance Comparison

### Storage Overhead

| Strategy | Per Update | Example (1000 updates) |
|----------|------------|------------------------|
| **none** | 0 bytes | 0 bytes |
| **copy_on_change** | ~200 bytes per changed field | 200KB (avg 1 field/update) |
| **scd2** | Full row (~1KB) | 1MB |

### Write Throughput

| Strategy | Ops/sec (single row) | Notes |
|----------|----------------------|-------|
| **none** | 10,000+ | Direct UPDATE |
| **copy_on_change** | 100-500 | Row-level lock during diff |
| **scd2** | 5,000+ | INSERT-only, no locks |

### Read Latency

| Strategy | Current Record | Historical Query |
|----------|----------------|------------------|
| **none** | <1ms | N/A |
| **copy_on_change** | <1ms | <10ms (scan audit table) |
| **scd2** | <1ms (with index) | <5ms (time-travel) |

---

## Switching Strategies

Can you change strategies later? **Yes, but with migration effort.**

### Migrating to More History

**none → copy_on_change**: Easy
- Add audit table
- Start tracking changes going forward
- No historical data captured

**none → scd2**: Moderate
- Add temporal fields (valid_from, valid_to, version)
- Backfill with version=1, valid_from=created_at
- Start versioning going forward

**copy_on_change → scd2**: Complex
- Reconstruct versions from audit trail
- Populate SCD2 table from audit history
- Data migration required

### Migrating to Less History

**scd2 → copy_on_change**: Moderate
- Keep current versions only
- Archive historical versions
- Start field-level tracking

**scd2 → none**: Easy (but lossy)
- Keep current versions only
- Drop temporal fields
- Historical data lost

---

## Best Practices

### Default to copy_on_change

Unless you have specific needs, **copy_on_change** is the sweet spot:
- ✅ Audit trail for compliance
- ✅ Good performance
- ✅ Low storage overhead
- ✅ Simple queries

### Use scd2 for:
- Regulatory requirements (SOX, GDPR)
- Financial/legal data
- Point-in-time reporting needs
- High write concurrency requirements

### Use none for:
- Static lookup tables
- Cache/temporary data
- High-churn data (>1000 updates/sec)

### Multi-Strategy in Same Database

**Yes!** Mix strategies per model:

```python
class User(PydanticModel):
    __temporal_strategy__ = "copy_on_change"  # Audit who changed what

class Contract(PydanticModel):
    __temporal_strategy__ = "scd2"  # Immutable versions

class Country(PydanticModel):
    __temporal_strategy__ = "none"  # Static lookup
```

---

## Next Steps

- **[Quickstart Guide](../quickstart_v3.md)** - Get started in 5 minutes
- **[SCD2 Foreign Keys](scd2_foreign_keys.md)** - FK patterns for versioned data
- **[API Reference](../api/pydantic_orm.md)** - Complete API documentation
- **[Production Deployment](production_deployment.md)** - Operational best practices
