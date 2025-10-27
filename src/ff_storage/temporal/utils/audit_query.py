"""
Helper utilities for querying audit logs.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID


class AuditQueryHelper:
    """
    Helper utilities for querying audit tables (copy_on_change strategy).
    """

    def __init__(self, db_pool, table_name: str):
        self.db_pool = db_pool
        self.table_name = table_name
        self.audit_table_name = f"{table_name}_audit"

    async def get_changes_by_user(
        self,
        user_id: UUID,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get all changes made by a specific user.

        Args:
            user_id: User ID
            start: Start date (optional)
            end: End date (optional)
            limit: Max records

        Returns:
            List of audit entries
        """
        where_parts = ["changed_by = $1"]
        where_values = [user_id]

        if start:
            where_parts.append(f"changed_at >= ${len(where_values) + 1}")
            where_values.append(start)

        if end:
            where_parts.append(f"changed_at <= ${len(where_values) + 1}")
            where_values.append(end)

        query = f"""
            SELECT * FROM {self.audit_table_name}
            WHERE {" AND ".join(where_parts)}
            ORDER BY changed_at DESC
            LIMIT ${len(where_values) + 1}
        """

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *where_values, limit)

        return [dict(row) for row in rows]

    async def get_changes_in_range(
        self,
        start: datetime,
        end: datetime,
        operation: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get all changes in date range.

        Args:
            start: Start date
            end: End date
            operation: Filter by operation (INSERT, UPDATE, DELETE)

        Returns:
            List of audit entries
        """
        where_parts = ["changed_at >= $1", "changed_at <= $2"]
        where_values = [start, end]

        if operation:
            where_parts.append(f"operation = ${len(where_values) + 1}")
            where_values.append(operation)

        query = f"""
            SELECT * FROM {self.audit_table_name}
            WHERE {" AND ".join(where_parts)}
            ORDER BY changed_at ASC
        """

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *where_values)

        return [dict(row) for row in rows]

    async def reconstruct_record_at_time(
        self,
        record_id: UUID,
        as_of: datetime,
        tenant_id: Optional[UUID] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Reconstruct record state at specific time (advanced).

        This is complex: need to replay all changes up to as_of.

        Args:
            record_id: Record ID
            as_of: Target datetime
            tenant_id: Tenant context

        Returns:
            Dict with reconstructed field values
        """
        # Get current record
        current_query = f"SELECT * FROM {self.table_name} WHERE id = $1"
        if tenant_id:
            current_query += " AND tenant_id = $2"
            current_params = [record_id, tenant_id]
        else:
            current_params = [record_id]

        async with self.db_pool.acquire() as conn:
            current_row = await conn.fetchrow(current_query, *current_params)

            if not current_row:
                return None

            current_data = dict(current_row)

            # Get all audit entries after as_of (to reverse)
            audit_query = f"""
                SELECT * FROM {self.audit_table_name}
                WHERE record_id = $1 AND changed_at > $2
                ORDER BY changed_at DESC
            """
            audit_params = [record_id, as_of]

            rows = await conn.fetch(audit_query, *audit_params)

            # Reverse changes
            for row in rows:
                field_name = row["field_name"]
                old_value = row["old_value"]

                if old_value is not None:
                    current_data[field_name] = old_value
                else:
                    # Field didn't exist at that time
                    current_data.pop(field_name, None)

        return current_data
