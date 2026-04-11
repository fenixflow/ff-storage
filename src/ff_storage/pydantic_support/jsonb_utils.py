"""JSONB serialization/deserialization utilities for database operations.

This module provides shared utilities for converting between Python objects
and JSONB column values. These utilities are used by:
- Query executor (for reading JSONB columns)
- Temporal strategies (for reading/writing JSONB columns)
- PydanticRepository (for reading/writing JSONB columns)

The key insight is that PostgreSQL drivers (asyncpg, psycopg2) may return
JSONB columns as JSON strings that need to be deserialized before passing
to Pydantic's model_validate(). Similarly, complex Python objects need to
be serialized to JSON strings when inserting into JSONB columns.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, Type

if TYPE_CHECKING:
    pass


def deserialize_jsonb_fields(model_class: Type, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deserialize JSONB fields from JSON strings to Python objects.

    This is necessary because PostgreSQL drivers may return JSONB columns as
    JSON strings that need to be deserialized back to Python dicts/lists
    before passing to Pydantic's model_validate().

    Args:
        model_class: Pydantic model class with field definitions
        data: Dictionary of field values from database

    Returns:
        Dictionary with JSONB fields deserialized to Python objects

    Example:
        >>> data = {"name": "Product", "metadata": '{"tags": ["new"]}'}
        >>> deserialized = deserialize_jsonb_fields(ProductModel, data)
        >>> deserialized["metadata"]
        {"tags": ["new"]}
    """
    # Only deserialize if we have a Pydantic model with field definitions
    if not hasattr(model_class, "model_fields"):
        return data  # Not a Pydantic model, return as-is

    # Import here to avoid circular dependency
    from ..db.schema_sync.models import ColumnType
    from .type_mapping import map_pydantic_type_to_column_type

    deserialized_data = data.copy()

    for field_name, field_value in data.items():
        # Skip fields not in model definition (e.g., temporal fields)
        if field_name not in model_class.model_fields:
            continue

        field_info = model_class.model_fields[field_name]
        python_type = field_info.annotation

        # Get column type for this field
        column_type, _ = map_pydantic_type_to_column_type(python_type, field_info)

        # Deserialize JSONB fields from JSON strings
        if column_type == ColumnType.JSONB and field_value is not None:
            # Only deserialize if it's a string (already serialized)
            if isinstance(field_value, str):
                try:
                    deserialized_data[field_name] = json.loads(field_value)
                except (json.JSONDecodeError, TypeError):
                    # If deserialization fails, keep as-is
                    pass

    return deserialized_data


def serialize_jsonb_fields(model_class: Type, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Serialize JSONB fields to JSON strings for database insertion.

    Identifies which fields are JSONB columns from the Pydantic model's
    field types and serializes Python dicts/lists to JSON strings.

    This is necessary because asyncpg may not automatically handle Python
    dicts/lists for JSONB columns in all configurations. Explicit JSON
    serialization ensures compatibility across different PostgreSQL drivers.

    Args:
        model_class: Pydantic model class with field definitions
        data: Dictionary of field values

    Returns:
        Dictionary with JSONB fields serialized to JSON strings

    Example:
        >>> data = {"name": "Product", "metadata": {"tags": ["new"]}}
        >>> serialized = serialize_jsonb_fields(ProductModel, data)
        >>> serialized["metadata"]
        '{"tags": ["new"]}'
    """
    # Only serialize if we have a Pydantic model with field definitions
    if not hasattr(model_class, "model_fields"):
        return data  # Not a Pydantic model, return as-is

    # Import here to avoid circular dependency
    from ..db.schema_sync.models import ColumnType
    from .type_mapping import map_pydantic_type_to_column_type

    serialized_data = data.copy()

    for field_name, field_value in data.items():
        # Skip fields not in model definition (e.g., temporal fields)
        if field_name not in model_class.model_fields:
            continue

        field_info = model_class.model_fields[field_name]
        python_type = field_info.annotation

        # Get column type for this field
        column_type, _ = map_pydantic_type_to_column_type(python_type, field_info)

        # Serialize JSONB fields to JSON strings
        if column_type == ColumnType.JSONB and field_value is not None:
            # Only serialize if not already a string
            if not isinstance(field_value, str):
                try:
                    # Use default=str to handle non-serializable types (UUID, datetime, etc.)
                    serialized_data[field_name] = json.dumps(field_value, default=str)
                except (TypeError, ValueError):
                    # If serialization fails, convert to string as fallback
                    serialized_data[field_name] = json.dumps(str(field_value))

    return serialized_data
