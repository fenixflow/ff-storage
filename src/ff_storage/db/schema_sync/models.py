"""
Provider-agnostic schema data models.

These models represent database schema elements in a way that works
across PostgreSQL, MySQL, and SQL Server.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ColumnType(Enum):
    """Database-agnostic column types."""

    UUID = "uuid"
    STRING = "string"
    TEXT = "text"
    INTEGER = "integer"
    BIGINT = "bigint"
    BOOLEAN = "boolean"
    TIMESTAMP = "timestamp"
    TIMESTAMPTZ = "timestamptz"
    JSONB = "jsonb"
    ARRAY = "array"
    DECIMAL = "decimal"


class ChangeType(Enum):
    """Schema change types."""

    # Additive (safe - auto-apply)
    CREATE_TABLE = "create_table"
    ADD_COLUMN = "add_column"
    ADD_INDEX = "add_index"
    ADD_CONSTRAINT = "add_constraint"

    # Destructive (dangerous - require confirmation)
    DROP_TABLE = "drop_table"
    DROP_COLUMN = "drop_column"
    DROP_INDEX = "drop_index"
    ALTER_COLUMN_TYPE = "alter_column_type"
    DROP_CONSTRAINT = "drop_constraint"


@dataclass
class ColumnDefinition:
    """Database-agnostic column definition."""

    name: str
    column_type: ColumnType
    nullable: bool = True
    default: Optional[str] = None
    max_length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None
    is_primary_key: bool = False
    is_foreign_key: bool = False
    references: Optional[str] = None
    native_type: Optional[str] = None  # Provider-specific (e.g., "UUID", "VARCHAR(255)")


@dataclass
class IndexDefinition:
    """Database-agnostic index definition."""

    name: str
    table_name: str
    columns: List[str]
    unique: bool = False
    index_type: str = "btree"
    where_clause: Optional[str] = None


@dataclass
class TableDefinition:
    """Complete table schema."""

    name: str
    schema: str
    columns: List[ColumnDefinition] = field(default_factory=list)
    indexes: List[IndexDefinition] = field(default_factory=list)


@dataclass
class SchemaChange:
    """Represents a schema change to be applied."""

    change_type: ChangeType
    table_name: str
    is_destructive: bool
    sql: str
    description: str
    column: Optional[ColumnDefinition] = None
    index: Optional[IndexDefinition] = None
