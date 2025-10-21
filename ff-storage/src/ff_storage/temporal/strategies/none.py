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

        # Build INSERT query
        table_name = self._get_table_name()
        columns = list(data.keys())
        placeholders = [f"${i+1}" for i in range(len(columns))]

        query = f"""
            INSERT INTO {table_name} ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            RETURNING *
        """

        # Execute
        async with db_pool.acquire() as conn:
            # Serialize JSONB fields to JSON strings for database insertion
            serialized_data = self._serialize_jsonb_fields(data)
            row = await conn.fetchrow(query, *serialized_data.values())

        return self._row_to_model(row)

    async def update(
        self,
        id: UUID,
        data: Dict[str, Any],
        db_pool,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> T:
        """
        Update record with direct UPDATE.

        Sets:
        - updated_at to NOW()
        """
        # Auto-set updated_at
        data["updated_at"] = datetime.now(timezone.utc)

        # Build WHERE clause
        where_parts = ["id = $1"]
        where_values = [id]

        if self.multi_tenant:
            if not tenant_id:
                raise ValueError("tenant_id required for multi-tenant model")
            where_parts.append(f"{self.tenant_field} = ${len(where_values) + 1}")
            where_values.append(tenant_id)

        if self.soft_delete:
            where_parts.append("deleted_at IS NULL")

        # Build SET clause
        set_parts = []
        set_values = []
        for key, value in data.items():
            set_values.append(value)
            set_parts.append(f"{key} = ${len(where_values) + len(set_values)}")

        table_name = self._get_table_name()
        query = f"""
            UPDATE {table_name}
            SET {', '.join(set_parts)}
            WHERE {' AND '.join(where_parts)}
            RETURNING *
        """

        # Execute
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, *where_values, *set_values)

        if not row:
            raise ValueError(f"Record not found: {id}")

        return self._row_to_model(row)

    async def delete(
        self,
        id: UUID,
        db_pool,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> bool:
        """
        Delete record.

        If soft_delete enabled: Sets deleted_at, deleted_by
        Otherwise: Hard DELETE
        """
        table_name = self._get_table_name()

        # Build WHERE clause
        where_parts = ["id = $1"]
        where_values = [id]

        if self.multi_tenant:
            if not tenant_id:
                raise ValueError("tenant_id required for multi-tenant model")
            where_parts.append(f"{self.tenant_field} = ${len(where_values) + 1}")
            where_values.append(tenant_id)

        if self.soft_delete:
            # Soft delete
            query = f"""
                UPDATE {table_name}
                SET deleted_at = ${ len(where_values) + 1},
                    deleted_by = ${ len(where_values) + 2}
                WHERE {' AND '.join(where_parts)} AND deleted_at IS NULL
                RETURNING id
            """
            values = where_values + [datetime.now(timezone.utc), user_id]
        else:
            # Hard delete
            query = f"""
                DELETE FROM {table_name}
                WHERE {' AND '.join(where_parts)}
                RETURNING id
            """
            values = where_values

        # Execute
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)

        return row is not None

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

        # Build WHERE clause
        where_parts = ["id = $1"]
        where_values = [id]

        if self.multi_tenant:
            if not tenant_id:
                raise ValueError("tenant_id required for multi-tenant model")
            where_parts.append(f"{self.tenant_field} = ${len(where_values) + 1}")
            where_values.append(tenant_id)

        if self.soft_delete and not include_deleted:
            where_parts.append("deleted_at IS NULL")

        query = f"""
            SELECT * FROM {table_name}
            WHERE {' AND '.join(where_parts)}
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
        filters = filters or {}

        # Build WHERE clause
        where_parts = []
        where_values = []

        # Multi-tenant filter
        if self.multi_tenant:
            if not tenant_id:
                raise ValueError("tenant_id required for multi-tenant model")
            where_parts.append(f"{self.tenant_field} = ${len(where_values) + 1}")
            where_values.append(tenant_id)

        # Soft delete filter
        if self.soft_delete and not include_deleted:
            where_parts.append("deleted_at IS NULL")

        # User filters
        for key, value in filters.items():
            where_parts.append(f"{key} = ${len(where_values) + 1}")
            where_values.append(value)

        # Build query
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        query = f"""
            SELECT * FROM {table_name}
            {where_clause}
            ORDER BY created_at DESC
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
        tenant_id: Optional[UUID] = None,
    ) -> Optional[T]:
        """
        Restore a soft-deleted record.

        Only available if soft_delete is enabled.
        """
        if not self.soft_delete:
            raise ValueError("restore() only available with soft_delete enabled")

        table_name = self._get_table_name()

        # Build WHERE clause
        where_parts = ["id = $1"]
        where_values = [id]

        if self.multi_tenant:
            if not tenant_id:
                raise ValueError("tenant_id required for multi-tenant model")
            where_parts.append(f"{self.tenant_field} = ${len(where_values) + 1}")
            where_values.append(tenant_id)

        query = f"""
            UPDATE {table_name}
            SET deleted_at = NULL,
                deleted_by = NULL,
                updated_at = ${len(where_values) + 1}
            WHERE {' AND '.join(where_parts)} AND deleted_at IS NOT NULL
            RETURNING *
        """

        # Execute
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, *where_values, datetime.now(timezone.utc))

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
        if hasattr(self.model_class, "model_validate"):
            # Pydantic v2
            return self.model_class.model_validate(dict(row))
        elif hasattr(self.model_class, "from_orm"):
            # Pydantic v1
            return self.model_class.from_orm(row)
        else:
            # Dataclass or other
            return self.model_class(**dict(row))
