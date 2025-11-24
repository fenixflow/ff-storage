"""
Copy-on-Change strategy - Field-level audit trail.

Main table: Standard CRUD (like none strategy)
Audit table: {table}_audit with field-level change tracking

Benefits:
- Lightweight: Only changed fields are stored
- Concurrent: Field-level updates don't conflict
- Granular: See exactly which fields changed when
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from ...db.schema_sync.models import ColumnType
from ..enums import TemporalStrategyType
from ..models import AuditEntry
from ..registry import register_strategy
from .base import T, TemporalStrategy


@register_strategy(TemporalStrategyType.COPY_ON_CHANGE)
class CopyOnChangeStrategy(TemporalStrategy[T]):
    """
    Field-level audit trail strategy.

    Main table: Standard CRUD with timestamps
    Audit table: Field-level change history

    Each UPDATE creates N audit rows (N = number of changed fields).
    Grouped by transaction_id for multi-field updates.
    """

    def get_temporal_fields(self) -> Dict[str, tuple[type, Any]]:
        """No additional fields in main table beyond base."""
        return self._get_base_fields()

    def get_temporal_indexes(self, table_name: str, schema: str = "public") -> List[dict]:
        """Return base indexes."""
        return self._get_base_indexes(table_name)

    def get_auxiliary_tables(self, table_name: str, schema: str = "public") -> List[dict]:
        """
        Return audit table definition.

        Audit table tracks field-level changes:
        - One row per changed field
        - Groups multi-field updates by transaction_id
        """

        audit_table_name = f"{table_name}_audit"

        columns = [
            {
                "name": "audit_id",
                "column_type": ColumnType.UUID,
                "native_type": "UUID",
                "nullable": False,
                "is_primary_key": True,
                "default": "gen_random_uuid()",
            },
            {
                "name": "record_id",
                "column_type": ColumnType.UUID,
                "native_type": "UUID",
                "nullable": False,
            },
        ]

        # Add tenant_id to audit table if multi_tenant
        if self.multi_tenant:
            columns.append(
                {
                    "name": self.tenant_field,
                    "column_type": ColumnType.UUID,
                    "native_type": "UUID",
                    "nullable": False,
                }
            )

        # Field-level tracking columns
        columns.extend(
            [
                {
                    "name": "field_name",
                    "column_type": ColumnType.STRING,
                    "native_type": "VARCHAR(255)",
                    "max_length": 255,
                    "nullable": False,
                },
                {
                    "name": "old_value",
                    "column_type": ColumnType.JSONB,
                    "native_type": "JSONB",
                    "nullable": True,
                },
                {
                    "name": "new_value",
                    "column_type": ColumnType.JSONB,
                    "native_type": "JSONB",
                    "nullable": True,
                },
                {
                    "name": "operation",
                    "column_type": ColumnType.STRING,
                    "native_type": "VARCHAR(10)",
                    "max_length": 10,
                    "nullable": False,
                },
                {
                    "name": "changed_at",
                    "column_type": ColumnType.TIMESTAMPTZ,
                    "native_type": "TIMESTAMP WITH TIME ZONE",
                    "nullable": False,
                    "default": "NOW()",
                },
                {
                    "name": "changed_by",
                    "column_type": ColumnType.UUID,
                    "native_type": "UUID",
                    "nullable": True,
                },
                {
                    "name": "transaction_id",
                    "column_type": ColumnType.UUID,
                    "native_type": "UUID",
                    "nullable": True,
                },
                {
                    "name": "metadata",
                    "column_type": ColumnType.JSONB,
                    "native_type": "JSONB",
                    "nullable": True,
                },
            ]
        )

        # Indexes for audit table
        indexes = [
            {
                "name": f"idx_{audit_table_name}_record_field",
                "table_name": audit_table_name,
                "columns": ["record_id", "field_name"],
                "index_type": "btree",
            },
            {
                "name": f"idx_{audit_table_name}_changed_at",
                "table_name": audit_table_name,
                "columns": ["changed_at"],
                "index_type": "btree",
            },
        ]

        if self.multi_tenant:
            indexes.append(
                {
                    "name": f"idx_{audit_table_name}_{self.tenant_field}",
                    "table_name": audit_table_name,
                    "columns": [self.tenant_field],
                    "index_type": "btree",
                }
            )

        return [
            {
                "name": audit_table_name,
                "schema": schema,
                "columns": columns,
                "indexes": indexes,
            }
        ]

    async def create(
        self,
        data: Dict[str, Any],
        db_pool,
        adapter,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> T:
        """
        Create record with INSERT audit entries.

        Creates:
        1. Main table row
        2. Audit entries for each field (operation=INSERT)
        """
        # Ensure ID
        if "id" not in data:
            data["id"] = uuid4()

        record_id = data["id"]

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

        # Transaction ID for grouping audit entries
        transaction_id = uuid4()

        # Build INSERT query for main table using QueryBuilder
        table_name = self._get_table_name()
        audit_table_name = f"{table_name}_audit"

        serialized_data = self._serialize_jsonb_fields(data)
        main_insert, insert_values = self.query_builder.build_insert(table_name, serialized_data)

        # Build audit entries (one per field)
        audit_entries = []
        user_fields = self._get_user_fields(data)

        for field_name, new_value in user_fields.items():
            entry = {
                "audit_id": uuid4(),
                "record_id": record_id,
                "field_name": field_name,
                "old_value": None,  # NULL for INSERT
                "new_value": self._serialize_value(new_value),
                "operation": "INSERT",
                "changed_at": now,
                "changed_by": user_id,
                "transaction_id": transaction_id,
            }
            # Only add tenant_id if multi-tenant is enabled
            if self.multi_tenant:
                entry["tenant_id"] = tenant_id
            audit_entries.append(entry)

        # Execute in transaction
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # Insert main record
                row = await conn.fetchrow(main_insert, *insert_values)

                # Insert audit entries
                await self._insert_audit_entries(conn, audit_table_name, audit_entries)

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
        Update record with field-level audit entries and row-level locking.

        Process:
        1. SELECT current record FOR UPDATE (lock row)
        2. Compute field diff (which fields changed)
        3. UPDATE main table
        4. INSERT audit entries (one per changed field)

        Concurrency:
        Uses SELECT ... FOR UPDATE to prevent race conditions where concurrent
        updates might miss field changes. This holds an exclusive lock on the row
        during diff computation, reducing write concurrency but ensuring correctness.

        Trade-off: Acceptable for moderate update rates (<100/sec per row).
        For higher concurrency needs, consider database triggers or optimistic locking.
        """
        table_name = self._get_table_name()
        quoted_table = self.query_builder.quote_identifier(table_name)
        audit_table_name = f"{table_name}_audit"

        # Auto-set updated_at
        data["updated_at"] = datetime.now(timezone.utc)

        # Track who made the update
        if user_id:
            data["updated_by"] = user_id

        # Transaction ID for grouping
        transaction_id = uuid4()
        now = datetime.now(timezone.utc)

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

        # Execute in transaction
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # 1. Get current record with row-level lock
                select_query = f"""
                    SELECT * FROM {quoted_table}
                    WHERE {" AND ".join(where_parts)}
                    FOR UPDATE
                """
                current_row = await conn.fetchrow(select_query, *where_values)

                if not current_row:
                    raise ValueError(f"Record not found: {id}")

                # 2. Compute field diff
                current_data = dict(current_row)
                audit_entries = []

                for field_name, new_value in data.items():
                    old_value = current_data.get(field_name)

                    # Skip if no change
                    if old_value == new_value:
                        continue

                    # Create audit entry for this field
                    entry = {
                        "audit_id": uuid4(),
                        "record_id": id,
                        "field_name": field_name,
                        "old_value": self._serialize_value(old_value),
                        "new_value": self._serialize_value(new_value),
                        "operation": "UPDATE",
                        "changed_at": now,
                        "changed_by": user_id,
                        "transaction_id": transaction_id,
                    }
                    # Only add tenant_id if multi-tenant is enabled
                    if self.multi_tenant:
                        entry["tenant_id"] = tenant_id
                    audit_entries.append(entry)

                # 3. UPDATE main table using QueryBuilder
                # Build SET clause parts
                # Filter out metadata fields to prevent overwriting with None values
                metadata_fields = self._get_metadata_fields()

                set_parts = []
                set_values = []
                base_param = len(where_values)

                for key, value in data.items():
                    # Skip metadata fields that should be preserved from current record
                    if key in metadata_fields:
                        continue

                    set_values.append(value)
                    quoted_key = self.query_builder.quote_identifier(key)
                    param_num = base_param + len(set_values)
                    set_parts.append(f"{quoted_key} = ${param_num}")

                set_clause = ", ".join(set_parts)

                update_query = f"""
                    UPDATE {quoted_table}
                    SET {set_clause}
                    WHERE {" AND ".join(where_parts)}
                    RETURNING *
                """

                row = await conn.fetchrow(update_query, *where_values, *set_values)

                # 4. INSERT audit entries
                if audit_entries:
                    await self._insert_audit_entries(conn, audit_table_name, audit_entries)

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
        Delete record with DELETE audit entry.

        If soft_delete: Update main table, create audit entry for deleted_at
        Otherwise: Hard DELETE, create audit entry
        """
        table_name = self._get_table_name()
        quoted_table = self.query_builder.quote_identifier(table_name)
        audit_table_name = f"{table_name}_audit"
        now = datetime.now(timezone.utc)
        transaction_id = uuid4()

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
        id_quoted = self.query_builder.quote_identifier("id")

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # Get current record for audit
                select_query = f"""
                    SELECT * FROM {quoted_table}
                    WHERE {" AND ".join(where_parts)}
                """
                if self.soft_delete:
                    select_query += f" AND {deleted_at_quoted} IS NULL"

                current_row = await conn.fetchrow(select_query, *where_values)

                if not current_row:
                    return False

                if self.soft_delete:
                    # Soft delete
                    delete_query = f"""
                        UPDATE {quoted_table}
                        SET {deleted_at_quoted} = ${len(where_values) + 1},
                            {deleted_by_quoted} = ${len(where_values) + 2}
                        WHERE {" AND ".join(where_parts)} AND {deleted_at_quoted} IS NULL
                        RETURNING {id_quoted}
                    """
                    await conn.fetchrow(delete_query, *where_values, now, user_id)

                    # Audit entry for deleted_at field
                    entry = {
                        "audit_id": uuid4(),
                        "record_id": id,
                        "field_name": "deleted_at",
                        "old_value": None,
                        "new_value": self._serialize_value(now),
                        "operation": "DELETE",
                        "changed_at": now,
                        "changed_by": user_id,
                        "transaction_id": transaction_id,
                    }
                    # Only add tenant_id if multi-tenant is enabled
                    if self.multi_tenant:
                        entry["tenant_id"] = tenant_id
                    audit_entries = [entry]
                else:
                    # Hard delete
                    delete_query = f"""
                        DELETE FROM {quoted_table}
                        WHERE {" AND ".join(where_parts)}
                        RETURNING {id_quoted}
                    """
                    await conn.fetchrow(delete_query, *where_values)

                    # Audit entry for DELETE
                    user_fields = self._get_user_fields(dict(current_row))
                    audit_entries = []

                    for field_name, old_value in user_fields.items():
                        entry = {
                            "audit_id": uuid4(),
                            "record_id": id,
                            "field_name": field_name,
                            "old_value": self._serialize_value(old_value),
                            "new_value": None,
                            "operation": "DELETE",
                            "changed_at": now,
                            "changed_by": user_id,
                            "transaction_id": transaction_id,
                        }
                        # Only add tenant_id if multi-tenant is enabled
                        if self.multi_tenant:
                            entry["tenant_id"] = tenant_id
                        audit_entries.append(entry)

                # Insert audit entries
                await self._insert_audit_entries(conn, audit_table_name, audit_entries)

        return True

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
        Transfer ownership by updating tenant_id with audit trail.

        For CopyOnChange strategy, this creates audit entries tracking
        the tenant_id change.

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
        audit_table_name = self._get_audit_table_name()
        transaction_id = uuid4()
        now = datetime.now(timezone.utc)

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

                row = await conn.fetchrow(update_query, *where_values, new_tenant_id, now, user_id)

                # 4. Create audit entry for tenant_id change
                audit_entry = {
                    "audit_id": uuid4(),
                    "record_id": id,
                    "field_name": self.tenant_field,
                    "old_value": self._serialize_value(current_tenant),
                    "new_value": self._serialize_value(new_tenant_id),
                    "operation": "TRANSFER",
                    "changed_at": now,
                    "changed_by": user_id,
                    "transaction_id": transaction_id,
                }
                # Only add tenant_id if multi-tenant is enabled
                if self.multi_tenant:
                    audit_entry["tenant_id"] = new_tenant_id  # Audit under new tenant

                # Insert audit entry
                await self._insert_audit_entries(conn, audit_table_name, [audit_entry])

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
        """Get record by ID (same as none strategy)."""
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
        """List records (same as none strategy)."""
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

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        created_at_quoted = self.query_builder.quote_identifier("created_at")
        query = f"""
            SELECT * FROM {quoted_table}
            {where_clause}
            ORDER BY {created_at_quoted} DESC
            LIMIT ${len(where_values) + 1}
            OFFSET ${len(where_values) + 2}
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *where_values, limit, offset)

        return [self._row_to_model(row) for row in rows]

    # ==================== Audit Query Methods ====================

    async def get_audit_history(
        self,
        record_id: UUID,
        db_pool,
        tenant_id: Optional[UUID] = None,
    ) -> List[AuditEntry]:
        """
        Get full audit history for a record.

        Returns list of AuditEntry objects ordered by changed_at.
        """
        table_name = self._get_table_name()
        audit_table_name = f"{table_name}_audit"
        quoted_audit_table = self.query_builder.quote_identifier(audit_table_name)

        # Build WHERE clause with proper quoting
        record_id_quoted = self.query_builder.quote_identifier("record_id")
        where_parts = [f"{record_id_quoted} = $1"]
        where_values = [record_id]

        if self.multi_tenant:
            if not tenant_id:
                raise ValueError("tenant_id required for multi-tenant model")
            tenant_field_quoted = self.query_builder.quote_identifier(self.tenant_field)
            where_parts.append(f"{tenant_field_quoted} = ${len(where_values) + 1}")
            where_values.append(tenant_id)

        changed_at_quoted = self.query_builder.quote_identifier("changed_at")
        query = f"""
            SELECT * FROM {quoted_audit_table}
            WHERE {" AND ".join(where_parts)}
            ORDER BY {changed_at_quoted} ASC
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *where_values)

        return [AuditEntry(**dict(row)) for row in rows]

    async def get_field_history(
        self,
        record_id: UUID,
        field_name: str,
        db_pool,
        tenant_id: Optional[UUID] = None,
    ) -> List[AuditEntry]:
        """Get history of specific field."""
        table_name = self._get_table_name()
        audit_table_name = f"{table_name}_audit"
        quoted_audit_table = self.query_builder.quote_identifier(audit_table_name)

        # Build WHERE clause with proper quoting
        record_id_quoted = self.query_builder.quote_identifier("record_id")
        field_name_quoted = self.query_builder.quote_identifier("field_name")
        where_parts = [f"{record_id_quoted} = $1", f"{field_name_quoted} = $2"]
        where_values = [record_id, field_name]

        if self.multi_tenant:
            if not tenant_id:
                raise ValueError("tenant_id required for multi-tenant model")
            tenant_field_quoted = self.query_builder.quote_identifier(self.tenant_field)
            where_parts.append(f"{tenant_field_quoted} = ${len(where_values) + 1}")
            where_values.append(tenant_id)

        changed_at_quoted = self.query_builder.quote_identifier("changed_at")
        query = f"""
            SELECT * FROM {quoted_audit_table}
            WHERE {" AND ".join(where_parts)}
            ORDER BY {changed_at_quoted} ASC
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *where_values)

        return [AuditEntry(**dict(row)) for row in rows]

    # ==================== Helper Methods ====================

    async def _insert_audit_entries(
        self, conn, audit_table_name: str, entries: List[Dict[str, Any]]
    ):
        """Bulk insert audit entries with quoted identifiers."""
        if not entries:
            return

        # Get columns from first entry
        columns = list(entries[0].keys())

        # Build multi-row INSERT with quoted identifiers using QueryBuilder
        quoted_audit_table = self.query_builder.quote_identifier(audit_table_name)
        quoted_columns = ", ".join(self.query_builder.quote_identifier(col) for col in columns)
        values_clauses = []
        all_values = []

        for i, entry in enumerate(entries):
            placeholders = []
            for j, col in enumerate(columns):
                idx = i * len(columns) + j + 1
                placeholders.append(f"${idx}")

                # Serialize JSONB values to JSON strings for asyncpg
                value = entry[col]
                if col in ("old_value", "new_value") and value is not None:
                    # Convert to JSON string for JSONB column
                    value = json.dumps(value)

                all_values.append(value)

            values_clauses.append(f"({', '.join(placeholders)})")

        query = f"""
            INSERT INTO {quoted_audit_table} ({quoted_columns})
            VALUES {", ".join(values_clauses)}
        """

        await conn.execute(query, *all_values)

    def _get_user_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Filter out system fields, return only user-defined fields."""
        system_fields = {
            "id",
            "created_at",
            "updated_at",
            "created_by",
            self.tenant_field,
            "deleted_at",
            "deleted_by",
        }

        return {k: v for k, v in data.items() if k not in system_fields}

    def _serialize_value(self, value: Any) -> Any:
        """
        Serialize value for JSONB storage.

        Returns JSON-compatible Python values that asyncpg can serialize to JSONB.
        We don't pre-serialize to JSON strings - let asyncpg handle the encoding.
        """
        if value is None:
            return None

        from datetime import date
        from decimal import Decimal
        from enum import Enum

        # Convert to JSON-compatible Python types (asyncpg will handle JSON encoding)
        if isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, date):
            return value.isoformat()
        elif isinstance(value, UUID):
            return str(value)
        elif isinstance(value, Decimal):
            return str(value)  # Preserve exact precision as string
        elif isinstance(value, Enum):
            return value.value  # Return the underlying value
        elif isinstance(value, bytes):
            return value.hex()
        elif isinstance(value, (dict, list, str, int, float, bool)):
            return value  # Already JSON-compatible

        # For complex types, verify JSON compatibility
        try:
            json.dumps(value)
            return value
        except (TypeError, ValueError):
            # Fallback: convert to string for non-serializable types
            return str(value)

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
