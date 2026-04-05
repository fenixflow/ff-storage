"""ERD data models for Entity Relationship Diagram generation.

This module provides Pydantic models representing ERD components:
- ERDColumn: Column definition with type, constraints, and FK info
- ERDTable: Table definition with columns and metadata
- ERDRelationship: Relationship between tables
- ERDResponse: Complete ERD with tables and relationships
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ERDColumn(BaseModel):
    """Column definition in ERD.

    Attributes:
        name: Column name
        type: SQL or Python type name
        nullable: Whether column allows NULL
        is_primary_key: Whether column is primary key
        is_foreign_key: Whether column is foreign key
        description: Optional column description
    """

    name: str
    type: str
    nullable: bool
    is_primary_key: bool = False
    is_foreign_key: bool = False
    description: str | None = None


class ERDTable(BaseModel):
    """Table definition in ERD.

    Attributes:
        name: Table name (e.g., "users", "products")
        schema_name: Database schema (e.g., "public")
        model_class: Python class name (e.g., "User", "Product")
        is_multi_tenant: Whether table has tenant_id column
        temporal_strategy: Temporal strategy (none, copy_on_change, scd2)
        columns: List of column definitions
    """

    name: str
    schema_name: str
    model_class: str
    is_multi_tenant: bool
    temporal_strategy: str | None
    columns: list[ERDColumn]


class ERDRelationship(BaseModel):
    """Relationship between tables in ERD.

    Attributes:
        from_table: Source table name
        from_column: Source column name (FK column)
        to_table: Target table name
        to_column: Target column name (usually "id")
        relationship_type: Type of relationship (many_to_one, one_to_many, many_to_many)
        cardinality: Cardinality notation (1:N, N:1, N:M)
    """

    from_table: str
    from_column: str
    to_table: str
    to_column: str
    relationship_type: str  # "many_to_one", "one_to_many", "many_to_many"
    cardinality: str  # "1:N", "N:1", "N:M"


class ERDResponse(BaseModel):
    """Full ERD response with tables and relationships.

    Attributes:
        tables: List of table definitions
        relationships: List of relationships between tables
        schemas: List of database schemas found
        generated_at: Timestamp when ERD was generated
    """

    tables: list[ERDTable]
    relationships: list[ERDRelationship]
    schemas: list[str]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
