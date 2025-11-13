"""
SCD2 (Slowly Changing Dimension Type 2) strategy.

Immutable version history with temporal validity.

Main table contains ALL versions with:
- valid_from, valid_to (temporal range)
- version (incrementing counter)
- deleted_at, deleted_by (soft delete built-in)

Benefits:
- Complete history (every version preserved)
- Time-travel queries (state at any point in time)
- Immutable (versions never change)
- Regulatory compliance (full audit trail)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from ..enums import TemporalStrategyType
from ..models import VersionInfo
from ..registry import register_strategy
from .base import T, TemporalStrategy


@register_strategy(TemporalStrategyType.SCD2)
class SCD2Strategy(TemporalStrategy[T]):
    """
    SCD2 (Slowly Changing Dimension Type 2) strategy.

    Immutable version history:
    - Each UPDATE creates a new version
    - Old versions are closed (valid_to set)
    - Current version has valid_to = NULL
    - Soft delete built-in
    """

    def __init__(
        self,
        model_class: type,
        query_builder,
        soft_delete: bool = True,  # Always True for SCD2
        multi_tenant: bool = True,
        tenant_field: str = "tenant_id",
    ):
        # SCD2 always has soft delete (deleted_at field)
        super().__init__(
            model_class,
            query_builder,
            soft_delete=True,
            multi_tenant=multi_tenant,
            tenant_field=tenant_field,
        )

    def get_temporal_fields(self) -> Dict[str, tuple[type, Any]]:
        """
        SCD2 temporal fields:
        - valid_from, valid_to (temporal range)
        - version (counter)
        - deleted_at, deleted_by (soft delete)
        """
        fields = self._get_base_fields()  # Includes soft delete, multi-tenant

        # SCD2-specific fields
        fields.update(
            {
                "valid_from": (datetime, "NOW()"),
                "valid_to": (Optional[datetime], None),
                "version": (int, 1),
            }
        )

        return fields

    def get_temporal_indexes(self, table_name: str, schema: str = "public") -> List[dict]:
        """
        SCD2 indexes:
        - Temporal range (valid_from, valid_to)
        - Current version (partial: valid_to IS NULL)
        - Not deleted (partial: deleted_at IS NULL)
        - Versions (id, version) with UNIQUE constraint
        """
        indexes = self._get_base_indexes(table_name)

        # Temporal range index
        indexes.append(
            {
                "name": f"idx_{table_name}_valid_period",
                "table_name": table_name,
                "columns": ["valid_from", "valid_to"],
                "index_type": "btree",
            }
        )

        # Current version (most common query)
        current_version_where = "valid_to IS NULL AND deleted_at IS NULL"
        if self.multi_tenant:
            indexes.append(
                {
                    "name": f"idx_{table_name}_current_version",
                    "table_name": table_name,
                    "columns": ["id", self.tenant_field],
                    "where_clause": current_version_where,
                    "index_type": "btree",
                }
            )
        else:
            indexes.append(
                {
                    "name": f"idx_{table_name}_current_version",
                    "table_name": table_name,
                    "columns": ["id"],
                    "where_clause": current_version_where,
                    "index_type": "btree",
                }
            )

        # CRITICAL: (id, version) UNIQUE constraint
        # Enforces that each logical ID can only have one row per version number
        indexes.append(
            {
                "name": f"idx_{table_name}_id_version_unique",
                "table_name": table_name,
                "columns": ["id", "version"],
                "unique": True,  # UNIQUE constraint
                "index_type": "btree",
            }
        )

        return indexes

    def get_auxiliary_tables(self, table_name: str, schema: str = "public") -> List[dict]:
        """No auxiliary tables for SCD2 (all data in main table)."""
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
        Create first version.

        Sets:
        - id (if not provided)
        - created_at, updated_at
        - created_by
        - tenant_id
        - version = 1
        - valid_from = NOW(), valid_to = NULL
        - deleted_at, deleted_by = NULL
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

        # SCD2 fields
        data["version"] = 1
        data["valid_from"] = now
        data["valid_to"] = None
        data["deleted_at"] = None
        data["deleted_by"] = None
        data["updated_by"] = None  # First version has no updater, only creator

        # Build INSERT query using QueryBuilder
        table_name = self._get_table_name()
        serialized_data = self._serialize_jsonb_fields(data)
        query, values = self.query_builder.build_insert(table_name, serialized_data)

        # Execute
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)

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
        Create new version (immutable update).

        Process:
        1. SELECT current version (valid_to IS NULL)
        2. UPDATE: Close current version (set valid_to = NOW())
        3. INSERT: Create new version (version + 1, valid_from = NOW())

        Transaction ensures atomicity.
        """
        table_name = self._get_table_name()
        quoted_table = self.query_builder.quote_identifier(table_name)
        now = datetime.now(timezone.utc)

        # Build WHERE clause for current version with proper quoting
        where_parts = [
            f"{self.query_builder.quote_identifier('id')} = $1",
            f"{self.query_builder.quote_identifier('valid_to')} IS NULL",
            f"{self.query_builder.quote_identifier('deleted_at')} IS NULL",
        ]
        where_values = [id]

        if self.multi_tenant:
            if not tenant_id:
                raise ValueError("tenant_id required for multi-tenant model")
            tenant_field_quoted = self.query_builder.quote_identifier(self.tenant_field)
            where_parts.append(f"{tenant_field_quoted} = ${len(where_values) + 1}")
            where_values.append(tenant_id)

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # 1. Get current version
                select_query = f"""
                    SELECT * FROM {quoted_table}
                    WHERE {" AND ".join(where_parts)}
                """
                current_row = await conn.fetchrow(select_query, *where_values)

                if not current_row:
                    raise ValueError(f"Record not found or already updated: {id}")

                current_data = dict(current_row)
                current_version = current_data["version"]

                # 2. Check if data actually changed (prevent no-op updates)
                # Get base metadata fields and add SCD2-specific temporal fields
                metadata_fields = self._get_metadata_fields()
                metadata_fields.update({"version", "valid_from", "valid_to"})

                # Compare only user-defined fields
                has_changes = False
                for key, new_value in data.items():
                    if key not in metadata_fields:
                        old_value = current_data.get(key)
                        if old_value != new_value:
                            has_changes = True
                            break

                # If no changes, return current version without creating a new one
                if not has_changes:
                    return self._row_to_model(current_row)

                # 3. Close current version
                valid_to_quoted = self.query_builder.quote_identifier("valid_to")
                close_query = f"""
                    UPDATE {quoted_table}
                    SET {valid_to_quoted} = ${len(where_values) + 1}
                    WHERE {" AND ".join(where_parts)}
                """
                await conn.execute(close_query, *where_values, now)

                # 4. Build new version
                new_data = current_data.copy()

                # Only update with user-defined fields, preserving metadata/temporal fields
                # This prevents tenant_id, created_at, etc. from being overwritten with None
                for key, value in data.items():
                    if key not in metadata_fields:
                        new_data[key] = value

                # Update version fields
                new_data["version"] = current_version + 1
                new_data["valid_from"] = now
                new_data["valid_to"] = None
                new_data["updated_at"] = now

                # Track who made the update (audit trail)
                if user_id:
                    new_data["updated_by"] = user_id

                # Insert new version using QueryBuilder
                serialized_data = self._serialize_jsonb_fields(new_data)
                insert_query, insert_values = self.query_builder.build_insert(
                    table_name, serialized_data
                )
                row = await conn.fetchrow(insert_query, *insert_values)

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
        Soft delete by creating new version with deleted_at set.

        SCD2 immutability principle: Every state change is a new version.
        Deletion is a state change, so we create version N+1 with deleted_at.

        Process:
        1. SELECT current version (valid_to IS NULL, deleted_at IS NULL)
        2. UPDATE: Close current version (set valid_to = NOW())
        3. INSERT: New version with deleted_at = NOW(), version++

        Returns:
            True if deleted, False if not found or already deleted
        """
        table_name = self._get_table_name()
        quoted_table = self.query_builder.quote_identifier(table_name)
        now = datetime.now(timezone.utc)

        # Build WHERE for current version with proper quoting
        where_parts = [
            f"{self.query_builder.quote_identifier('id')} = $1",
            f"{self.query_builder.quote_identifier('valid_to')} IS NULL",
            f"{self.query_builder.quote_identifier('deleted_at')} IS NULL",
        ]
        where_values = [id]

        if self.multi_tenant:
            if not tenant_id:
                raise ValueError("tenant_id required for multi-tenant model")
            tenant_field_quoted = self.query_builder.quote_identifier(self.tenant_field)
            where_parts.append(f"{tenant_field_quoted} = ${len(where_values) + 1}")
            where_values.append(tenant_id)

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # 1. Get current version
                select_query = f"""
                    SELECT * FROM {quoted_table}
                    WHERE {" AND ".join(where_parts)}
                """
                current_row = await conn.fetchrow(select_query, *where_values)

                if not current_row:
                    return False  # Not found or already deleted

                current_data = dict(current_row)
                current_version = current_data["version"]

                # 2. Close current version
                valid_to_quoted = self.query_builder.quote_identifier("valid_to")
                close_query = f"""
                    UPDATE {quoted_table}
                    SET {valid_to_quoted} = ${len(where_values) + 1}
                    WHERE {" AND ".join(where_parts)}
                """
                await conn.execute(close_query, *where_values, now)

                # 3. Create new deleted version
                new_data = current_data.copy()
                new_data["version"] = current_version + 1
                new_data["valid_from"] = now
                new_data["valid_to"] = None
                new_data["deleted_at"] = now  # MARK AS DELETED
                new_data["deleted_by"] = user_id
                new_data["updated_at"] = now

                # INSERT new version using QueryBuilder (without RETURNING)
                serialized_data = self._serialize_jsonb_fields(new_data)
                insert_query, insert_values = self.query_builder.build_insert(
                    table_name, serialized_data
                )
                # Remove RETURNING * since we don't need the row back
                insert_query = insert_query.replace(" RETURNING *", "")
                await conn.execute(insert_query, *insert_values)

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
        Transfer ownership by creating a new version with new tenant_id.

        SCD2 immutability principle: Changing tenant_id is a state change,
        so we create version N+1 with the new tenant_id.

        Process:
        1. SELECT current version (valid_to IS NULL, deleted_at IS NULL)
        2. Validate old tenant_id != new tenant_id (prevent no-op transfers)
        3. UPDATE: Close current version (set valid_to = NOW())
        4. INSERT: New version with new tenant_id, version++

        Args:
            id: Record ID
            new_tenant_id: New tenant to own this record
            current_tenant_id: Current tenant (for validation)
            user_id: User performing transfer (audit trail)

        Returns:
            New version with updated tenant_id

        Raises:
            ValueError: If record not found or tenant_id unchanged
        """
        table_name = self._get_table_name()
        quoted_table = self.query_builder.quote_identifier(table_name)
        now = datetime.now(timezone.utc)

        # Build WHERE for current version with proper quoting
        where_parts = [
            f"{self.query_builder.quote_identifier('id')} = $1",
            f"{self.query_builder.quote_identifier('valid_to')} IS NULL",
            f"{self.query_builder.quote_identifier('deleted_at')} IS NULL",
        ]
        where_values = [id]

        # Optionally validate current tenant
        if current_tenant_id is not None:
            tenant_field_quoted = self.query_builder.quote_identifier(self.tenant_field)
            where_parts.append(f"{tenant_field_quoted} = ${len(where_values) + 1}")
            where_values.append(current_tenant_id)

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # 1. Get current version
                select_query = f"""
                    SELECT * FROM {quoted_table}
                    WHERE {" AND ".join(where_parts)}
                """
                current_row = await conn.fetchrow(select_query, *where_values)

                if not current_row:
                    raise ValueError(f"Record not found: {id}")

                current_data = dict(current_row)
                current_version = current_data["version"]
                current_tenant = current_data.get(self.tenant_field)

                # 2. Validate tenant actually changed (prevent no-op transfers)
                if current_tenant == new_tenant_id:
                    raise ValueError(
                        f"Cannot transfer to same tenant. Record {id} already belongs to {new_tenant_id}"
                    )

                # 3. Close current version
                valid_to_quoted = self.query_builder.quote_identifier("valid_to")
                close_query = f"""
                    UPDATE {quoted_table}
                    SET {valid_to_quoted} = ${len(where_values) + 1}
                    WHERE {" AND ".join(where_parts)}
                """
                await conn.execute(close_query, *where_values, now)

                # 4. Build new version with new tenant_id
                new_data = current_data.copy()
                new_data["version"] = current_version + 1
                new_data["valid_from"] = now
                new_data["valid_to"] = None
                new_data["updated_at"] = now
                new_data[self.tenant_field] = new_tenant_id  # CHANGE TENANT

                # Track who made the transfer (audit trail)
                if user_id:
                    new_data["updated_by"] = user_id

                # Insert new version using QueryBuilder
                serialized_data = self._serialize_jsonb_fields(new_data)
                insert_query, insert_values = self.query_builder.build_insert(
                    table_name, serialized_data
                )
                row = await conn.fetchrow(insert_query, *insert_values)

        return self._row_to_model(row)

    async def get(
        self,
        id: UUID,
        db_pool,
        tenant_id: Optional[UUID] = None,
        as_of: Optional[datetime] = None,
        include_deleted: bool = False,
        **kwargs,
    ) -> Optional[T]:
        """
        Get record (current or historical) with correct soft delete semantics.

        Args:
            as_of: If provided, get version valid at this time (time travel)
            include_deleted: If True, include soft-deleted records

        Current version query (as_of is None):
            WHERE id = ? AND valid_to IS NULL [AND deleted_at IS NULL]

        Time travel query (as_of provided):
            WHERE id = ?
              AND valid_from <= as_of
              AND (valid_to IS NULL OR valid_to > as_of)
              [AND (deleted_at IS NULL OR deleted_at > as_of)]

        CRITICAL: When time-traveling, record is only visible if it was NOT deleted
        at that point in time (deleted_at IS NULL OR deleted_at > as_of).
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

        valid_to_quoted = self.query_builder.quote_identifier("valid_to")
        valid_from_quoted = self.query_builder.quote_identifier("valid_from")
        deleted_at_quoted = self.query_builder.quote_identifier("deleted_at")

        if as_of is None:
            # Current version
            where_parts.append(f"{valid_to_quoted} IS NULL")
            if not include_deleted:
                where_parts.append(f"{deleted_at_quoted} IS NULL")
        else:
            # Time travel: Get version valid at as_of time
            where_parts.append(f"{valid_from_quoted} <= ${len(where_values) + 1}")
            where_values.append(as_of)
            where_parts.append(
                f"({valid_to_quoted} IS NULL OR {valid_to_quoted} > ${len(where_values) + 1})"
            )
            where_values.append(as_of)

            if not include_deleted:
                # CRITICAL: Check if record was deleted at as_of time
                # Record is visible only if:
                # - deleted_at IS NULL (never deleted), OR
                # - deleted_at > as_of (deletion happened AFTER as_of)
                where_parts.append(
                    f"({deleted_at_quoted} IS NULL OR {deleted_at_quoted} > ${len(where_values) + 1})"
                )
                where_values.append(as_of)

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
        as_of: Optional[datetime] = None,
        include_deleted: bool = False,
        **kwargs,
    ) -> List[T]:
        """
        List records (current or historical).

        By default, returns current versions only.
        With as_of, returns versions valid at that time.
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

        valid_to_quoted = self.query_builder.quote_identifier("valid_to")
        valid_from_quoted = self.query_builder.quote_identifier("valid_from")
        deleted_at_quoted = self.query_builder.quote_identifier("deleted_at")

        # Temporal filter
        if as_of is None:
            # Current versions
            where_parts.append(f"{valid_to_quoted} IS NULL")
            if not include_deleted:
                where_parts.append(f"{deleted_at_quoted} IS NULL")
        else:
            # Time travel: Get versions valid at as_of time
            where_parts.append(f"{valid_from_quoted} <= ${len(where_values) + 1}")
            where_values.append(as_of)
            where_parts.append(
                f"({valid_to_quoted} IS NULL OR {valid_to_quoted} > ${len(where_values) + 1})"
            )
            where_values.append(as_of)

            if not include_deleted:
                # CRITICAL: Check if records were deleted at as_of time
                # Same logic as get(): deleted_at IS NULL OR deleted_at > as_of
                where_parts.append(
                    f"({deleted_at_quoted} IS NULL OR {deleted_at_quoted} > ${len(where_values) + 1})"
                )
                where_values.append(as_of)

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

    # ==================== SCD2-Specific Methods ====================

    async def get_version_history(
        self,
        id: UUID,
        db_pool,
        tenant_id: Optional[UUID] = None,
    ) -> List[T]:
        """
        Get all versions of a record, ordered by version.

        Returns every version from creation to present.
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

        version_quoted = self.query_builder.quote_identifier("version")
        query = f"""
            SELECT * FROM {quoted_table}
            WHERE {" AND ".join(where_parts)}
            ORDER BY {version_quoted} ASC
        """

        # Execute
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *where_values)

        return [self._row_to_model(row) for row in rows]

    async def get_version(
        self,
        id: UUID,
        version: int,
        db_pool,
        tenant_id: Optional[UUID] = None,
    ) -> Optional[T]:
        """Get specific version of a record."""
        table_name = self._get_table_name()
        quoted_table = self.query_builder.quote_identifier(table_name)

        # Build WHERE clause with proper quoting
        where_parts = [
            f"{self.query_builder.quote_identifier('id')} = $1",
            f"{self.query_builder.quote_identifier('version')} = $2",
        ]
        where_values = [id, version]

        if self.multi_tenant:
            if not tenant_id:
                raise ValueError("tenant_id required for multi-tenant model")
            tenant_field_quoted = self.query_builder.quote_identifier(self.tenant_field)
            where_parts.append(f"{tenant_field_quoted} = ${len(where_values) + 1}")
            where_values.append(tenant_id)

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

    async def get_version_info(
        self,
        id: UUID,
        db_pool,
        tenant_id: Optional[UUID] = None,
    ) -> List[VersionInfo]:
        """
        Get version metadata (without full records).

        Returns list of VersionInfo with version number, validity range, status.
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

        # Quote column names for SELECT
        version_quoted = self.query_builder.quote_identifier("version")
        valid_from_quoted = self.query_builder.quote_identifier("valid_from")
        valid_to_quoted = self.query_builder.quote_identifier("valid_to")
        deleted_at_quoted = self.query_builder.quote_identifier("deleted_at")

        query = f"""
            SELECT {version_quoted}, {valid_from_quoted}, {valid_to_quoted}, {deleted_at_quoted}
            FROM {quoted_table}
            WHERE {" AND ".join(where_parts)}
            ORDER BY {version_quoted} ASC
        """

        # Execute
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *where_values)

        return [
            VersionInfo(
                version=row["version"],
                valid_from=row["valid_from"],
                valid_to=row["valid_to"],
                is_current=(row["valid_to"] is None),
                is_deleted=(row["deleted_at"] is not None),
            )
            for row in rows
        ]

    async def compare_versions(
        self,
        id: UUID,
        version1: int,
        version2: int,
        db_pool,
        tenant_id: Optional[UUID] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compare two versions field-by-field.

        Returns dict mapping field_name → {old, new, changed}
        """
        # Get both versions
        v1 = await self.get_version(id, version1, db_pool, tenant_id)
        v2 = await self.get_version(id, version2, db_pool, tenant_id)

        if not v1 or not v2:
            raise ValueError(f"Version not found: {id} v{version1} or v{version2}")

        # Convert to dicts
        v1_dict = self._model_to_dict(v1)
        v2_dict = self._model_to_dict(v2)

        # Compare fields
        diff = {}
        all_fields = set(v1_dict.keys()) | set(v2_dict.keys())

        for field in all_fields:
            old_val = v1_dict.get(field)
            new_val = v2_dict.get(field)

            diff[field] = {
                "old": old_val,
                "new": new_val,
                "changed": old_val != new_val,
            }

        return diff

    # ==================== Helper Methods ====================

    def get_current_version_filters(self) -> List[str]:
        """
        Override base method to include SCD2-specific filters.

        For SCD2, current records must have:
        - valid_to IS NULL (current version)
        - deleted_at IS NULL (not deleted)

        Returns:
            List of SQL WHERE conditions (with properly quoted identifiers)
        """
        # Get base filters (deleted_at IS NULL) with proper quoting
        filters = super().get_current_version_filters()

        # Add SCD2 current version filter with proper quoting
        quoted_valid_to = self.query_builder.quote_identifier("valid_to")
        filters.append(f"{quoted_valid_to} IS NULL")

        return filters

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

    def _model_to_dict(self, model: T) -> Dict[str, Any]:
        """Convert model instance to dict."""
        if hasattr(model, "model_dump"):
            # Pydantic v2
            return model.model_dump()
        elif hasattr(model, "dict"):
            # Pydantic v1
            return model.dict()
        else:
            # Dataclass or other
            return {k: getattr(model, k) for k in dir(model) if not k.startswith("_")}
