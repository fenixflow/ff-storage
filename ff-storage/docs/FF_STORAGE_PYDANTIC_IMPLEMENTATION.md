# ff-storage Pydantic Integration - Complete Implementation Guide

**Version:** 3.0.0 (Pydantic Support)
**Status:** Design Document
**Date:** 2025-01-20

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Module Structure](#module-structure)
4. [Core Components](#core-components)
5. [Temporal Strategy System](#temporal-strategy-system)
6. [Type Mapping System](#type-mapping-system)
7. [Field Metadata System](#field-metadata-system)
8. [SchemaManager Integration](#schemamanager-integration)
9. [Repository Pattern](#repository-pattern)
10. [Implementation Phases](#implementation-phases)
11. [Testing Strategy](#testing-strategy)
12. [Migration Guide](#migration-guide)
13. [API Reference](#api-reference)

---

## Executive Summary

This document specifies the complete implementation of Pydantic support for ff-storage, transforming it into **the definitive foundation for API-centric platforms**.

### Key Features

- **Automatic Temporal Management**: Declare strategy, ff-storage manages all temporal fields and logic
- **Zero-SQL Schema Evolution**: Pydantic models automatically sync to database
- **Type-Safe CRUD**: Generic repository with full Pydantic integration
- **Multi-Strategy Support**: none, copy_on_change, scd2, soft_delete
- **Provider-Agnostic**: PostgreSQL (full), MySQL/SQL Server (future)

### Benefits

- **Single Source of Truth**: Pydantic model = API schema = Database schema
- **Zero Migration Files**: Additive changes applied automatically
- **Production-Ready**: Temporal versioning, soft deletes, audit trails built-in
- **Backwards Compatible**: Existing dataclass models continue to work

---

## Architecture Overview

### Design Philosophy

1. **Convention over Configuration**: Smart defaults, explicit overrides
2. **Automatic Field Injection**: Temporal fields added based on strategy
3. **Provider Abstraction**: Same API across PostgreSQL/MySQL/SQL Server
4. **Safety First**: Additive changes auto-apply, destructive changes require approval

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     User Application                         │
│  (Defines Pydantic models with __temporal_strategy__)       │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  ff-storage Core                             │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           PydanticModel (Base Class)                 │  │
│  │  - Automatic temporal field injection                │  │
│  │  - Table name/schema management                      │  │
│  │  - SQL generation hooks                              │  │
│  └──────────────────────────────────────────────────────┘  │
│                          │                                   │
│         ┌────────────────┼────────────────┐                │
│         ▼                ▼                ▼                 │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐       │
│  │ Introspector│  │   Type      │  │  Repository  │       │
│  │             │  │   Mapper    │  │              │       │
│  │ Pydantic    │  │             │  │  Generic     │       │
│  │ → Table     │  │ Pydantic    │  │  CRUD with   │       │
│  │ Definition  │  │ → SQL       │  │  Temporal    │       │
│  └─────────────┘  └─────────────┘  └──────────────┘       │
│         │                │                │                 │
└─────────┼────────────────┼────────────────┼─────────────────┘
          │                │                │
          └────────────────┼────────────────┘
                           ▼
          ┌────────────────────────────────┐
          │       SchemaManager            │
          │  - Auto-detect Pydantic models │
          │  - Generate migrations         │
          │  - Apply changes (Terraform)   │
          └────────────────────────────────┘
                           │
                           ▼
          ┌────────────────────────────────┐
          │  Database (PostgreSQL/etc)     │
          │  - Tables with temporal fields │
          │  - Indexes auto-generated      │
          │  - Triggers (if needed)        │
          └────────────────────────────────┘
```

---

## Module Structure

### New Directory Structure

```
ff-storage/
├── src/
│   └── ff_storage/
│       ├── db/
│       │   ├── connections/          # Existing
│       │   ├── schema_sync/          # Existing (enhanced)
│       │   └── models.py             # Existing dataclass models (keep)
│       │
│       ├── pydantic_support/         # NEW MODULE
│       │   ├── __init__.py
│       │   ├── base.py               # PydanticModel base class
│       │   ├── introspector.py       # Schema extraction
│       │   ├── repository.py         # Generic CRUD repository
│       │   ├── type_mapping.py       # Pydantic → SQL type mapping
│       │   ├── field_metadata.py     # Field metadata extractors
│       │   └── temporal.py           # Temporal strategy definitions
│       │
│       └── __init__.py               # Export PydanticModel, PydanticRepository
│
├── tests/
│   └── pydantic_support/             # NEW TEST SUITE
│       ├── test_base.py
│       ├── test_introspector.py
│       ├── test_repository.py
│       ├── test_type_mapping.py
│       └── test_temporal_strategies.py
│
└── docs/
    ├── FF_STORAGE_PYDANTIC_IMPLEMENTATION.md  # This document
    └── examples/
        ├── basic_model.py
        ├── temporal_scd2.py
        ├── temporal_soft_delete.py
        └── multi_tenant.py
```

---

## Core Components

### 1. PydanticModel Base Class

**File:** `src/ff_storage/pydantic_support/base.py`

```python
"""
Pydantic base model with automatic temporal management.

This module provides the foundational PydanticModel class that integrates
Pydantic with ff-storage's schema synchronization and repository systems.
"""

from datetime import datetime, timezone
from typing import Any, ClassVar, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class PydanticModel(BaseModel):
    """
    Base Pydantic model for ff-storage integration.

    Features:
    - Automatic temporal field injection based on strategy
    - Table name and schema management
    - SQL generation for SchemaManager
    - Backwards compatible with existing ff-storage patterns

    Temporal Strategies:
    - "none": No temporal fields (only id, created_at, updated_at)
    - "copy_on_change": Traditional UPDATE with updated_at timestamp
    - "scd2": Slowly Changing Dimension Type 2 (immutable versions)
    - "soft_delete": Soft delete only (deleted_at field)

    Example:
        ```python
        class User(PydanticModel):
            __table_name__ = "users"
            __schema__ = "public"
            __temporal_strategy__ = "soft_delete"

            email: str = Field(max_length=255, json_schema_extra={"db_unique": True})
            name: str
            age: int = Field(ge=0, le=150)
        ```

    Class Variables:
        __table_name__: Override default table name (default: class name + 's')
        __schema__: Database schema (default: "public")
        __temporal_strategy__: Temporal versioning strategy (default: "copy_on_change")
        __tenant_field__: Field name for multi-tenancy (default: None)
    """

    # Pydantic v2 configuration
    model_config = ConfigDict(
        from_attributes=True,        # Support ORM mode (row → model)
        arbitrary_types_allowed=True, # Allow UUID, datetime, etc.
        validate_assignment=True,     # Validate on field assignment
        populate_by_name=True,        # Allow field population by name
    )

    # Class-level metadata for ff-storage
    __table_name__: ClassVar[Optional[str]] = None
    __schema__: ClassVar[str] = "public"
    __temporal_strategy__: ClassVar[str] = "copy_on_change"
    __tenant_field__: ClassVar[Optional[str]] = None  # For multi-tenancy

    # Standard fields (present in ALL models)
    id: UUID = Field(
        default_factory=uuid4,
        description="Primary key UUID",
        json_schema_extra={
            "db_primary_key": True,
            "db_index": True,
        }
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Record creation timestamp (UTC)",
        json_schema_extra={
            "db_index": True,
            "db_order": "DESC",
        }
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update timestamp (UTC)",
        json_schema_extra={
            "db_index": True,
        }
    )

    # ==================== Table Name Management ====================

    @classmethod
    def table_name(cls) -> str:
        """
        Get database table name.

        Returns:
            Table name (without schema prefix)

        Example:
            >>> User.table_name()
            'users'
        """
        if cls.__table_name__:
            return cls.__table_name__
        return cls.__name__.lower() + "s"

    @classmethod
    def full_table_name(cls) -> str:
        """
        Get fully qualified table name (schema.table).

        Returns:
            Full table name with schema prefix

        Example:
            >>> User.full_table_name()
            'public.users'
        """
        return f"{cls.__schema__}.{cls.table_name()}"

    # ==================== Temporal Field Injection ====================

    @classmethod
    def get_temporal_fields(cls) -> dict[str, tuple[type, Any]]:
        """
        Get temporal fields to inject based on strategy.

        This method is called by PydanticSchemaIntrospector to automatically
        add temporal fields to the table schema.

        Returns:
            Dict mapping field_name → (type, default_value)

        Example:
            >>> AtomicRule.__temporal_strategy__ = "scd2"
            >>> AtomicRule.get_temporal_fields()
            {
                'valid_from': (datetime, 'NOW()'),
                'valid_to': (Optional[datetime], None),
                'version': (int, 1),
                'deleted_at': (Optional[datetime], None),
                'deleted_by': (Optional[UUID], None),
            }
        """
        from typing import Optional

        strategy = cls.__temporal_strategy__
        fields = {}

        if strategy == "none":
            # No additional temporal fields
            return fields

        # Soft delete fields (for scd2 and soft_delete)
        if strategy in ("scd2", "soft_delete"):
            fields["deleted_at"] = (Optional[datetime], None)
            fields["deleted_by"] = (Optional[UUID], None)

        # SCD2-specific fields
        if strategy == "scd2":
            fields["valid_from"] = (datetime, "NOW()")
            fields["valid_to"] = (Optional[datetime], None)
            fields["version"] = (int, 1)

        return fields

    @classmethod
    def get_temporal_indexes(cls) -> list[dict[str, Any]]:
        """
        Get index definitions for temporal fields.

        Returns:
            List of index definition dicts

        Example:
            >>> AtomicRule.get_temporal_indexes()
            [
                {
                    'name': 'idx_atomic_rules_valid_period',
                    'columns': ['valid_from', 'valid_to'],
                    'type': 'btree',
                },
                {
                    'name': 'idx_atomic_rules_current',
                    'columns': ['id'],
                    'where': 'valid_to IS NULL AND deleted_at IS NULL',
                },
            ]
        """
        strategy = cls.__temporal_strategy__
        table_name = cls.table_name()
        indexes = []

        if strategy == "scd2":
            # Index on valid period for temporal queries
            indexes.append({
                "name": f"idx_{table_name}_valid_period",
                "table_name": table_name,
                "columns": ["valid_from", "valid_to"],
                "index_type": "btree",
            })

            # Partial index for current version (most common query)
            indexes.append({
                "name": f"idx_{table_name}_current",
                "table_name": table_name,
                "columns": ["id"],
                "where": "valid_to IS NULL AND deleted_at IS NULL",
            })

        if strategy in ("scd2", "soft_delete"):
            # Partial index for non-deleted records
            indexes.append({
                "name": f"idx_{table_name}_not_deleted",
                "table_name": table_name,
                "columns": ["deleted_at"],
                "where": "deleted_at IS NULL",
            })

        return indexes

    # ==================== SQL Generation (SchemaManager Integration) ====================

    @classmethod
    def get_create_table_sql(cls) -> str:
        """
        Generate CREATE TABLE SQL for this model.

        Called by SchemaManager.sync_schema() to generate table schema.
        Uses PydanticSchemaIntrospector to extract table definition,
        then PostgresMigrationGenerator to create SQL.

        Returns:
            CREATE TABLE statement with all columns and indexes

        Example:
            >>> print(User.get_create_table_sql())
            CREATE TABLE IF NOT EXISTS public.users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                email VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                age INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_users_created_at ON public.users(created_at DESC);
            ...
        """
        # Import here to avoid circular dependency
        from ff_storage.pydantic_support.introspector import PydanticSchemaIntrospector
        from ff_storage.db.schema_sync.postgres import PostgresMigrationGenerator

        # Extract table definition from Pydantic model
        introspector = PydanticSchemaIntrospector()
        table_def = introspector.extract_table_definition(cls)

        # Generate SQL using existing migration generator
        generator = PostgresMigrationGenerator()
        create_table_sql = generator.generate_create_table(table_def)

        # Generate index SQL
        index_sqls = [
            generator.generate_create_index(cls.__schema__, index)
            for index in table_def.indexes
        ]

        # Combine table + indexes
        all_sql = [create_table_sql] + index_sqls
        return "\n".join(all_sql)

    @classmethod
    def get_table_name(cls) -> str:
        """Alias for table_name() for SchemaManager compatibility."""
        return cls.table_name()

    # ==================== Instance Methods ====================

    def update_timestamp(self) -> None:
        """Update the updated_at field to current UTC time."""
        self.updated_at = datetime.now(timezone.utc)
```

---

### 2. PydanticSchemaIntrospector

**File:** `src/ff_storage/pydantic_support/introspector.py`

```python
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

from ff_storage.db.schema_sync.models import (
    ColumnDefinition,
    ColumnType,
    IndexDefinition,
    TableDefinition,
)


class PydanticSchemaIntrospector:
    """
    Extract database schema definitions from Pydantic models.

    This class bridges Pydantic's validation system with ff-storage's
    schema synchronization system.
    """

    def extract_table_definition(
        self,
        pydantic_model: type[BaseModel]
    ) -> TableDefinition:
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
                ...
            ]
        """
        from ff_storage.pydantic_support.type_mapping import map_pydantic_type_to_column_type

        table_name = pydantic_model.table_name()
        schema = pydantic_model.__schema__

        # Step 1: Extract user-defined fields
        columns = []
        indexes = []

        for field_name, field_info in pydantic_model.model_fields.items():
            # Create column definition
            column = self._extract_column_definition(
                field_name,
                field_info,
                pydantic_model
            )
            columns.append(column)

            # Create index if specified in metadata
            if self._should_create_index(field_info):
                index = self._create_index_definition(
                    table_name,
                    field_name,
                    field_info
                )
                indexes.append(index)

        # Step 2: Auto-inject temporal fields
        temporal_fields = pydantic_model.get_temporal_fields()
        for field_name, (field_type, default_value) in temporal_fields.items():
            column = self._create_temporal_column(field_name, field_type, default_value)
            columns.append(column)

        # Step 3: Add temporal indexes
        temporal_indexes = pydantic_model.get_temporal_indexes()
        for idx_def in temporal_indexes:
            index = IndexDefinition(**idx_def)
            indexes.append(index)

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
        from ff_storage.pydantic_support.type_mapping import map_pydantic_type_to_column_type

        # Get type annotation
        field_type = field_info.annotation

        # Map Pydantic type → ColumnType
        column_type, native_type = map_pydantic_type_to_column_type(
            field_type,
            field_info
        )

        # Extract metadata
        metadata = field_info.json_schema_extra or {}

        # Determine nullable
        nullable = not field_info.is_required()

        # Extract constraints
        max_length = getattr(field_info, "max_length", None)

        # Extract default value
        default = self._extract_default(field_info)

        return ColumnDefinition(
            name=field_name,
            column_type=column_type,
            nullable=nullable,
            default=default,
            max_length=max_length,
            is_primary_key=metadata.get("db_primary_key", False),
            is_foreign_key=metadata.get("db_foreign_key", False),
            references=metadata.get("db_references", None),
            native_type=native_type,
        )

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
        return (
            metadata.get("db_index", False) or
            metadata.get("db_unique", False)
        )

    def _create_index_definition(
        self,
        table_name: str,
        field_name: str,
        field_info: FieldInfo,
    ) -> IndexDefinition:
        """
        Create IndexDefinition from field metadata.

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
        where_clause = metadata.get("db_index_where", None)

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
        from typing import Optional, get_args, get_origin
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
        elif field_type == int or field_type is int:
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
```

---

### 3. Type Mapping System

**File:** `src/ff_storage/pydantic_support/type_mapping.py`

```python
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
from typing import Any, Optional, get_args, get_origin
from uuid import UUID

from pydantic.fields import FieldInfo

from ff_storage.db.schema_sync.models import ColumnType


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

    # Check for custom db_type override
    if "db_type" in metadata:
        custom_type = metadata["db_type"]
        column_type = _parse_custom_type(custom_type)
        return column_type, custom_type

    # Handle Optional[T] / Union[T, None]
    origin = get_origin(python_type)
    if origin is type(None) or str(origin) == "typing.Union":
        args = get_args(python_type)
        if len(args) == 2 and type(None) in args:
            # Extract T from Optional[T]
            python_type = args[0] if args[1] is type(None) else args[1]
            origin = get_origin(python_type)

    # Direct type mappings
    if python_type == UUID or python_type is UUID:
        return ColumnType.UUID, "UUID"

    elif python_type == str or python_type is str:
        max_length = field_info.max_length or 255
        return ColumnType.STRING, f"VARCHAR({max_length})"

    elif python_type == int or python_type is int:
        return ColumnType.INTEGER, "INTEGER"

    elif python_type == bool or python_type is bool:
        return ColumnType.BOOLEAN, "BOOLEAN"

    elif python_type == float or python_type is float:
        return ColumnType.DECIMAL, "DOUBLE PRECISION"

    elif python_type == datetime or python_type is datetime:
        return ColumnType.TIMESTAMPTZ, "TIMESTAMP WITH TIME ZONE"

    elif python_type == date or python_type is date:
        return ColumnType.TIMESTAMP, "DATE"

    elif python_type == Decimal or python_type is Decimal:
        precision = metadata.get("db_precision", 15)
        scale = metadata.get("db_scale", 2)
        return ColumnType.DECIMAL, f"DECIMAL({precision},{scale})"

    # Complex types (list, dict, nested models)
    elif origin is list:
        args = get_args(python_type)
        if args and hasattr(args[0], "model_fields"):
            # List of Pydantic models → JSONB
            return ColumnType.JSONB, "JSONB"
        else:
            # List of primitives → Array
            return ColumnType.ARRAY, "TEXT[]"

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
```

---

## Temporal Strategy System

### Strategy Definitions

**File:** `src/ff_storage/pydantic_support/temporal.py`

```python
"""
Temporal strategy definitions and helpers.

Defines the four temporal strategies supported by ff-storage:
1. none - No temporal fields
2. copy_on_change - Traditional UPDATE
3. scd2 - Slowly Changing Dimension Type 2
4. soft_delete - Soft delete with deleted_at
"""

from enum import Enum


class TemporalStrategy(str, Enum):
    """
    Supported temporal versioning strategies.

    Attributes:
        NONE: No temporal fields, only id/created_at/updated_at
        COPY_ON_CHANGE: Traditional in-place UPDATE with updated_at timestamp
        SCD2: Immutable versions with valid_from/valid_to range
        SOFT_DELETE: Soft delete with deleted_at timestamp
    """

    NONE = "none"
    COPY_ON_CHANGE = "copy_on_change"
    SCD2 = "scd2"
    SOFT_DELETE = "soft_delete"


# Strategy field mapping
STRATEGY_FIELDS = {
    TemporalStrategy.NONE: {},

    TemporalStrategy.COPY_ON_CHANGE: {},

    TemporalStrategy.SCD2: {
        "valid_from": "TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()",
        "valid_to": "TIMESTAMP WITH TIME ZONE",
        "version": "INTEGER NOT NULL DEFAULT 1",
        "deleted_at": "TIMESTAMP WITH TIME ZONE",
        "deleted_by": "UUID",
    },

    TemporalStrategy.SOFT_DELETE: {
        "deleted_at": "TIMESTAMP WITH TIME ZONE",
        "deleted_by": "UUID",
    },
}
```

### Strategy Comparison Table

| Feature | none | copy_on_change | scd2 | soft_delete |
|---------|------|----------------|------|-------------|
| **Fields Added** | None | None | valid_from, valid_to, version, deleted_at, deleted_by | deleted_at, deleted_by |
| **Update Behavior** | UPDATE in place | UPDATE + updated_at | Close old + INSERT new | UPDATE + updated_at |
| **History Tracking** | ❌ No | ✅ Via updated_at | ✅ Full version history | ❌ No |
| **Delete Behavior** | Hard DELETE | Hard DELETE | Set deleted_at | Set deleted_at |
| **Time Travel** | ❌ Not supported | ❌ Not supported | ✅ as_of(date) | ❌ Not supported |
| **Audit Trail** | Basic | Basic | Complete (immutable) | Soft delete only |
| **Storage Cost** | Low | Low | High (all versions) | Low |
| **Use Cases** | Lookup tables, static data | Application data | Regulatory compliance, rules | User data |

---

## Repository Pattern

**File:** `src/ff_storage/pydantic_support/repository.py`

This file is extensive. See the API Reference section for the complete implementation.

### Key Methods

- `async create(model: T) -> T` - Create with automatic temporal field population
- `async update(id: UUID, model: T) -> T` - Update with strategy enforcement
- `async get(id: UUID, as_of: datetime = None) -> T | None` - Get current or historical version
- `async delete(id: UUID, deleted_by: UUID = None) -> bool` - Soft/hard delete
- `async list(filters: dict, ...) -> list[T]` - List with automatic temporal filtering
- `async get_version_history(id: UUID) -> list[T]` - Get all versions (SCD2 only)

---

## SchemaManager Integration

### Enhanced SchemaManager

**File:** `src/ff_storage/db/schema_sync/manager.py` (Enhanced)

The existing SchemaManager already supports Pydantic models via the `get_create_table_sql()` method.

**No changes needed** - PydanticModel implements this interface.

```python
# Existing code in SchemaManager.sync_schema()
for model_class in models:
    if hasattr(model_class, "get_create_table_sql"):
        sql = model_class.get_create_table_sql()
    # ...
```

**PydanticModel** implements `get_create_table_sql()` → Works automatically!

---

## Implementation Phases

### Phase 1: Core Foundation (Week 1)
- [ ] Create `pydantic_support/` module structure
- [ ] Implement `PydanticModel` base class
- [ ] Implement `get_temporal_fields()` and `get_temporal_indexes()`
- [ ] Unit tests for temporal field injection
- [ ] Documentation and examples

**Deliverable:** PydanticModel that generates correct CREATE TABLE SQL

### Phase 2: Schema Introspection (Week 1-2)
- [ ] Implement `PydanticSchemaIntrospector`
- [ ] Implement `map_pydantic_type_to_column_type()`
- [ ] Handle all Python types (UUID, str, int, datetime, Decimal, list, dict)
- [ ] Handle nested Pydantic models (→ JSONB)
- [ ] Unit tests for type mapping
- [ ] Integration tests with SchemaManager

**Deliverable:** Full Pydantic → TableDefinition conversion

### Phase 3: Repository Implementation (Week 2)
- [ ] Implement `PydanticRepository` base CRUD
- [ ] Implement temporal strategy enforcement
  - [ ] `_update_in_place()` (copy_on_change)
  - [ ] `_update_scd2()` (SCD2 with version increment)
- [ ] Implement soft delete logic
- [ ] Implement time-travel queries (`as_of`, `get_version_history`)
- [ ] Integration tests with PostgreSQL
- [ ] Performance benchmarks

**Deliverable:** Fully functional generic repository

### Phase 4: Multi-Tenancy Support (Week 3)
- [ ] Add `__tenant_field__` to PydanticModel
- [ ] Auto-inject tenant_id filtering in repository
- [ ] Add tenant_id to indexes
- [ ] Multi-tenant integration tests
- [ ] Documentation for multi-tenant patterns

**Deliverable:** Multi-tenant repository support

### Phase 5: Documentation & Examples (Week 3)
- [ ] Complete API reference documentation
- [ ] Create example applications
  - [ ] Basic CRUD app
  - [ ] SCD2 audit trail example
  - [ ] Multi-tenant SaaS example
- [ ] Migration guide from dataclass models
- [ ] Video walkthrough (optional)

**Deliverable:** Production-ready documentation

### Phase 6: MySQL/SQL Server Support (Future)
- [ ] Implement MySQL introspector
- [ ] Implement MySQL migration generator
- [ ] Implement SQL Server support
- [ ] Cross-database compatibility tests

**Deliverable:** Multi-database support

---

## Testing Strategy

### Unit Tests

**Directory:** `tests/pydantic_support/`

1. **test_base.py** - PydanticModel tests
   - Test temporal field injection for each strategy
   - Test index generation
   - Test table name resolution
   - Test SQL generation

2. **test_introspector.py** - Schema extraction tests
   - Test column extraction from Pydantic fields
   - Test all type mappings
   - Test nested model handling
   - Test metadata extraction

3. **test_type_mapping.py** - Type conversion tests
   - Test all Python types → SQL types
   - Test Optional handling
   - Test custom db_type overrides
   - Test complex types (list, dict)

4. **test_temporal_strategies.py** - Strategy tests
   - Test each strategy in isolation
   - Test field injection
   - Test index generation

5. **test_repository.py** - Repository tests
   - Test CRUD operations for each strategy
   - Test version history
   - Test time travel
   - Test soft delete
   - Test multi-tenancy

### Integration Tests

**Directory:** `tests/integration/pydantic_support/`

1. **test_schema_sync.py** - SchemaManager integration
   - Test full model → database sync
   - Test additive changes (add column)
   - Test index creation
   - Test temporal field handling

2. **test_repository_postgres.py** - Real database tests
   - Test against live PostgreSQL instance
   - Test all CRUD operations
   - Test concurrent updates
   - Test transaction handling

### Performance Tests

**Directory:** `tests/performance/`

1. **test_repository_performance.py**
   - Benchmark create/update/list operations
   - Compare temporal strategies
   - Test with large datasets (10k+ records)

---

## Migration Guide

### From Dataclass Models to Pydantic

#### Before (Dataclass)

```python
from dataclasses import dataclass
from ff_storage.db.models import BaseModel

@dataclass
class User(BaseModel):
    email: str
    name: str
```

#### After (Pydantic)

```python
from pydantic import Field
from ff_storage import PydanticModel

class User(PydanticModel):
    __table_name__ = "users"
    __temporal_strategy__ = "soft_delete"

    email: str = Field(max_length=255, json_schema_extra={"db_unique": True})
    name: str = Field(max_length=255)
```

### Migration Checklist

- [ ] Update base class: `BaseModel` → `PydanticModel`
- [ ] Add Field() definitions with constraints
- [ ] Set `__temporal_strategy__`
- [ ] Add `json_schema_extra` for db metadata (indexes, unique, etc.)
- [ ] Test CREATE TABLE SQL generation
- [ ] Run SchemaManager sync in dry_run mode
- [ ] Apply schema changes
- [ ] Update repository instantiation
- [ ] Run tests

---

## API Reference

### PydanticModel

**Class:** `ff_storage.pydantic_support.PydanticModel`

**Class Variables:**
- `__table_name__: ClassVar[Optional[str]]` - Override table name
- `__schema__: ClassVar[str]` - Database schema (default: "public")
- `__temporal_strategy__: ClassVar[str]` - Temporal strategy (default: "copy_on_change")
- `__tenant_field__: ClassVar[Optional[str]]` - Multi-tenancy field name

**Instance Fields:**
- `id: UUID` - Primary key (auto-generated)
- `created_at: datetime` - Creation timestamp (auto-set)
- `updated_at: datetime` - Update timestamp (auto-set)

**Methods:**

`table_name() -> str` (classmethod)
- Returns table name without schema prefix

`full_table_name() -> str` (classmethod)
- Returns schema.table format

`get_temporal_fields() -> dict[str, tuple[type, Any]]` (classmethod)
- Returns temporal fields to inject based on strategy

`get_temporal_indexes() -> list[dict]` (classmethod)
- Returns index definitions for temporal fields

`get_create_table_sql() -> str` (classmethod)
- Generates CREATE TABLE SQL for SchemaManager

`update_timestamp() -> None`
- Updates updated_at to current UTC time

### PydanticRepository

**Class:** `ff_storage.pydantic_support.PydanticRepository[T]`

**Constructor:**
```python
def __init__(
    self,
    model_class: type[T],
    db_pool,  # PostgresPool or similar
    logger=None,
    tenant_id: str = None,  # For multi-tenancy
)
```

**Methods:**

`async create(model: T) -> T`
- Create new record with automatic temporal field population

`async update(id: UUID, model: T) -> T`
- Update record with temporal strategy enforcement

`async get(id: UUID, as_of: datetime = None) -> T | None`
- Get record (current version or historical via as_of)

`async delete(id: UUID, deleted_by: UUID = None) -> bool`
- Delete record (soft or hard depending on strategy)

`async list(filters: dict = None, limit: int = 100, offset: int = 0, include_deleted: bool = False, as_of: datetime = None) -> list[T]`
- List records with automatic temporal filtering

`async count(filters: dict = None, include_deleted: bool = False) -> int`
- Count records matching filters

`async get_version_history(id: UUID) -> list[T]`
- Get all versions (SCD2 only)

### Field Metadata

**json_schema_extra Options:**

```python
Field(
    max_length=255,
    json_schema_extra={
        "db_index": bool,              # Create index
        "db_unique": bool,             # Create unique index
        "db_index_type": str,          # Index type (btree, gin, etc.)
        "db_index_where": str,         # Partial index WHERE clause
        "db_primary_key": bool,        # Mark as primary key
        "db_foreign_key": bool,        # Mark as foreign key
        "db_references": str,          # Foreign key reference (schema.table.column)
        "db_type": str,                # Custom SQL type override
        "db_precision": int,           # Decimal precision
        "db_scale": int,               # Decimal scale
    }
)
```

---

## Summary

This implementation provides:

✅ **Automatic temporal management** - Declare strategy, ff-storage handles the rest
✅ **Zero-SQL schema evolution** - Pydantic models auto-sync to database
✅ **Type-safe CRUD** - Generic repository with full Pydantic support
✅ **Production-ready** - Temporal versioning, soft deletes, audit trails
✅ **Multi-tenant ready** - Built-in tenant isolation
✅ **Backwards compatible** - Dataclass models still work

**Next Steps:** See `IX_DS_MIGRATION_PLAN.md` for ix-ds integration.