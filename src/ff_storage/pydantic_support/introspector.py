"""
Schema introspection for Pydantic models.

Extracts database table definitions from Pydantic models, including:
- Column definitions with types and constraints
- Index definitions
- Temporal fields (auto-injected)
- Constraints (unique, foreign key, etc.)
"""

from typing import Any, Optional, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from ..db.schema_sync.models import (
    ColumnDefinition,
    ColumnType,
    IndexDefinition,
    TableDefinition,
)
from .type_mapping import map_pydantic_type_to_column_type


class PydanticSchemaIntrospector:
    """
    Extract database schema definitions from Pydantic models.

    This class bridges Pydantic's validation system with ff-storage's
    schema synchronization system.
    """

    def extract_table_definition(self, pydantic_model: type[BaseModel]) -> TableDefinition:
        """
        Convert Pydantic model to TableDefinition.

        Process:
        1. Extract user-defined fields → ColumnDefinitions
        2. Auto-inject temporal fields based on __temporal_strategy__
        3. Extract indexes from field metadata
        4. Add temporal indexes

        Args:
            pydantic_model: Pydantic model class

        Returns:
            TableDefinition ready for SchemaManager

        Example:
            >>> introspector = PydanticSchemaIntrospector()
            >>> table_def = introspector.extract_table_definition(User)
            >>> print(table_def.columns)
            [
                ColumnDefinition(name='id', column_type=ColumnType.UUID, ...),
                ColumnDefinition(name='email', column_type=ColumnType.STRING, ...),
                ...,
            ]
        """
        table_name = pydantic_model.table_name()
        schema = pydantic_model.__schema__

        # Step 1: Extract user-defined fields
        columns = []
        indexes = []

        for field_name, field_info in pydantic_model.model_fields.items():
            # Create column definition
            column = self._extract_column_definition(field_name, field_info, pydantic_model)
            columns.append(column)

            # Create index if specified in metadata
            if self._should_create_index(field_info):
                index = self._create_index_definition(table_name, field_name, field_info)
                indexes.append(index)

        # Step 2: Auto-inject temporal fields
        if hasattr(pydantic_model, "get_temporal_fields"):
            temporal_fields = pydantic_model.get_temporal_fields()
            for field_name, (field_type, default_value) in temporal_fields.items():
                # Skip if field already exists (user-defined)
                if field_name in pydantic_model.model_fields:
                    continue

                column = self._create_temporal_column(field_name, field_type, default_value)
                columns.append(column)

        # Step 3: Add temporal indexes
        if hasattr(pydantic_model, "get_temporal_indexes"):
            temporal_indexes = pydantic_model.get_temporal_indexes()
            for idx_def in temporal_indexes:
                index = IndexDefinition(**idx_def)
                indexes.append(index)

        # Step 4: Handle SCD2 primary key special case
        # For SCD2 strategy, we need to remove PRIMARY KEY from `id` column
        # because SCD2 allows multiple versions of the same logical record
        # (same id, different version). The UNIQUE constraint on (id, version)
        # from get_temporal_indexes() handles uniqueness instead.
        if hasattr(pydantic_model, "__temporal_strategy__"):
            strategy = pydantic_model.__temporal_strategy__
            if strategy == "scd2":
                # Find and modify the id column to remove PRIMARY KEY
                for column in columns:
                    if column.name == "id" and column.is_primary_key:
                        # Create a new column definition without PRIMARY KEY
                        column.is_primary_key = False

        return TableDefinition(
            name=table_name,
            schema=schema,
            columns=columns,
            indexes=indexes,
        )

    def _extract_column_definition(
        self,
        field_name: str,
        field_info: FieldInfo,
        model_class: type[BaseModel],
    ) -> ColumnDefinition:
        """
        Extract ColumnDefinition from Pydantic Field.

        Args:
            field_name: Name of the field
            field_info: Pydantic FieldInfo object
            model_class: Model class (for context)

        Returns:
            ColumnDefinition for this field
        """
        # Get type annotation
        field_type = field_info.annotation

        # Map Pydantic type → ColumnType
        column_type, native_type = map_pydantic_type_to_column_type(field_type, field_info)

        # Extract metadata
        metadata = field_info.json_schema_extra or {}

        # Determine nullable
        nullable = self._is_nullable(field_type, field_info)

        # Extract constraints (max_length will be in native_type from type_mapping)
        max_length = metadata.get("max_length", None)

        # Extract default value (db_default takes precedence over Pydantic default)
        default = metadata.get("db_default") or self._extract_default(field_info)

        # Override nullable if db_nullable is explicitly set
        if "db_nullable" in metadata:
            nullable = metadata["db_nullable"]

        # Extract FK reference
        fk_reference = metadata.get("db_foreign_key", None)
        is_fk = fk_reference is not None

        return ColumnDefinition(
            name=field_name,
            column_type=column_type,
            nullable=nullable,
            default=default,
            max_length=max_length,
            is_primary_key=metadata.get("db_primary_key", False),
            is_foreign_key=is_fk,
            references=fk_reference,
            native_type=native_type,
        )

    def _is_nullable(self, field_type: type, field_info: FieldInfo) -> bool:
        """
        Determine if field is nullable in the database.

        A field is nullable if:
        1. It's typed as Optional[T] (Union[T, None])
        2. It's not required AND has no default (Pydantic will set to None)

        A field is NOT nullable if:
        1. It's a required field (Field(...))
        2. It has a default or default_factory (always has a value)

        Args:
            field_type: Python type annotation
            field_info: Pydantic FieldInfo

        Returns:
            True if nullable, False otherwise
        """
        # Check if Optional[T] (Union[T, None])
        origin = get_origin(field_type)
        if origin is type(None) or str(origin) == "typing.Union":
            args = get_args(field_type)
            if len(args) == 2 and type(None) in args:
                return True

        # If field is NOT required and has NO default, it's implicitly Optional
        # (Pydantic will set it to None if not provided)
        if (
            not field_info.is_required()
            and field_info.default is None
            and field_info.default_factory is None
        ):
            return True

        # Otherwise: NOT nullable
        # - Required fields: Field(...) → NOT NULL
        # - Fields with defaults/factories → NOT NULL (always have value)
        return False

    def _extract_default(self, field_info: FieldInfo) -> Optional[str]:
        """
        Extract default value as SQL string.

        Args:
            field_info: Pydantic FieldInfo

        Returns:
            SQL default expression or None
        """
        if field_info.default is not None:
            default_val = field_info.default

            # Handle special defaults
            if callable(default_val):
                # Functions like uuid4, datetime.now → handle in SQL
                return None
            elif isinstance(default_val, bool):
                return str(default_val).upper()
            elif isinstance(default_val, (int, float)):
                return str(default_val)
            elif isinstance(default_val, str):
                return f"'{default_val}'"

        return None

    def _should_create_index(self, field_info: FieldInfo) -> bool:
        """
        Check if field should have an index.

        Args:
            field_info: Pydantic FieldInfo

        Returns:
            True if index should be created
        """
        metadata = field_info.json_schema_extra or {}
        return metadata.get("db_index", False) or metadata.get("db_unique", False)

    def _create_index_definition(
        self,
        table_name: str,
        field_name: str,
        field_info: FieldInfo,
    ) -> IndexDefinition:
        """
        Create IndexDefinition from field metadata.

        Supports partial indexes via db_index_where parameter.

        Args:
            table_name: Name of the table
            field_name: Name of the field
            field_info: Pydantic FieldInfo with metadata

        Returns:
            IndexDefinition for this field
        """
        metadata = field_info.json_schema_extra or {}

        # Generate index name
        index_name = metadata.get("db_index_name", f"idx_{table_name}_{field_name}")

        # Extract index properties
        unique = metadata.get("db_unique", False)
        index_type = metadata.get("db_index_type", "btree")
        where_clause = metadata.get("db_index_where", None)  # Partial index support

        # Handle multi-column indexes
        columns = metadata.get("db_index_columns", [field_name])
        if isinstance(columns, str):
            columns = [columns]

        return IndexDefinition(
            name=index_name,
            table_name=table_name,
            columns=columns,
            unique=unique,
            index_type=index_type,
            where_clause=where_clause,
        )

    def _create_temporal_column(
        self,
        field_name: str,
        field_type: type,
        default_value: Any,
    ) -> ColumnDefinition:
        """
        Create ColumnDefinition for auto-injected temporal field.

        Args:
            field_name: Name of the temporal field
            field_type: Python type (datetime, int, etc.)
            default_value: Default value or SQL expression

        Returns:
            ColumnDefinition for temporal field
        """
        from datetime import datetime
        from typing import get_args, get_origin
        from uuid import UUID

        # Check if Optional
        origin = get_origin(field_type)
        if origin is type(None) or str(origin) == "typing.Union":
            args = get_args(field_type)
            if len(args) == 2 and type(None) in args:
                nullable = True
                field_type = args[0] if args[1] is type(None) else args[1]
            else:
                nullable = False
        else:
            nullable = False

        # Map type to ColumnType
        if field_type == datetime or "datetime" in str(field_type):
            column_type = ColumnType.TIMESTAMPTZ
            native_type = "TIMESTAMP WITH TIME ZONE"
        elif field_type is int:
            column_type = ColumnType.INTEGER
            native_type = "INTEGER"
        elif field_type == UUID or "UUID" in str(field_type):
            column_type = ColumnType.UUID
            native_type = "UUID"
        else:
            column_type = ColumnType.STRING
            native_type = "TEXT"

        # Format default value
        if default_value == "NOW()":
            default_sql = "NOW()"
        elif isinstance(default_value, int):
            default_sql = str(default_value)
        else:
            default_sql = None

        return ColumnDefinition(
            name=field_name,
            column_type=column_type,
            nullable=nullable,
            default=default_sql,
            native_type=native_type,
        )
