"""
Pydantic base model with automatic temporal management.

This module provides the foundational PydanticModel class that integrates
Pydantic with ff-storage's temporal and schema synchronization systems.
"""

from datetime import datetime, timezone
from typing import Any, ClassVar, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from pydantic.fields import FieldInfo

from ..db.query_builder import PostgresQueryBuilder
from ..temporal.enums import TemporalStrategyType


class PydanticModel(BaseModel):
    """
    Base Pydantic model for ff-storage integration.

    Features:
    - Automatic temporal field injection based on strategy
    - Table name and schema management
    - SQL generation for SchemaManager
    - Soft delete and multi-tenant support (enabled by default)
    - Backwards compatible with existing ff-storage patterns

    Temporal Strategies:
    - "none": No temporal tracking (only id, created_at, updated_at)
    - "copy_on_change": Field-level audit trail
    - "scd2": Slowly Changing Dimension Type 2 (immutable versions)

    Example:
        ```python
        class User(PydanticModel):
            __table_name__ = "users"
            __schema__ = "public"
            __temporal_strategy__ = "copy_on_change"
            __soft_delete__ = True      # Default
            __multi_tenant__ = True     # Default

            email: str = Field(max_length=255, json_schema_extra={"db_unique": True})
            name: str
            age: int = Field(ge=0, le=150)
        ```

    Class Variables:
        __table_name__: Override default table name (default: class name + 's')
        __schema__: Database schema (default: "public")
        __temporal_strategy__: Temporal strategy (default: "none")
        __soft_delete__: Enable soft delete (default: True)
        __multi_tenant__: Enable multi-tenancy (default: True)
        __tenant_field__: Field name for multi-tenancy (default: "tenant_id")
    """

    # Pydantic v2 configuration
    model_config = ConfigDict(
        from_attributes=True,  # Support ORM mode (row → model)
        arbitrary_types_allowed=True,  # Allow UUID, datetime, etc.
        validate_assignment=True,  # Validate on field assignment
        populate_by_name=True,  # Allow field population by name
    )

    # Class-level metadata for ff-storage
    __table_name__: ClassVar[Optional[str]] = None
    __schema__: ClassVar[str] = "public"
    __temporal_strategy__: ClassVar[str] = "none"
    __soft_delete__: ClassVar[bool] = True  # Default: enabled
    __multi_tenant__: ClassVar[bool] = True  # Default: enabled
    __tenant_field__: ClassVar[str] = "tenant_id"

    # Standard fields (present in ALL models)
    id: UUID = Field(
        default_factory=uuid4,
        description="Primary key UUID",
        json_schema_extra={
            "db_primary_key": True,
            "db_index": True,
        },
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Record creation timestamp (UTC)",
        json_schema_extra={
            "db_index": True,
            "db_order": "DESC",
        },
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update timestamp (UTC)",
        json_schema_extra={
            "db_index": True,
        },
    )

    created_by: Optional[UUID] = Field(
        default=None,
        description="User who created this record",
    )

    updated_by: Optional[UUID] = Field(
        default=None,
        description="User who last updated this record",
    )

    # ==================== Dynamic Field Injection ====================

    def __init_subclass__(cls, **kwargs):
        """
        Dynamically inject temporal fields based on configuration.

        This method runs when a subclass of PydanticModel is created and
        automatically adds temporal fields (tenant_id, version, valid_from, etc.)
        as proper Pydantic model fields based on the temporal strategy and
        configuration flags.

        The injected fields can then be accessed via dot notation without
        AttributeError (e.g., model.tenant_id, model.version).
        """
        super().__init_subclass__(**kwargs)

        # Skip injection for the base PydanticModel class itself
        if cls.__name__ == "PydanticModel":
            return

        # Get temporal fields to inject based on strategy and config
        try:
            temporal_fields = cls.get_temporal_fields()
        except Exception:
            # If get_temporal_fields() fails (e.g., during initial class creation),
            # skip field injection. This can happen if the temporal registry
            # isn't fully initialized yet.
            return

        # Track if we modified any fields
        fields_modified = False

        # Inject each temporal field as a proper Pydantic field
        for field_name, (field_type, default_value) in temporal_fields.items():
            # Skip if field already exists (user-defined takes precedence)
            if hasattr(cls, field_name) and field_name in cls.model_fields:
                continue

            # Convert SQL defaults to Python defaults
            if default_value == "NOW()":
                # For datetime fields with SQL NOW() default
                def now_factory():
                    return datetime.now(timezone.utc)

                default_factory = now_factory
                default = None
            elif default_value == "gen_random_uuid()":
                # For UUID fields with SQL gen_random_uuid() default
                default_factory = uuid4
                default = None
            elif callable(default_value):
                # Already a callable, use as factory
                default_factory = default_value
                default = None
            elif default_value is None:
                # Explicit None default
                default_factory = None
                default = None
            else:
                # Static default value (e.g., version=1)
                default_factory = None
                default = default_value

            # Create FieldInfo for the temporal field
            # Note: FieldInfo doesn't allow both default and default_factory
            if default_factory is not None:
                field_info = FieldInfo(
                    annotation=field_type,
                    default_factory=default_factory,
                    description=f"Temporal field injected by {cls.__temporal_strategy__} strategy",
                )
            else:
                field_info = FieldInfo(
                    annotation=field_type,
                    default=default,
                    description=f"Temporal field injected by {cls.__temporal_strategy__} strategy",
                )

            # Add to model_fields
            cls.model_fields[field_name] = field_info

            # Add to __annotations__ for proper type hints
            if not hasattr(cls, "__annotations__"):
                cls.__annotations__ = {}
            cls.__annotations__[field_name] = field_type

            # Set the field as a class attribute for Pydantic to recognize it
            setattr(cls, field_name, field_info)

            fields_modified = True

        # Rebuild the model if we modified any fields
        # This ensures Pydantic's internal structures are updated
        if fields_modified:
            try:
                cls.model_rebuild()
            except Exception:
                # If model_rebuild fails (older Pydantic versions), that's OK
                # The fields are still injected and will work
                pass

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

    # ==================== Temporal Configuration ====================

    @classmethod
    def get_temporal_strategy(cls) -> TemporalStrategyType:
        """
        Get temporal strategy enum.

        Returns:
            TemporalStrategyType enum value
        """
        return TemporalStrategyType(cls.__temporal_strategy__)

    @classmethod
    def get_temporal_fields(cls) -> dict[str, tuple[type, Any]]:
        """
        Get temporal fields to inject based on strategy and features.

        This method is called by PydanticSchemaIntrospector to automatically
        add temporal fields to the table schema.

        Returns:
            Dict mapping field_name → (type, default_value)

        Example:
            >>> Product.__temporal_strategy__ = "scd2"
            >>> Product.__soft_delete__ = True
            >>> Product.get_temporal_fields()
            {
                'tenant_id': (UUID, None),
                'valid_from': (datetime, 'NOW()'),
                'valid_to': (Optional[datetime], None),
                'version': (int, 1),
                'deleted_at': (Optional[datetime], None),
                'deleted_by': (Optional[UUID], None),
            }
        """
        from ..temporal.registry import get_strategy

        # Create QueryBuilder for database-agnostic SQL generation
        # TODO: Auto-detect database type and select appropriate QueryBuilder
        query_builder = PostgresQueryBuilder()

        # Get strategy instance
        strategy = get_strategy(
            strategy_type=cls.get_temporal_strategy(),
            model_class=cls,
            query_builder=query_builder,
            soft_delete=cls.__soft_delete__,
            multi_tenant=cls.__multi_tenant__,
            tenant_field=cls.__tenant_field__,
        )

        return strategy.get_temporal_fields()

    @classmethod
    def get_temporal_indexes(cls) -> list[dict[str, Any]]:
        """
        Get index definitions for temporal fields.

        Returns:
            List of index definition dicts

        Example:
            >>> Product.get_temporal_indexes()
            [
                {
                    'name': 'idx_products_tenant_id',
                    'table_name': 'products',
                    'columns': ['tenant_id'],
                    'type': 'btree',
                },
                ...
            ]
        """
        from ..temporal.registry import get_strategy

        # Create QueryBuilder for database-agnostic SQL generation
        query_builder = PostgresQueryBuilder()

        strategy = get_strategy(
            strategy_type=cls.get_temporal_strategy(),
            model_class=cls,
            query_builder=query_builder,
            soft_delete=cls.__soft_delete__,
            multi_tenant=cls.__multi_tenant__,
            tenant_field=cls.__tenant_field__,
        )

        return strategy.get_temporal_indexes(
            table_name=cls.table_name(),
            schema=cls.__schema__,
        )

    @classmethod
    def get_auxiliary_tables(cls) -> list[dict[str, Any]]:
        """
        Get auxiliary table definitions (e.g., audit tables).

        Returns:
            List of auxiliary table definitions

        Example:
            >>> Order.__temporal_strategy__ = "copy_on_change"
            >>> tables = Order.get_auxiliary_tables()
            >>> tables[0]['name']
            'orders_audit'
        """
        from ..temporal.registry import get_strategy

        # Create QueryBuilder for database-agnostic SQL generation
        query_builder = PostgresQueryBuilder()

        strategy = get_strategy(
            strategy_type=cls.get_temporal_strategy(),
            model_class=cls,
            query_builder=query_builder,
            soft_delete=cls.__soft_delete__,
            multi_tenant=cls.__multi_tenant__,
            tenant_field=cls.__tenant_field__,
        )

        return strategy.get_auxiliary_tables(
            table_name=cls.table_name(),
            schema=cls.__schema__,
        )

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
                tenant_id UUID NOT NULL,
                deleted_at TIMESTAMP WITH TIME ZONE,
                deleted_by UUID,
                email VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                age INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON public.users(tenant_id);
            ...
        """
        # Import here to avoid circular dependency
        from ..db.schema_sync.postgres import PostgresMigrationGenerator
        from .introspector import PydanticSchemaIntrospector

        # Extract table definition from Pydantic model
        introspector = PydanticSchemaIntrospector()
        table_def = introspector.extract_table_definition(cls)

        # Generate SQL using existing migration generator
        generator = PostgresMigrationGenerator()
        create_table_sql = generator.generate_create_table(table_def)

        # Generate index SQL
        index_sqls = [
            generator.generate_create_index(cls.__schema__, index) for index in table_def.indexes
        ]

        # Combine table + indexes
        all_sql = [create_table_sql] + index_sqls
        return "\n".join(all_sql)

    @classmethod
    def get_auxiliary_tables_sql(cls) -> list[str]:
        """
        Generate CREATE TABLE SQL for all auxiliary tables.

        Auxiliary tables are additional tables created by temporal strategies,
        such as audit tables for copy_on_change strategy.

        Called by SchemaManager to auto-create auxiliary tables during sync.

        Returns:
            List of SQL statements (one per auxiliary table + indexes)

        Example:
            >>> # For copy_on_change strategy
            >>> sqls = Product.get_auxiliary_tables_sql()
            >>> print(sqls[0])
            CREATE TABLE IF NOT EXISTS public.products_audit (
                audit_id UUID PRIMARY KEY,
                record_id UUID NOT NULL,
                field_name VARCHAR(255) NOT NULL,
                old_value JSONB,
                new_value JSONB,
                ...
            );
        """
        from ..db.schema_sync.models import ColumnDefinition, IndexDefinition, TableDefinition
        from ..db.schema_sync.postgres import PostgresMigrationGenerator

        aux_tables = cls.get_auxiliary_tables()
        if not aux_tables:
            return []

        generator = PostgresMigrationGenerator()
        sql_statements = []

        for aux_table_def in aux_tables:
            # Convert to TableDefinition
            table_def = TableDefinition(
                name=aux_table_def["name"],
                schema=aux_table_def.get("schema", cls.__schema__),
                columns=[ColumnDefinition(**col_dict) for col_dict in aux_table_def["columns"]],
                indexes=[
                    IndexDefinition(**idx_dict) for idx_dict in aux_table_def.get("indexes", [])
                ],
            )

            # Generate CREATE TABLE
            create_sql = generator.generate_create_table(table_def)
            sql_statements.append(create_sql)

            # Generate indexes
            for index in table_def.indexes:
                index_sql = generator.generate_create_index(table_def.schema, index)
                sql_statements.append(index_sql)

        return sql_statements

    @classmethod
    def get_table_name(cls) -> str:
        """Alias for table_name() for SchemaManager compatibility."""
        return cls.table_name()

    # ==================== Instance Methods ====================

    def update_timestamp(self) -> None:
        """Update the updated_at field to current UTC time."""
        self.updated_at = datetime.now(timezone.utc)

    def model_dump_for_db(self, exclude_none: bool = False) -> dict[str, Any]:
        """
        Dump model to dict for database operations.

        Args:
            exclude_none: Exclude None values

        Returns:
            Dict suitable for database INSERT/UPDATE
        """
        return self.model_dump(exclude_none=exclude_none, mode="python")
