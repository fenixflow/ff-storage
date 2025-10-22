# SCD2 Foreign Key Patterns

How to handle FK relationships in SCD2 (versioned) models.

## The Challenge

SCD2 tables have multiple rows per logical ID:

```sql
SELECT id, version, valid_from, valid_to, name FROM contracts;
-- id                | version | valid_from | valid_to  | name
-- abc-123           | 1       | 2024-01-01 | 2024-06-01| Contract v1
-- abc-123           | 2       | 2024-06-01 | NULL      | Contract v2
```

**Question**: Should child tables reference the logical ID (`abc-123`) or specific versions?

## Recommended Pattern: FK to Logical ID

**Most common and simplest approach.**

```python
class Contract(PydanticModel):
    __temporal_strategy__ = "scd2"
    contract_number: str
    terms: str

class Payment(PydanticModel):
    __temporal_strategy__ = "copy_on_change"  # Or "none"

    contract_id: UUID = Field(
        db_foreign_key="public.contracts(id)",  # FK to logical ID
        db_index=True,
    )
    amount: Decimal
```

### How It Works

- FK references logical ID (not version-specific row)
- Children "follow" the current version via joins
- Simple, matches business logic ("payment for contract ABC")

### Query Pattern

```python
# Get current contract
contract = await contract_repo.get(contract_id)

# Get payments for contract (all versions)
payments = await payment_repo.list(filters={"contract_id": contract_id})

# Join with current contract version
query = """
    SELECT p.*, c.terms
    FROM payments p
    JOIN contracts c ON c.id = p.contract_id
   WHERE c.valid_to IS NULL  -- Current version only
     AND p.contract_id = $1
"""
```

### Limitations

- FK constraint can't enforce "current version exists"
- Child might reference deleted contract version
- Need application logic to handle version changes

---

## Alternative: Materialized View for Current Versions

For complex queries, create a view of current versions:

```python
class Contract(PydanticModel):
    __temporal_strategy__ = "scd2"

    @classmethod
    def create_current_view_sql(cls) -> str:
        """Generate SQL for current versions view."""
        return """
        CREATE MATERIALIZED VIEW contracts_current AS
        SELECT * FROM contracts
        WHERE valid_to IS NULL AND deleted_at IS NULL;

        CREATE UNIQUE INDEX ON contracts_current(id);

        -- Refresh periodically or via trigger
        """
```

Then FK to the view:

```python
class Payment(PydanticModel):
    contract_id: UUID = Field(
        db_foreign_key="public.contracts_current(id)",  # FK to view
    )
```

**Pros**:
- FK constraint enforced
- Simpler queries (no temporal filtering)

**Cons**:
- View must be refreshed
- Extra maintenance

---

## Advanced: Surrogate record_id Pattern

For strict referential integrity per version:

```python
class Contract(PydanticModel):
    __temporal_strategy__ = "scd2"

    record_id: UUID = Field(default_factory=uuid4, db_primary_key=True)
    logical_id: UUID = Field(default_factory=uuid4)  # Groups versions
    version: int
    # ... other fields

class Payment(PydanticModel):
    contract_record_id: UUID = Field(
        db_foreign_key="public.contracts(record_id)",  # FK to specific version
    )
```

**Schema**:
```sql
CREATE TABLE contracts (
    record_id UUID PRIMARY KEY,  -- Unique per version row
    logical_id UUID NOT NULL,    -- Groups versions together
    version INTEGER NOT NULL,
    ...
    UNIQUE (logical_id, version)
);

CREATE TABLE payments (
    id UUID PRIMARY KEY,
    contract_record_id UUID REFERENCES contracts(record_id),
    ...
);
```

**Pros**:
- FK enforces version-specific referential integrity
- Child points to exact version

**Cons**:
- More complex schema
- Need to track logical_id vs record_id
- Queries more complex
- **Not currently supported by ff-storage** (would require custom implementation)

---

## Best Practices

### 1. Default to FK to Logical ID

Unless you have specific needs, use the logical ID pattern:

```python
contract_id: UUID = Field(
    db_foreign_key="public.contracts(id)",
    db_on_delete="RESTRICT",  # Prevent deleting referenced contracts
)
```

### 2. Add Application-Level Checks

Since FK can't enforce "current version exists", add checks:

```python
async def create_payment(payment_data, contract_id):
    # Verify contract exists and is current
    contract = await contract_repo.get(contract_id)
    if not contract:
        raise ValueError(f"Contract {contract_id} not found or deleted")

    # Create payment
    return await payment_repo.create(payment_data)
```

### 3. Document Version Behavior

In model docstrings:

```python
class Payment(PydanticModel):
    """
    Payment record.

    contract_id references the logical ID of a Contract.
    Payments "follow" contract versions - joins always use current version.
    """
    contract_id: UUID
```

### 4. Use Cascade Carefully

```python
# RESTRICT: Safe default (prevent deleting referenced contracts)
db_on_delete="RESTRICT"

# CASCADE: Deletes payments when contract deleted (careful!)
db_on_delete="CASCADE"

# SET NULL: Sets contract_id to NULL (if nullable)
db_on_delete="SET NULL"
```

---

## Common Patterns

### One-to-Many (Contract → Payments)

```python
# Parent (versioned)
class Contract(PydanticModel):
    __temporal_strategy__ = "scd2"
    contract_number: str

# Child (non-versioned or copy_on_change)
class Payment(PydanticModel):
    contract_id: UUID = Field(db_foreign_key="public.contracts(id)")
    amount: Decimal
```

### Many-to-Many (Products ← OrderItems → Orders)

```python
class Product(PydanticModel):
    __temporal_strategy__ = "scd2"
    name: str
    price: Decimal

class Order(PydanticModel):
    __temporal_strategy__ = "copy_on_change"
    order_number: str

class OrderItem(PydanticModel):
    __temporal_strategy__ = "copy_on_change"

    order_id: UUID = Field(db_foreign_key="public.orders(id)")
    product_id: UUID = Field(db_foreign_key="public.products(id)")
    quantity: int
    price_at_purchase: Decimal  # Snapshot of product price
```

**Key**: `price_at_purchase` snapshots the product price to avoid version confusion.

### Self-Referential (Comments → Parent Comment)

```python
class Comment(PydanticModel):
    __temporal_strategy__ = "copy_on_change"

    parent_id: Optional[UUID] = Field(
        default=None,
        db_foreign_key="public.comments(id)",
    )
    text: str
```

---

## Time-Travel Joins

When querying historical data, join to specific versions:

```python
# Get payments with contract terms at specific time
as_of = datetime(2024, 6, 15)

query = """
    SELECT p.*, c.terms
    FROM payments p
    JOIN contracts c ON c.id = p.contract_id
    WHERE p.created_at <= $1
      AND c.valid_from <= $1
      AND (c.valid_to IS NULL OR c.valid_to > $1)
"""
```

Or use repository:

```python
# Get contract as it was at payment time
payment = await payment_repo.get(payment_id)
contract_at_time = await contract_repo.get(
    payment.contract_id,
    as_of=payment.created_at
)
```

---

## Summary

**Recommended**: FK to logical ID
- Simple, matches business logic
- Works with ff-storage out of the box
- Add application-level checks for current version

**Alternative**: Materialized view
- For complex query performance
- Requires view maintenance

**Advanced**: Surrogate record_id
- Not supported by ff-storage currently
- Only for strict version-specific integrity needs

---

**Next Steps**:
- [Strategy Selection Guide](strategy_selection.md)
- [Quickstart Guide](../quickstart_v3.md)
- [API Reference](../api/pydantic_orm.md)
