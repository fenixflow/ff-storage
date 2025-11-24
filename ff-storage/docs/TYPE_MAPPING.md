# Type Mapping Guide for ff-storage v4.0

This guide explains how ff-storage maps Python/Pydantic types to PostgreSQL column types, including the enhanced support for native arrays introduced in v4.0.

## Table of Contents
- [Basic Type Mappings](#basic-type-mappings)
- [List/Array Type Mappings](#listarray-type-mappings)
- [Complex Type Mappings](#complex-type-mappings)
- [Custom Type Overrides](#custom-type-overrides)
- [Schema Drift Debugging](#schema-drift-debugging)
- [Migration from v3.x](#migration-from-v3x)

## Basic Type Mappings

ff-storage automatically maps Python/Pydantic types to appropriate PostgreSQL column types:

| Python Type | PostgreSQL Type | Notes |
|------------|-----------------|-------|
| `UUID` | `UUID` | Native UUID type |
| `str` | `VARCHAR(255)` | Default max length is 255 |
| `int` | `INTEGER` | 32-bit integer |
| `bool` | `BOOLEAN` | True/False values |
| `float` | `DOUBLE PRECISION` | 64-bit floating point |
| `datetime` | `TIMESTAMP WITH TIME ZONE` | Timezone-aware timestamps |
| `date` | `DATE` | Date without time |
| `Decimal` | `NUMERIC(15,2)` | Default precision 15, scale 2 |

### String Length Configuration

You can specify custom string lengths using Pydantic's `Field`:

```python
from pydantic import Field
from ff_storage import PydanticModel

class MyModel(PydanticModel):
    short_text: str = Field(max_length=50)      # VARCHAR(50)
    medium_text: str = Field(max_length=500)    # VARCHAR(500)
    long_text: str = Field(max_length=2000)     # VARCHAR(2000)
    unlimited_text: str = Field(db_type="TEXT") # TEXT (unlimited)
```

### Decimal Precision

Configure decimal precision and scale:

```python
class MyModel(PydanticModel):
    price: Decimal = Field(decimal_places=2, max_digits=10)  # NUMERIC(10,2)
    rate: Decimal = Field(db_precision=5, db_scale=4)        # NUMERIC(5,4)
```

## List/Array Type Mappings

**New in v4.0**: Native PostgreSQL arrays for simple types provide better performance and type safety.

| Python Type | PostgreSQL Type | Storage Format |
|------------|-----------------|----------------|
| `List[UUID]` | `UUID[]` | Native array |
| `List[str]` | `TEXT[]` | Native array |
| `List[int]` | `INTEGER[]` | Native array |
| `List[float]` | `DOUBLE PRECISION[]` | Native array |
| `List[bool]` | `BOOLEAN[]` | Native array |
| `List[Dict]` | `JSONB` | JSON storage |
| `List[BaseModel]` | `JSONB` | JSON storage |
| `list` (untyped) | `JSONB` | JSON storage |

### Example Usage

```python
from typing import List
from uuid import UUID
from pydantic import BaseModel

class MyModel(PydanticModel):
    # Native arrays (v4.0+)
    user_ids: List[UUID]        # UUID[] - native PostgreSQL array
    tags: List[str]              # TEXT[] - native PostgreSQL array
    scores: List[int]            # INTEGER[] - native PostgreSQL array

    # JSONB storage for complex types
    metadata: List[Dict]         # JSONB
    nested_models: List[SubModel]  # JSONB
```

### Benefits of Native Arrays

1. **Type Safety**: PostgreSQL enforces element types
2. **Performance**: Native array operations are faster than JSONB
3. **Indexing**: Can create GIN indexes on array columns
4. **Operators**: Use PostgreSQL array operators (`@>`, `<@`, `&&`)

### Array Operations

```python
# Query examples with native arrays
results = db.read_query(
    "SELECT * FROM mytable WHERE user_ids @> ARRAY[%s]::UUID[]",
    (some_uuid,)
)

# Array contains
results = db.read_query(
    "SELECT * FROM mytable WHERE tags && ARRAY['tag1', 'tag2']"
)
```

## Complex Type Mappings

Complex types are stored as JSONB for flexibility:

| Python Type | PostgreSQL Type | Use Case |
|------------|-----------------|----------|
| `Dict` | `JSONB` | Flexible key-value storage |
| `Dict[str, Any]` | `JSONB` | Typed dictionaries |
| Pydantic Models | `JSONB` | Nested model storage |
| `Optional[T]` | Same as T | Nullable flag handled separately |

### Example

```python
from typing import Dict, Optional
from pydantic import BaseModel

class Address(BaseModel):
    street: str
    city: str
    country: str

class MyModel(PydanticModel):
    settings: Dict[str, Any]     # JSONB
    address: Address              # JSONB (nested model)
    optional_data: Optional[Dict] # JSONB (nullable)
```

## Custom Type Overrides

You can override the default type mapping using `json_schema_extra`:

```python
class MyModel(PydanticModel):
    # Override to use TEXT instead of VARCHAR
    description: str = Field(json_schema_extra={"db_type": "TEXT"})

    # Use specific array type
    custom_array: List[str] = Field(json_schema_extra={"db_type": "VARCHAR(100)[]"})

    # Custom numeric precision
    amount: Decimal = Field(json_schema_extra={"db_type": "NUMERIC(20,6)"})

    # Force JSONB for simple lists (v3.x behavior)
    legacy_list: List[UUID] = Field(json_schema_extra={"db_type": "JSONB"})
```

## Schema Drift Debugging

v4.0 introduces enhanced debugging capabilities for schema drift issues.

### Enable Verbose Mode

```python
from ff_storage import SchemaManager
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create schema manager with verbose mode
schema_manager = SchemaManager(db, logger=logger, verbose=True)

# Compare schemas - will output detailed debugging info
changes = schema_manager.compare_schemas(desired_schema, current_schema)
```

### Debug Output Example

```
DEBUG: Comparing column 'user_ids':
  Before normalization:
    Desired: type=UUID[], nullable=False, default=None
    Current: type=uuid[], nullable=False, default=NULL
  After normalization:
    Desired: type=UUID[], nullable=False, default=None
    Current: type=UUID[], nullable=False, default=None
```

### Common Schema Drift Issues and Solutions

1. **Type Case Differences**: Handled automatically by normalizer
2. **Array Type Mismatch**: Ensure using v4.0+ type mappings
3. **Default Value Differences**: NULL vs None normalized automatically
4. **Precision/Scale**: Specify explicitly with Field metadata

## Migration from v3.x

### Breaking Changes

The main breaking change in v4.0 is the mapping of `List[UUID]` and other simple list types:

- **v3.x**: `List[UUID]` → `JSONB`
- **v4.0**: `List[UUID]` → `UUID[]`

### Migration Steps

1. **For New Tables**: No action needed, tables will be created with native arrays

2. **For Existing Tables with JSONB Lists**:

   Option A: Keep existing JSONB columns (backward compatible)
   ```python
   class MyModel(PydanticModel):
       # Force JSONB to match existing schema
       user_ids: List[UUID] = Field(json_schema_extra={"db_type": "JSONB"})
   ```

   Option B: Migrate to native arrays (recommended)
   ```sql
   -- Example migration for List[UUID] column
   ALTER TABLE mytable ADD COLUMN user_ids_new UUID[];
   UPDATE mytable SET user_ids_new =
       ARRAY(SELECT jsonb_array_elements_text(user_ids)::UUID);
   ALTER TABLE mytable DROP COLUMN user_ids;
   ALTER TABLE mytable RENAME COLUMN user_ids_new TO user_ids;
   ```

3. **Test Your Queries**: Native arrays use different operators than JSONB:
   - JSONB: `user_ids @> '["uuid-here"]'::jsonb`
   - Array: `user_ids @> ARRAY['uuid-here']::UUID[]`

### Compatibility Mode

To maintain v3.x behavior for all lists, you can create a custom type mapper:

```python
from ff_storage.pydantic_support import type_mapping

# Override at application startup to force v3.x behavior
def legacy_list_mapping(python_type, field_info, metadata):
    # Force all lists to JSONB
    if get_origin(python_type) is list:
        return ColumnType.JSONB, "JSONB"
    # Delegate to default mapping for non-lists
    return type_mapping.map_pydantic_type_to_column_type(
        python_type, field_info, metadata
    )

# Apply override before creating models
type_mapping.map_pydantic_type_to_column_type = legacy_list_mapping
```

## Best Practices

1. **Use Native Arrays** for simple types (UUID, str, int, float, bool)
2. **Use JSONB** for complex nested structures and variable schemas
3. **Specify Precision** explicitly for Decimal fields
4. **Set Max Length** for VARCHAR fields based on actual requirements
5. **Enable Verbose Mode** when debugging schema drift issues
6. **Test Migrations** thoroughly when upgrading from v3.x to v4.0

## Troubleshooting

### Schema Drift After Upgrade

If you see schema drift after upgrading to v4.0:

1. Enable verbose mode to see exact differences
2. Check if List types changed from JSONB to arrays
3. Use custom `db_type` overrides if needed
4. Consider running migrations to update schema

### Type Not Supported

For types not in the default mapping:

1. Use `json_schema_extra={"db_type": "YOUR_TYPE"}`
2. Store as TEXT or JSONB for complex types
3. Create a custom type mapper for application-wide changes

### Performance Issues

1. Native arrays are faster than JSONB for simple types
2. Create appropriate indexes (GIN for arrays, GIN for JSONB)
3. Consider partitioning for very large array columns

## Further Reading

- [PostgreSQL Array Types Documentation](https://www.postgresql.org/docs/current/arrays.html)
- [PostgreSQL JSONB Documentation](https://www.postgresql.org/docs/current/datatype-json.html)
- [Pydantic Field Configuration](https://docs.pydantic.dev/latest/usage/fields/)
- [ff-storage Schema Sync Guide](./SCHEMA_SYNC.md)