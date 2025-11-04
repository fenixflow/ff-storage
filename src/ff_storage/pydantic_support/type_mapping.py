"""
Type mapping from Pydantic/Python types to SQL types.

Handles:
- Basic Python types (str, int, bool, etc.)
- Pydantic types (UUID, datetime, Decimal)
- Complex types (list, dict, nested models)
- Custom type overrides via field metadata
"""

from datetime import date, datetime
from decimal import Decimal
from typing import get_args, get_origin
from uuid import UUID

from pydantic.fields import FieldInfo

from ..db.schema_sync.models import ColumnType


def _extract_max_length_from_field(field_info: FieldInfo) -> int | None:
    """
    Extract max_length from Pydantic v2 field constraints.

    Pydantic v2 stores constraints in metadata, not as direct attributes.
    """
    # Check Pydantic v2 metadata for constraint objects
    if hasattr(field_info, "metadata"):
        for constraint in field_info.metadata:
            if hasattr(constraint, "max_length") and constraint.max_length is not None:
                return constraint.max_length

    # Fallback: Try direct attribute (Pydantic v1 compatibility)
    if hasattr(field_info, "max_length") and field_info.max_length is not None:
        return field_info.max_length

    return None


def map_pydantic_type_to_column_type(
    python_type: type,
    field_info: FieldInfo,
) -> tuple[ColumnType, str]:
    """
    Map Pydantic field type to (ColumnType, native SQL type string).

    Args:
        python_type: Python type annotation from Pydantic field
        field_info: FieldInfo with metadata and constraints

    Returns:
        Tuple of (ColumnType enum, native SQL type string)

    Example:
        >>> from pydantic import Field
        >>> field_info = Field(max_length=255)
        >>> col_type, native = map_pydantic_type_to_column_type(str, field_info)
        >>> print(col_type, native)
        ColumnType.STRING VARCHAR(255)
    """
    metadata = field_info.json_schema_extra or {}

    # Check for custom db_type override (takes precedence)
    if "db_type" in metadata:
        custom_type = metadata["db_type"]
        column_type = _parse_custom_type(custom_type)
        return column_type, custom_type

    # Check for db_precision/db_scale OR Pydantic's max_digits/decimal_places for numeric types
    if (python_type == Decimal or python_type is Decimal) and (
        "db_precision" in metadata
        or "db_scale" in metadata
        or hasattr(field_info, "max_digits")
        or hasattr(field_info, "decimal_places")
    ):
        # Prefer explicit db_* overrides, fallback to Pydantic's constraints
        precision = metadata.get("db_precision") or getattr(field_info, "max_digits", None) or 15
        scale = metadata.get("db_scale") or getattr(field_info, "decimal_places", None) or 2
        return ColumnType.DECIMAL, f"NUMERIC({precision},{scale})"

    # Handle Optional[T] / Union[T, None]
    origin = get_origin(python_type)
    # Check for Union types (handles both typing.Union and types.UnionType from Python 3.10+)
    origin_str = str(origin)
    if origin is type(None) or "Union" in origin_str:
        args = get_args(python_type)
        if len(args) == 2 and type(None) in args:
            # Extract T from Optional[T]
            python_type = args[0] if args[1] is type(None) else args[1]
            origin = get_origin(python_type)

    # Direct type mappings
    if python_type == UUID or python_type is UUID:
        return ColumnType.UUID, "UUID"

    elif python_type is str:
        # Priority 1: Explicit override in json_schema_extra
        max_length = metadata.get("max_length")
        # Priority 2: Pydantic v2 constraints
        if max_length is None:
            max_length = _extract_max_length_from_field(field_info)
        # Priority 3: Default to 255
        if max_length is None:
            max_length = 255
        return ColumnType.STRING, f"VARCHAR({max_length})"

    elif python_type is int:
        return ColumnType.INTEGER, "INTEGER"

    elif python_type is bool:
        return ColumnType.BOOLEAN, "BOOLEAN"

    elif python_type is float:
        return ColumnType.DECIMAL, "DOUBLE PRECISION"

    elif python_type == datetime or python_type is datetime:
        return ColumnType.TIMESTAMPTZ, "TIMESTAMP WITH TIME ZONE"

    elif python_type == date or python_type is date:
        return ColumnType.TIMESTAMP, "DATE"

    elif python_type == Decimal or python_type is Decimal:
        # Prefer explicit db_* overrides, fallback to Pydantic's constraints
        precision = metadata.get("db_precision") or getattr(field_info, "max_digits", None) or 15
        scale = metadata.get("db_scale") or getattr(field_info, "decimal_places", None) or 2
        return ColumnType.DECIMAL, f"NUMERIC({precision},{scale})"

    # Complex types (list, dict, nested models)
    elif origin is list:
        # ALL lists → JSONB for consistency and portability
        # - Consistent with dict → JSONB and list[Pydantic] → JSONB
        # - Portable across PostgreSQL, MySQL, SQL Server
        # - No need for custom serializers on list[str], list[int], etc.
        # - Users wanting PostgreSQL native arrays can use json_schema_extra={"db_type": "TEXT[]"}
        return ColumnType.JSONB, "JSONB"

    elif origin is dict:
        # Dict → JSONB
        return ColumnType.JSONB, "JSONB"

    elif hasattr(python_type, "model_fields"):
        # Nested Pydantic model → JSONB
        return ColumnType.JSONB, "JSONB"

    # Fallback to TEXT
    return ColumnType.TEXT, "TEXT"


def _parse_custom_type(custom_type_str: str) -> ColumnType:
    """
    Parse custom db_type string to ColumnType enum.

    Args:
        custom_type_str: SQL type string like "DECIMAL(15,2)"

    Returns:
        Appropriate ColumnType enum value
    """
    type_upper = custom_type_str.upper()

    if "UUID" in type_upper:
        return ColumnType.UUID
    elif "VARCHAR" in type_upper or "CHARACTER" in type_upper:
        return ColumnType.STRING
    elif "TEXT" in type_upper:
        return ColumnType.TEXT
    elif "INT" in type_upper or "SERIAL" in type_upper:
        return ColumnType.INTEGER if "BIGINT" not in type_upper else ColumnType.BIGINT
    elif "BOOL" in type_upper:
        return ColumnType.BOOLEAN
    elif "TIMESTAMP" in type_upper:
        return ColumnType.TIMESTAMPTZ if "TIME ZONE" in type_upper else ColumnType.TIMESTAMP
    elif "JSONB" in type_upper:
        return ColumnType.JSONB
    elif "JSON" in type_upper:
        return ColumnType.JSONB
    elif "DECIMAL" in type_upper or "NUMERIC" in type_upper:
        return ColumnType.DECIMAL
    elif "[]" in type_upper or "ARRAY" in type_upper:
        return ColumnType.ARRAY
    else:
        return ColumnType.STRING  # Fallback
