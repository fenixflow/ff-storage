"""
Enhanced Field metadata for database-specific and mock data configuration.

Provides a rich Field() wrapper that extends Pydantic Field with
database-specific metadata for "Pydantic as source of truth" architecture.

This allows complete SQL schema definition at the field level, including:
- Type overrides (db_type)
- Default expressions (db_default)
- Foreign key relationships (db_foreign_key, db_on_delete, db_on_update)
- Check constraints (db_check)
- Index specifications (db_index, db_index_where for partial indexes)
- Numeric precision/scale (db_precision, db_scale)

Mock data generation hints:
- mock_pattern: Named pattern for value generation (e.g., "email", "name")
- mock_generator: Custom generator function
- mock_skip: Skip field in mock generation (use overrides instead)
"""

from typing import Any, Callable, Literal, Optional

from pydantic import Field as PydanticField


def Field(
    # Standard Pydantic validation parameters
    default=None,
    *,
    default_factory=None,
    description: Optional[str] = None,
    max_length: Optional[int] = None,
    min_length: Optional[int] = None,
    ge: Optional[float] = None,
    le: Optional[float] = None,
    gt: Optional[float] = None,
    lt: Optional[float] = None,
    # Database-specific parameters
    db_type: Optional[str] = None,
    db_default: Optional[str] = None,
    db_nullable: Optional[bool] = None,
    db_precision: Optional[int] = None,
    db_scale: Optional[int] = None,
    db_primary_key: bool = False,
    db_unique: bool = False,
    db_index: bool = False,
    db_index_type: Literal["btree", "hash", "gin", "gist", "brin"] = "btree",
    db_index_where: Optional[str] = None,
    db_index_opclass: Optional[str] = None,
    db_foreign_key: Optional[str] = None,
    db_on_delete: Literal["CASCADE", "SET NULL", "RESTRICT", "NO ACTION"] = "RESTRICT",
    db_on_update: Literal["CASCADE", "SET NULL", "RESTRICT", "NO ACTION"] = "CASCADE",
    db_check: Optional[str] = None,
    db_generated: Optional[str] = None,
    # Mock data generation parameters
    mock_pattern: Optional[str] = None,
    mock_generator: Optional[Callable[[Any], Any]] = None,
    mock_skip: bool = False,
    **kwargs,
):
    """
    Enhanced Field with database-specific metadata.

    This function wraps Pydantic's Field to add database schema metadata,
    enabling complete SQL generation from Pydantic models.

    Args:
        # Standard Pydantic parameters
        default: Default value (use None for nullable fields)
        default_factory: Factory function for default values
        description: Field description (used in API docs and comments)
        max_length: Maximum string length (generates VARCHAR(n))
        min_length: Minimum string length (validation only)
        ge: Greater than or equal (validation + CHECK constraint)
        le: Less than or equal (validation + CHECK constraint)
        gt: Greater than (validation + CHECK constraint)
        lt: Less than (validation + CHECK constraint)

        # Database-specific parameters
        db_type: Override SQL type (e.g., "DECIMAL(15,2)", "JSONB")
        db_default: SQL default expression (e.g., "NOW()", "0", "gen_random_uuid()")
        db_nullable: Override nullable inference (default: inferred from Optional[T])
        db_precision: Numeric precision (for DECIMAL/NUMERIC)
        db_scale: Numeric scale (for DECIMAL/NUMERIC)
        db_primary_key: Mark as primary key
        db_unique: Create UNIQUE constraint
        db_index: Create index on this field
        db_index_type: Index type (btree, hash, gin, gist, brin)
        db_index_where: WHERE clause for partial index (e.g., "deleted_at IS NULL")
        db_index_opclass: Index operator class (e.g., "gin_trgm_ops" for trigram GIN indexes)
        db_foreign_key: Foreign key reference (format: "schema.table(column)")
        db_on_delete: ON DELETE action for FK (CASCADE, SET NULL, RESTRICT, NO ACTION)
        db_on_update: ON UPDATE action for FK (CASCADE, SET NULL, RESTRICT, NO ACTION)
        db_check: CHECK constraint expression (e.g., "price > 0")
        db_generated: Generated column expression (e.g., "STORED AS (field1 + field2)")

        # Mock data generation parameters
        mock_pattern: Named pattern for value generation. Supported patterns:
            "email", "name", "first_name", "last_name", "company", "address",
            "city", "country", "phone", "url", "title", "description", "text"
        mock_generator: Custom generator function. Receives a Faker instance
            and returns the generated value. Example: lambda f: f.bothify("POL-####")
        mock_skip: If True, skip this field in mock generation. Must provide
            value via overrides parameter when creating mock instances.

    Returns:
        Pydantic FieldInfo with database metadata in json_schema_extra

    Examples:
        >>> from ff_storage import PydanticModel, Field
        >>>
        >>> class Product(PydanticModel):
        ...     # String with explicit length
        ...     name: str = Field(max_length=255, db_index=True)
        ...
        ...     # Decimal with precision/scale
        ...     price: Decimal = Field(
        ...         ge=0,
        ...         db_precision=10,
        ...         db_scale=2,
        ...         db_check="price >= 0"
        ...     )
        ...
        ...     # Foreign key with CASCADE
        ...     category_id: UUID = Field(
        ...         db_foreign_key="public.categories(id)",
        ...         db_on_delete="CASCADE",
        ...         db_index=True
        ...     )
        ...
        ...     # Partial index for active records
        ...     status: str = Field(
        ...         db_index=True,
        ...         db_index_where="deleted_at IS NULL"
        ...     )
        ...
        ...     # SQL default expression
        ...     created_at: datetime = Field(
        ...         db_default="NOW()"
        ...     )
        ...
        ...     # Mock data patterns
        ...     email: str = Field(mock_pattern="email")
        ...     policy_number: str = Field(mock_generator=lambda f: f.bothify("POL-####-????"))
        ...     internal_ref: str = Field(mock_skip=True)  # Provide via overrides
    """
    # Build json_schema_extra with all database metadata
    json_schema_extra = {}

    # Add database-specific metadata (only non-None values)
    db_metadata = {
        "db_type": db_type,
        "db_default": db_default,
        "db_nullable": db_nullable,
        "db_precision": db_precision,
        "db_scale": db_scale,
        "db_primary_key": db_primary_key,
        "db_unique": db_unique,
        "db_index": db_index,
        "db_index_type": db_index_type,
        "db_index_where": db_index_where,
        "db_index_opclass": db_index_opclass,
        "db_foreign_key": db_foreign_key,
        "db_on_delete": db_on_delete,
        "db_on_update": db_on_update,
        "db_check": db_check,
        "db_generated": db_generated,
        # Mock data generation
        "mock_pattern": mock_pattern,
        "mock_generator": mock_generator,
        "mock_skip": mock_skip,
    }

    # Filter out None values and False booleans (for mock_skip, db_primary_key, etc.)
    # We want to include True booleans but exclude False defaults
    json_schema_extra = {k: v for k, v in db_metadata.items() if v is not None and v is not False}

    # Handle kwargs json_schema_extra merge
    if "json_schema_extra" in kwargs:
        existing_extra = kwargs.pop("json_schema_extra")
        if isinstance(existing_extra, dict):
            json_schema_extra.update(existing_extra)

    # Build Field arguments - don't pass both default and default_factory
    field_args = {
        "description": description,
        "max_length": max_length,
        "min_length": min_length,
        "ge": ge,
        "le": le,
        "gt": gt,
        "lt": lt,
        "json_schema_extra": json_schema_extra if json_schema_extra else None,
    }

    # Only add default OR default_factory, not both
    if default_factory is not None:
        field_args["default_factory"] = default_factory
    else:
        field_args["default"] = default

    # Add any additional kwargs
    field_args.update(kwargs)

    # Return Pydantic Field with enriched metadata
    return PydanticField(**field_args)
