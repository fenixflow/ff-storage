"""
None strategy - Standard CRUD with basic timestamps.

No temporal tracking beyond created_at/updated_at.
Supports soft delete and multi-tenant as cross-cutting features.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from ..enums import TemporalStrategyType
from ..registry import register_strategy
from .base import T, TemporalStrategy


@register_strategy(TemporalStrategyType.NONE)
class NoneStrategy(TemporalStrategy[T]):
    """
    Standard CRUD strategy with no temporal tracking.

    Features:
    - Direct INSERT/UPDATE/DELETE
    - Auto-sets created_at, updated_at, created_by
    - Supports soft delete (if enabled)
    - Supports multi-tenant filtering (if enabled)
    """

    def get_temporal_fields(self) -> Dict[str, tuple[type, Any]]:
        """No additional temporal fields beyond base (soft delete, multi-tenant)."""
        return self._get_base_fields()

    def get_temporal_indexes(self, table_name: str, schema: str = "public") -> List[dict]:
        """Return base indexes (tenant, soft delete)."""
        return self._get_base_indexes(table_name)

    def get_auxiliary_tables(self, table_name: str, schema: str = "public") -> List[dict]:
        """No auxiliary tables for none strategy."""
        return []

    async def create(
        self,
        data: Dict[str, Any],
        db_pool,
        adapter,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> T:
        """
        Create record with standard INSERT.

        Sets:
        - id (if not provided)
        - created_at, updated_at
        - created_by (if user_id provided)
        - tenant_id (if multi_tenant enabled)
        - deleted_at, deleted_by = NULL (if soft_delete enabled)
        """
        # Ensure ID
        if "id" not in data:
            data["id"] = uuid4()

        # Set timestamps
        now = datetime.now(timezone.utc)
        data["created_at"] = now
        data["updated_at"] = now

        # Set created_by
        if user_id:
            data["created_by"] = user_id

        # Set tenant_id
        if self.multi_tenant:
            if not tenant_id:
                raise ValueError("tenant_id required for multi-tenant model")
            data[self.tenant_field] = tenant_id

        # Initialize soft delete fields
        if self.soft_delete:
            data["deleted_at"] = None
            data["deleted_by"] = None

        # Build INSERT query using QueryBuilder
        table_name = self._get_table_name()
        serialized_data = self._serialize_jsonb_fields(data)
        query, values = self.query_builder.build_insert(table_name, serialized_data)

        # Execute using adapter
        row = await adapter.execute_with_returning(db_pool, query, values, table_name)

        return self._row_to_model(row)

    async def update(
        self,
        id: UUID,
        data: Dict[str, Any],
        db_pool,
        adapter,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> T:
        """
        Update record with direct UPDATE.

        Sets:
        - updated_at to NOW()
        - updated_by if user_id provided
        """
        # Auto-set updated_at
        data["updated_at"] = datetime.now(timezone.utc)

        # Track who made the update
        if user_id:
            data["updated_by"] = user_id

        # Build WHERE clause with proper quoting
        where_parts = [f"{self.query_builder.quote_identifier('id')} = $1"]
        where_values = [id]

        if self.multi_tenant:
            if not tenant_id:
                raise ValueError("tenant_id required for multi-tenant model")
            tenant_field_quoted = self.query_builder.quote_identifier(self.tenant_field)
            where_parts.append(f"{tenant_field_quoted} = ${len(where_values) + 1}")
            where_values.append(tenant_id)

        if self.soft_delete:
            deleted_at_quoted = self.query_builder.quote_identifier("deleted_at")
            where_parts.append(f"{deleted_at_quoted} IS NULL")

        # Build SET clause using QueryBuilder
        table_name = self._get_table_name()
        quoted_table = self.query_builder.quote_identifier(table_name)

        # Build SET clause parts
        set_parts = []
        set_values = []
        base_param = len(where_values)

        for key, value in data.items():
            set_values.append(value)
            quoted_key = self.query_builder.quote_identifier(key)
            param_num = base_param + len(set_values)
            set_parts.append(f"{quoted_key} = ${param_num}")

        set_clause = ", ".join(set_parts)

        query = f"""
            UPDATE {quoted_table}
            SET {set_clause}
            WHERE {" AND ".join(where_parts)}
            RETURNING *
        """

        # Execute using adapter
        all_values = where_values + set_values
        row = await adapter.execute_with_returning(db_pool, query, all_values, table_name)

        if not row:
            raise ValueError(f"Record not found: {id}")

        return self._row_to_model(row)

    async def delete(
        self,
        id: UUID,
        db_pool,
        adapter,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> bool:
        """
        Delete record.

        If soft_delete enabled: Sets deleted_at, deleted_by
        Otherwise: Hard DELETE
        """
        table_name = self._get_table_name()
        quoted_table = self.query_builder.quote_identifier(table_name)

        # Build WHERE clause with proper quoting
        where_parts = [f"{self.query_builder.quote_identifier('id')} = $1"]
        where_values = [id]

        if self.multi_tenant:
            if not tenant_id:
                raise ValueError("tenant_id required for multi-tenant model")
            tenant_field_quoted = self.query_builder.quote_identifier(self.tenant_field)
            where_parts.append(f"{tenant_field_quoted} = ${len(where_values) + 1}")
            where_values.append(tenant_id)

        if self.soft_delete:
            # Soft delete
            deleted_at_quoted = self.query_builder.quote_identifier("deleted_at")
            deleted_by_quoted = self.query_builder.quote_identifier("deleted_by")
            query = f"""
                UPDATE {quoted_table}
                SET {deleted_at_quoted} = ${len(where_values) + 1},
                    {deleted_by_quoted} = ${len(where_values) + 2}
                WHERE {" AND ".join(where_parts)} AND {deleted_at_quoted} IS NULL
                RETURNING {self.query_builder.quote_identifier("id")}
            """
            values = where_values + [datetime.now(timezone.utc), user_id]
        else:
            # Hard delete
            query = f"""
                DELETE FROM {quoted_table}
                WHERE {" AND ".join(where_parts)}
                RETURNING {self.query_builder.quote_identifier("id")}
            """
            values = where_values

        # Execute using adapter
        row = await adapter.execute_with_returning(db_pool, query, values, table_name)

        return row is not None

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
        Transfer ownership by directly updating tenant_id.

        For None strategy, this is a simple UPDATE operation.

        Args:
            id: Record ID
            new_tenant_id: New tenant to own this record
            current_tenant_id: Current tenant (for validation)
            user_id: User performing transfer (audit trail)

        Returns:
            Updated record with new tenant_id

        Raises:
            ValueError: If record not found or tenant_id unchanged
        """
        table_name = self._get_table_name()
        quoted_table = self.query_builder.quote_identifier(table_name)

        # Build WHERE clause with proper quoting
        where_parts = [f"{self.query_builder.quote_identifier('id')} = $1"]
        where_values = [id]

        # Optionally validate current tenant
        if current_tenant_id is not None:
            tenant_field_quoted = self.query_builder.quote_identifier(self.tenant_field)
            where_parts.append(f"{tenant_field_quoted} = ${len(where_values) + 1}")
            where_values.append(current_tenant_id)

        if self.soft_delete:
            deleted_at_quoted = self.query_builder.quote_identifier("deleted_at")
            where_parts.append(f"{deleted_at_quoted} IS NULL")

        # Get current record to validate tenant change
        select_query = f"""
            SELECT * FROM {quoted_table}
            WHERE {" AND ".join(where_parts)}
        """

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # 1. Get current record
                current_row = await conn.fetchrow(select_query, *where_values)

                if not current_row:
                    raise ValueError(f"Record not found: {id}")

                current_data = dict(current_row)
                current_tenant = current_data.get(self.tenant_field)

                # 2. Validate tenant actually changed (prevent no-op transfers)
                if current_tenant == new_tenant_id:
                    raise ValueError(
                        f"Cannot transfer to same tenant. Record {id} already belongs to {new_tenant_id}"
                    )

                # 3. UPDATE with new tenant_id
                tenant_field_quoted = self.query_builder.quote_identifier(self.tenant_field)
                updated_at_quoted = self.query_builder.quote_identifier("updated_at")
                updated_by_quoted = self.query_builder.quote_identifier("updated_by")

                update_query = f"""
                    UPDATE {quoted_table}
                    SET {tenant_field_quoted} = ${len(where_values) + 1},
                        {updated_at_quoted} = ${len(where_values) + 2},
                        {updated_by_quoted} = ${len(where_values) + 3}
                    WHERE {" AND ".join(where_parts)}
                    RETURNING *
                """

                now = datetime.now(timezone.utc)
                row = await conn.fetchrow(update_query, *where_values, new_tenant_id, now, user_id)

        if not row:
            raise ValueError(f"Failed to transfer ownership for record: {id}")

        return self._row_to_model(row)

    async def get(
        self,
        id: UUID,
        db_pool,
        tenant_id: Optional[UUID] = None,
        include_deleted: bool = False,
        **kwargs,
    ) -> Optional[T]:
        """
        Get record by ID.

        Args:
            include_deleted: If True, include soft-deleted records
        """
        table_name = self._get_table_name()
        quoted_table = self.query_builder.quote_identifier(table_name)

        # Build WHERE clause with proper quoting
        where_parts = [f"{self.query_builder.quote_identifier('id')} = $1"]
        where_values = [id]

        if self.multi_tenant:
            if not tenant_id:
                raise ValueError("tenant_id required for multi-tenant model")
            tenant_field_quoted = self.query_builder.quote_identifier(self.tenant_field)
            where_parts.append(f"{tenant_field_quoted} = ${len(where_values) + 1}")
            where_values.append(tenant_id)

        if self.soft_delete and not include_deleted:
            deleted_at_quoted = self.query_builder.quote_identifier("deleted_at")
            where_parts.append(f"{deleted_at_quoted} IS NULL")

        query = f"""
            SELECT * FROM {quoted_table}
            WHERE {" AND ".join(where_parts)}
        """

        # Execute
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, *where_values)

        if not row:
            return None

        return self._row_to_model(row)

    async def list(
        self,
        filters: Optional[Dict[str, Any]],
        db_pool,
        tenant_id: Optional[UUID] = None,
        limit: int = 100,
        offset: int = 0,
        include_deleted: bool = False,
        **kwargs,
    ) -> List[T]:
        """
        List records with filters.

        Args:
            filters: Field filters (key=value)
            include_deleted: If True, include soft-deleted records
        """
        table_name = self._get_table_name()
        quoted_table = self.query_builder.quote_identifier(table_name)
        filters = filters or {}

        # Multi-tenant filter: Add to filters if not already present
        # This allows callers to override with a list for cross-tenant reads
        if self.multi_tenant:
            if self.tenant_field not in filters:
                # Add default tenant_id if not already specified in filters
                if not tenant_id:
                    raise ValueError("tenant_id required for multi-tenant model")
                filters[self.tenant_field] = tenant_id
            # Tenant filtering will be handled by _validate_and_build_filter_clauses()
            # which supports both single values (=) and lists (IN)

        # Build WHERE clause with proper quoting
        where_parts = []
        where_values = []

        # Soft delete filter
        if self.soft_delete and not include_deleted:
            deleted_at_quoted = self.query_builder.quote_identifier("deleted_at")
            where_parts.append(f"{deleted_at_quoted} IS NULL")

        # User filters (with validation to prevent SQL injection)
        if filters:
            filter_clauses, filter_values = self._validate_and_build_filter_clauses(
                filters, base_param_count=len(where_values)
            )
            where_parts.extend(filter_clauses)
            where_values.extend(filter_values)

        # Build query
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        created_at_quoted = self.query_builder.quote_identifier("created_at")
        query = f"""
            SELECT * FROM {quoted_table}
            {where_clause}
            ORDER BY {created_at_quoted} DESC
            LIMIT ${len(where_values) + 1}
            OFFSET ${len(where_values) + 2}
        """

        # Execute
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *where_values, limit, offset)

        return [self._row_to_model(row) for row in rows]

    # ==================== Restore (Soft Delete) ====================

    async def restore(
        self,
        id: UUID,
        db_pool,
        adapter,
        tenant_id: Optional[UUID] = None,
    ) -> Optional[T]:
        """
        Restore a soft-deleted record.

        Only available if soft_delete is enabled.
        """
        if not self.soft_delete:
            raise ValueError("restore() only available with soft_delete enabled")

        table_name = self._get_table_name()
        quoted_table = self.query_builder.quote_identifier(table_name)

        # Build WHERE clause with proper quoting
        where_parts = [f"{self.query_builder.quote_identifier('id')} = $1"]
        where_values = [id]

        if self.multi_tenant:
            if not tenant_id:
                raise ValueError("tenant_id required for multi-tenant model")
            tenant_field_quoted = self.query_builder.quote_identifier(self.tenant_field)
            where_parts.append(f"{tenant_field_quoted} = ${len(where_values) + 1}")
            where_values.append(tenant_id)

        deleted_at_quoted = self.query_builder.quote_identifier("deleted_at")
        deleted_by_quoted = self.query_builder.quote_identifier("deleted_by")
        updated_at_quoted = self.query_builder.quote_identifier("updated_at")

        query = f"""
            UPDATE {quoted_table}
            SET {deleted_at_quoted} = NULL,
                {deleted_by_quoted} = NULL,
                {updated_at_quoted} = ${len(where_values) + 1}
            WHERE {" AND ".join(where_parts)} AND {deleted_at_quoted} IS NOT NULL
            RETURNING *
        """

        # Execute using adapter
        all_values = where_values + [datetime.now(timezone.utc)]
        row = await adapter.execute_with_returning(db_pool, query, all_values, table_name)

        if not row:
            return None

        return self._row_to_model(row)

    # ==================== Helper Methods ====================

    def _get_table_name(self) -> str:
        """
        Get fully-qualified table name from model class.

        Returns schema-qualified name (e.g., "ix_ds_v2.umr") to ensure queries
        work regardless of PostgreSQL search_path configuration.
        """
        # Get schema (default to "public" if not specified)
        schema = getattr(self.model_class, "__schema__", "public")

        # Get table name
        if hasattr(self.model_class, "table_name"):
            table = self.model_class.table_name()
        elif hasattr(self.model_class, "__table_name__"):
            table = self.model_class.__table_name__
        else:
            table = self.model_class.__name__.lower() + "s"

        # Return schema-qualified name
        return f"{schema}.{table}"

    def _row_to_model(self, row) -> T:
        """Convert database row to model instance."""
        # Deserialize JSONB fields from JSON strings back to Python objects
        row_dict = self._deserialize_jsonb_fields(dict(row))

        if hasattr(self.model_class, "model_validate"):
            # Pydantic v2
            return self.model_class.model_validate(row_dict)
        elif hasattr(self.model_class, "from_orm"):
            # Pydantic v1
            return self.model_class.from_orm(row_dict)
        else:
            # Dataclass or other
            return self.model_class(**row_dict)
