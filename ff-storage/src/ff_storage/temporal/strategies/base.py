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
        connection=None,
    ) -> T:
        """
        Create operation with temporal logic.

        Args:
            data: Record data (dict)
            db_pool: Database connection pool
            tenant_id: Tenant context (for multi-tenant)
            user_id: User performing the action (for audit trail)
            connection: Optional database connection for transaction support.
                       If provided, uses this connection instead of acquiring
                       from pool. Enables external transaction management.

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
        connection=None,
    ) -> T:
        """
        Update operation with temporal logic.

        Args:
            id: Record ID
            data: Updated data (dict)
            db_pool: Database connection pool
            tenant_id: Tenant context
            user_id: User performing the action
            connection: Optional database connection for transaction support.
                       If provided, uses this connection instead of acquiring
                       from pool. Enables external transaction management.

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
        connection=None,
    ) -> bool:
        """
        Delete operation with temporal logic.

        Args:
            id: Record ID
            db_pool: Database connection pool
            tenant_id: Tenant context
            user_id: User performing the action
            connection: Optional database connection for transaction support.
                       If provided, uses this connection instead of acquiring
                       from pool. Enables external transaction management.

        Returns:
            True if deleted, False if not found
        """
        pass

    async def transfer_ownership(
        self,
        id: UUID,
        new_tenant_id: UUID,
        db_pool,
        adapter,
        current_tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> T:
        """
        Transfer record ownership to a different tenant (optional).

        Not all strategies need to implement this - it's only required for
        superadmin operations that allow moving records between tenants.

        Default implementation raises NotImplementedError. Strategies that
        support this operation should override this method.

        Args:
            id: Record ID
            new_tenant_id: New tenant to own this record
            db_pool: Database connection pool
            adapter: Database adapter
            current_tenant_id: Current tenant context (for validation)
            user_id: User performing the transfer (for audit trail)

        Returns:
            Updated record (model instance) with new tenant_id

        Raises:
            NotImplementedError: If strategy doesn't support ownership transfer
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support transfer_ownership()"
        )

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

        Delegates to the shared utility in pydantic_support.jsonb_utils.

        Args:
            data: Dictionary of field values

        Returns:
            Dictionary with JSONB fields serialized to JSON strings
        """
        from ...pydantic_support.jsonb_utils import serialize_jsonb_fields

        return serialize_jsonb_fields(self.model_class, data)

    def _deserialize_jsonb_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deserialize JSONB fields from JSON strings to Python objects.

        Delegates to the shared utility in pydantic_support.jsonb_utils.

        Args:
            data: Dictionary of field values from database

        Returns:
            Dictionary with JSONB fields deserialized to Python objects
        """
        from ...pydantic_support.jsonb_utils import deserialize_jsonb_fields

        return deserialize_jsonb_fields(self.model_class, data)
