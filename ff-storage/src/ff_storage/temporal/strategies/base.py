"""
Abstract base class for temporal strategies.

Defines the interface that all temporal strategies must implement.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar
from uuid import UUID

T = TypeVar("T")


class TemporalStrategy(ABC, Generic[T]):
    """
    Abstract base for temporal strategies.

    Each strategy implements a different pattern for tracking changes over time.
    """

    def __init__(
        self,
        model_class: type,
        query_builder,
        soft_delete: bool = True,
        multi_tenant: bool = True,
        tenant_field: str = "tenant_id",
    ):
        """
        Initialize strategy.

        Args:
            model_class: Model class this strategy operates on
            query_builder: QueryBuilder instance for database-specific SQL generation
            soft_delete: Enable soft delete (adds deleted_at, deleted_by)
            multi_tenant: Enable multi-tenancy (adds tenant_id)
            tenant_field: Name of tenant field
        """
        self.model_class = model_class
        self.query_builder = query_builder
        self.soft_delete = soft_delete
        self.multi_tenant = multi_tenant
        self.tenant_field = tenant_field

    # ==================== Schema Generation ====================

    @abstractmethod
    def get_temporal_fields(self) -> Dict[str, tuple[type, Any]]:
        """
        Return temporal fields to add to main table.

        Returns:
            Dict mapping field_name → (type, default_value)

        Example:
            {
                "valid_from": (datetime, "NOW()"),
                "valid_to": (Optional[datetime], None),
                "version": (int, 1),
            }
        """
        pass

    @abstractmethod
    def get_temporal_indexes(self, table_name: str, schema: str = "public") -> List[dict]:
        """
        Return index definitions for temporal fields.

        Args:
            table_name: Name of the table
            schema: Database schema

        Returns:
            List of index definition dicts

        Example:
            [
                {
                    "name": "idx_products_valid_period",
                    "table_name": "products",
                    "columns": ["valid_from", "valid_to"],
                    "index_type": "btree",
                },
            ]
        """
        pass

    @abstractmethod
    def get_auxiliary_tables(self, table_name: str, schema: str = "public") -> List[dict]:
        """
        Return auxiliary table definitions (e.g., audit tables).

        Args:
            table_name: Name of the main table
            schema: Database schema

        Returns:
            List of table definition dicts (each with columns, indexes)

        Example:
            [
                {
                    "name": "products_audit",
                    "schema": "public",
                    "columns": [...],
                    "indexes": [...],
                },
            ]
        """
        pass

    # ==================== CRUD Operations ====================

    @abstractmethod
    async def create(
        self,
        data: Dict[str, Any],
        db_pool,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> T:
        """
        Create operation with temporal logic.

        Args:
            data: Record data (dict)
            db_pool: Database connection pool
            tenant_id: Tenant context (for multi-tenant)
            user_id: User performing the action (for audit trail)

        Returns:
            Created record (model instance)
        """
        pass

    @abstractmethod
    async def update(
        self,
        id: UUID,
        data: Dict[str, Any],
        db_pool,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> T:
        """
        Update operation with temporal logic.

        Args:
            id: Record ID
            data: Updated data (dict)
            db_pool: Database connection pool
            tenant_id: Tenant context
            user_id: User performing the action

        Returns:
            Updated record (model instance)
        """
        pass

    @abstractmethod
    async def delete(
        self,
        id: UUID,
        db_pool,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> bool:
        """
        Delete operation with temporal logic.

        Args:
            id: Record ID
            db_pool: Database connection pool
            tenant_id: Tenant context
            user_id: User performing the action

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def get(
        self,
        id: UUID,
        db_pool,
        tenant_id: Optional[UUID] = None,
        **kwargs,
    ) -> Optional[T]:
        """
        Get operation with temporal filtering.

        Args:
            id: Record ID
            db_pool: Database connection pool
            tenant_id: Tenant context
            **kwargs: Strategy-specific options (e.g., as_of, include_deleted)

        Returns:
            Record (model instance) or None if not found
        """
        pass

    @abstractmethod
    async def list(
        self,
        filters: Optional[Dict[str, Any]],
        db_pool,
        tenant_id: Optional[UUID] = None,
        limit: int = 100,
        offset: int = 0,
        **kwargs,
    ) -> List[T]:
        """
        List operation with temporal filtering.

        Args:
            filters: Field filters (dict)
            db_pool: Database connection pool
            tenant_id: Tenant context
            limit: Max records to return
            offset: Pagination offset
            **kwargs: Strategy-specific options (e.g., include_deleted, as_of)

        Returns:
            List of records (model instances)
        """
        pass

    # ==================== Helper Methods ====================

    def _get_base_fields(self) -> Dict[str, tuple[type, Any]]:
        """
        Get base fields common to all strategies.

        Returns:
            Dict of base fields (id, created_at, updated_at, etc.)
        """
        from uuid import UUID

        fields = {}

        # Multi-tenant
        if self.multi_tenant:
            fields[self.tenant_field] = (UUID, None)

        # Soft delete
        if self.soft_delete:
            fields["deleted_at"] = (Optional[datetime], None)
            fields["deleted_by"] = (Optional[UUID], None)

        return fields

    def _get_base_indexes(self, table_name: str) -> List[dict]:
        """
        Get base indexes common to all strategies.

        Args:
            table_name: Name of the table

        Returns:
            List of index definitions
        """
        indexes = []

        # Multi-tenant index
        if self.multi_tenant:
            indexes.append(
                {
                    "name": f"idx_{table_name}_{self.tenant_field}",
                    "table_name": table_name,
                    "columns": [self.tenant_field],
                    "index_type": "btree",
                }
            )

            # Composite index: tenant + created_at (common query pattern)
            indexes.append(
                {
                    "name": f"idx_{table_name}_{self.tenant_field}_created",
                    "table_name": table_name,
                    "columns": [self.tenant_field, "created_at"],
                    "where_clause": "deleted_at IS NULL" if self.soft_delete else None,
                    "index_type": "btree",
                }
            )

        # Soft delete partial index (active records only)
        if self.soft_delete:
            indexes.append(
                {
                    "name": f"idx_{table_name}_not_deleted",
                    "table_name": table_name,
                    "columns": ["deleted_at"],
                    "where_clause": "deleted_at IS NULL",
                    "index_type": "btree",
                }
            )

        return indexes

    def _get_metadata_fields(self) -> set[str]:
        """
        Get set of metadata/system fields that should be excluded from user updates.

        These fields are managed by the system and should not be overwritten
        when applying user-provided data during updates.

        Returns:
            Set of field names that are system-managed

        Example:
            >>> metadata = strategy._get_metadata_fields()
            >>> metadata
            {'id', 'created_at', 'updated_at', 'created_by', 'deleted_at', 'deleted_by', 'tenant_id'}
        """
        metadata = {
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "deleted_at",
            "deleted_by",
        }

        # Add tenant_field if multi-tenant
        if self.multi_tenant:
            metadata.add(self.tenant_field)

        return metadata

    def _validate_and_build_filter_clauses(
        self, filters: Dict[str, Any], base_param_count: int = 0
    ) -> tuple[List[str], List[Any]]:
        """
        Validate filter keys and build safe WHERE clause components.

        This method uses the QueryBuilder to generate database-specific WHERE clauses
        with proper identifier quoting and parameter placeholders.

        Args:
            filters: Dictionary of field_name: value filters
            base_param_count: Number of parameters already in the query (for $N numbering)

        Returns:
            Tuple of (where_clauses list, parameter_values list)

        Example:
            >>> clauses, values = self._validate_and_build_filter_clauses(
            ...     {"status": "active", "price": 100}, base_param_count=2
            ... )
            >>> clauses
            ['"status" = $3', '"price" = $4']
            >>> values
            ['active', 100]
        """
        if not filters:
            return [], []

        # Use QueryBuilder to generate WHERE clause
        where_clause_str, where_values = self.query_builder.build_where_clause(
            filters, base_param_count=base_param_count, operator="AND"
        )

        # Split into individual clauses for compatibility with existing code
        # that expects a list of clause strings
        where_clauses = where_clause_str.split(" AND ")

        return where_clauses, where_values

    def get_current_version_filters(self) -> List[str]:
        """
        Get SQL filter conditions for querying current (non-historical) records.

        This is used to prevent data leakage where historical or deleted
        records are inadvertently returned in queries.

        Uses QueryBuilder to properly quote identifiers, preventing SQL errors
        when field names are reserved keywords.

        Returns:
            List of SQL WHERE conditions (without the WHERE keyword)

        Examples:
            For SCD2: ["valid_to IS NULL", "deleted_at IS NULL"]
            For soft delete: ["deleted_at IS NULL"]
            For none: []
        """
        filters = []

        # Soft delete filter (for active records only)
        # Use QueryBuilder to quote identifier in case field name is a reserved keyword
        if self.soft_delete:
            quoted_deleted_at = self.query_builder.quote_identifier("deleted_at")
            filters.append(f"{quoted_deleted_at} IS NULL")

        return filters

    def _serialize_jsonb_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Serialize JSONB fields to JSON strings for database insertion.

        Identifies which fields are JSONB columns from the Pydantic model's
        field types and serializes Python dicts/lists to JSON strings.

        This is necessary because asyncpg may not automatically handle Python
        dicts/lists for JSONB columns in all configurations. Explicit JSON
        serialization ensures compatibility across different PostgreSQL drivers.

        Args:
            data: Dictionary of field values

        Returns:
            Dictionary with JSONB fields serialized to JSON strings

        Example:
            >>> data = {"name": "Product", "metadata": {"tags": ["new"]}}
            >>> serialized = self._serialize_jsonb_fields(data)
            >>> serialized["metadata"]
            '{"tags": ["new"]}'
        """
        import json

        # Only serialize if we have a Pydantic model with field definitions
        if not hasattr(self.model_class, "model_fields"):
            return data  # Not a Pydantic model, return as-is

        # Import here to avoid circular dependency
        from ...db.schema_sync.models import ColumnType
        from ...pydantic_support.type_mapping import map_pydantic_type_to_column_type

        serialized_data = data.copy()

        for field_name, field_value in data.items():
            # Skip fields not in model definition (e.g., temporal fields)
            if field_name not in self.model_class.model_fields:
                continue

            field_info = self.model_class.model_fields[field_name]
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

    def _deserialize_jsonb_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deserialize JSONB fields from JSON strings to Python objects.

        This is the reverse of _serialize_jsonb_fields. When reading from
        the database, JSONB columns may be returned as JSON strings that need
        to be deserialized back to Python dicts/lists before passing to Pydantic.

        Args:
            data: Dictionary of field values from database

        Returns:
            Dictionary with JSONB fields deserialized to Python objects

        Example:
            >>> data = {"name": "Product", "metadata": '{"tags": ["new"]}'}
            >>> deserialized = self._deserialize_jsonb_fields(data)
            >>> deserialized["metadata"]
            {"tags": ["new"]}
        """
        import json

        # Only deserialize if we have a Pydantic model with field definitions
        if not hasattr(self.model_class, "model_fields"):
            return data  # Not a Pydantic model, return as-is

        # Import here to avoid circular dependency
        from ...db.schema_sync.models import ColumnType
        from ...pydantic_support.type_mapping import map_pydantic_type_to_column_type

        deserialized_data = data.copy()

        for field_name, field_value in data.items():
            # Skip fields not in model definition (e.g., temporal fields)
            if field_name not in self.model_class.model_fields:
                continue

            field_info = self.model_class.model_fields[field_name]
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
