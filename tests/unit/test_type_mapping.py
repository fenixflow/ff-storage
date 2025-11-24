"""
Comprehensive unit tests for Pydantic to PostgreSQL type mapping.

Tests the mapping of various Python/Pydantic types to SQL column types,
including the enhanced support for native PostgreSQL arrays.
"""

import pytest
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

from pydantic import BaseModel, Field
from ff_storage.pydantic_support.type_mapping import map_pydantic_type_to_column_type
from ff_storage.db.schema_sync.models import ColumnType


class TestBasicTypeMapping:
    """Test mapping of basic Python types."""

    def test_uuid_mapping(self):
        """UUID should map to UUID column type."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(UUID, field_info)
        assert col_type == ColumnType.UUID
        assert native_type == "UUID"

    def test_str_mapping(self):
        """String should map to VARCHAR with default length."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(str, field_info)
        assert col_type == ColumnType.STRING
        assert native_type == "VARCHAR(255)"

    def test_str_with_max_length(self):
        """String with max_length should use that length."""
        field_info = Field(json_schema_extra={"max_length": 100})
        col_type, native_type = map_pydantic_type_to_column_type(str, field_info)
        assert col_type == ColumnType.STRING
        assert native_type == "VARCHAR(100)"

    def test_int_mapping(self):
        """Int should map to INTEGER."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(int, field_info)
        assert col_type == ColumnType.INTEGER
        assert native_type == "INTEGER"

    def test_bool_mapping(self):
        """Bool should map to BOOLEAN."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(bool, field_info)
        assert col_type == ColumnType.BOOLEAN
        assert native_type == "BOOLEAN"

    def test_float_mapping(self):
        """Float should map to DOUBLE PRECISION."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(float, field_info)
        assert col_type == ColumnType.DECIMAL
        assert native_type == "DOUBLE PRECISION"

    def test_datetime_mapping(self):
        """Datetime should map to TIMESTAMP WITH TIME ZONE."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(datetime, field_info)
        assert col_type == ColumnType.TIMESTAMPTZ
        assert native_type == "TIMESTAMP WITH TIME ZONE"

    def test_date_mapping(self):
        """Date should map to DATE."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(date, field_info)
        assert col_type == ColumnType.TIMESTAMP
        assert native_type == "DATE"

    def test_time_mapping(self):
        """Time should map to TIME."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(time, field_info)
        assert col_type == ColumnType.TIME
        assert native_type == "TIME"

    def test_timedelta_mapping(self):
        """Timedelta should map to INTERVAL."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(timedelta, field_info)
        assert col_type == ColumnType.INTERVAL
        assert native_type == "INTERVAL"

    def test_bytes_mapping(self):
        """Bytes should map to BYTEA."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(bytes, field_info)
        assert col_type == ColumnType.BINARY
        assert native_type == "BYTEA"

    def test_decimal_mapping(self):
        """Decimal should map to NUMERIC with precision and scale."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(Decimal, field_info)
        assert col_type == ColumnType.DECIMAL
        assert native_type == "NUMERIC(15,2)"  # Default precision/scale

    def test_decimal_with_precision(self):
        """Decimal with custom precision should use those values."""
        field_info = Field(json_schema_extra={"db_precision": 10, "db_scale": 4})
        col_type, native_type = map_pydantic_type_to_column_type(Decimal, field_info)
        assert col_type == ColumnType.DECIMAL
        assert native_type == "NUMERIC(10,4)"


class TestListTypeMapping:
    """Test enhanced list type mapping with native PostgreSQL arrays."""

    def test_list_uuid_mapping(self):
        """List[UUID] should map to native UUID[] array."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(List[UUID], field_info)
        assert col_type == ColumnType.ARRAY
        assert native_type == "UUID[]"

    def test_list_str_mapping(self):
        """List[str] should map to native TEXT[] array."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(List[str], field_info)
        assert col_type == ColumnType.ARRAY
        assert native_type == "TEXT[]"

    def test_list_int_mapping(self):
        """List[int] should map to native INTEGER[] array."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(List[int], field_info)
        assert col_type == ColumnType.ARRAY
        assert native_type == "INTEGER[]"

    def test_list_float_mapping(self):
        """List[float] should map to native DOUBLE PRECISION[] array."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(List[float], field_info)
        assert col_type == ColumnType.ARRAY
        assert native_type == "DOUBLE PRECISION[]"

    def test_list_bool_mapping(self):
        """List[bool] should map to native BOOLEAN[] array."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(List[bool], field_info)
        assert col_type == ColumnType.ARRAY
        assert native_type == "BOOLEAN[]"

    def test_list_dict_mapping(self):
        """List[Dict] should map to JSONB for complex types."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(List[Dict], field_info)
        assert col_type == ColumnType.JSONB
        assert native_type == "JSONB"

    def test_list_untyped_mapping(self):
        """Untyped list should map to JSONB."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(list, field_info)
        assert col_type == ColumnType.JSONB
        assert native_type == "JSONB"

    def test_list_nested_model_mapping(self):
        """List of Pydantic models should map to JSONB."""

        class NestedModel(BaseModel):
            name: str
            value: int

        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(List[NestedModel], field_info)
        assert col_type == ColumnType.JSONB
        assert native_type == "JSONB"


class TestSetTypeMapping:
    """Test enhanced set type mapping with native PostgreSQL arrays."""

    def test_set_uuid_mapping(self):
        """Set[UUID] should map to native UUID[] array."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(Set[UUID], field_info)
        assert col_type == ColumnType.ARRAY
        assert native_type == "UUID[]"

    def test_set_str_mapping(self):
        """Set[str] should map to native TEXT[] array."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(Set[str], field_info)
        assert col_type == ColumnType.ARRAY
        assert native_type == "TEXT[]"

    def test_set_int_mapping(self):
        """Set[int] should map to native INTEGER[] array."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(Set[int], field_info)
        assert col_type == ColumnType.ARRAY
        assert native_type == "INTEGER[]"

    def test_set_untyped_mapping(self):
        """Untyped set should map to JSONB."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(set, field_info)
        assert col_type == ColumnType.JSONB
        assert native_type == "JSONB"


class TestTupleTypeMapping:
    """Test tuple type mapping (ordered collections with mixed types)."""

    def test_tuple_mapping(self):
        """Tuple should map to JSONB."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(Tuple[str, int], field_info)
        assert col_type == ColumnType.JSONB
        assert native_type == "JSONB"

    def test_tuple_untyped_mapping(self):
        """Untyped tuple should map to JSONB."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(tuple, field_info)
        assert col_type == ColumnType.JSONB
        assert native_type == "JSONB"


class TestComplexTypeMapping:
    """Test mapping of complex types."""

    def test_dict_mapping(self):
        """Dict should map to JSONB."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(Dict, field_info)
        assert col_type == ColumnType.JSONB
        assert native_type == "JSONB"

    def test_dict_typed_mapping(self):
        """Dict with type parameters should still map to JSONB."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(Dict[str, int], field_info)
        assert col_type == ColumnType.JSONB
        assert native_type == "JSONB"

    def test_nested_model_mapping(self):
        """Nested Pydantic model should map to JSONB."""

        class TestModel(BaseModel):
            name: str
            value: int

        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(TestModel, field_info)
        assert col_type == ColumnType.JSONB
        assert native_type == "JSONB"


class TestOptionalTypeMapping:
    """Test mapping of Optional types."""

    def test_optional_uuid_mapping(self):
        """Optional[UUID] should map to UUID (nullable is handled separately)."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(Optional[UUID], field_info)
        assert col_type == ColumnType.UUID
        assert native_type == "UUID"

    def test_optional_str_mapping(self):
        """Optional[str] should map to VARCHAR."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(Optional[str], field_info)
        assert col_type == ColumnType.STRING
        assert native_type == "VARCHAR(255)"

    def test_optional_list_uuid_mapping(self):
        """Optional[List[UUID]] should map to UUID[] array."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(Optional[List[UUID]], field_info)
        assert col_type == ColumnType.ARRAY
        assert native_type == "UUID[]"


class TestCustomTypeOverride:
    """Test custom type override via metadata."""

    def test_custom_db_type_override(self):
        """db_type in metadata should override default mapping."""
        field_info = Field(json_schema_extra={"db_type": "TEXT"})
        col_type, native_type = map_pydantic_type_to_column_type(str, field_info)
        assert col_type == ColumnType.TEXT
        assert native_type == "TEXT"

    def test_custom_array_type_override(self):
        """Can override list mapping with custom array type."""
        field_info = Field(json_schema_extra={"db_type": "VARCHAR(50)[]"})
        col_type, native_type = map_pydantic_type_to_column_type(List[str], field_info)
        assert col_type == ColumnType.ARRAY
        assert native_type == "VARCHAR(50)[]"

    def test_custom_numeric_type_override(self):
        """Can override numeric type with specific precision."""
        field_info = Field(json_schema_extra={"db_type": "NUMERIC(20,6)"})
        col_type, native_type = map_pydantic_type_to_column_type(Decimal, field_info)
        assert col_type == ColumnType.DECIMAL
        assert native_type == "NUMERIC(20,6)"


class TestEdgeCases:
    """Test edge cases and fallback behavior."""

    def test_unknown_type_fallback(self):
        """Unknown types should fallback to TEXT."""

        class CustomClass:
            pass

        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(CustomClass, field_info)
        assert col_type == ColumnType.TEXT
        assert native_type == "TEXT"

    def test_none_type_fallback(self):
        """None type should fallback to TEXT."""
        field_info = Field()
        col_type, native_type = map_pydantic_type_to_column_type(type(None), field_info)
        assert col_type == ColumnType.TEXT
        assert native_type == "TEXT"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
