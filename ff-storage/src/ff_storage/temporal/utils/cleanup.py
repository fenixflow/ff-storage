"""
Cleanup utilities for temporal data.

Production systems need to archive or prune old temporal data:
- Audit logs grow without bound
- SCD2 versions accumulate
- Soft-deleted records stay forever

These utilities help manage data lifecycle.
"""

from datetime import datetime
from typing import Optional


class TemporalCleanup:
    """
    Utilities for cleaning up temporal data.
    """

    def __init__(self, db_pool):
        self.db_pool = db_pool

    async def archive_audit_logs(
        self,
        table_name: str,
        older_than: datetime,
        archive_table_name: Optional[str] = None,
    ) -> int:
        """
        Move old audit logs to archive table.

        Args:
            table_name: Main table name
            older_than: Archive logs older than this date
            archive_table_name: Archive table name (default: {table}_audit_archive)

        Returns:
            Number of rows archived
        """
        audit_table = f"{table_name}_audit"
        archive_table = archive_table_name or f"{audit_table}_archive"

        # Create archive table if not exists (same schema as audit)
        create_archive = f"""
            CREATE TABLE IF NOT EXISTS {archive_table} (LIKE {audit_table} INCLUDING ALL)
        """

        # Move old records
        move_query = f"""
            WITH moved AS (
                DELETE FROM {audit_table}
                WHERE changed_at < $1
                RETURNING *
            )
            INSERT INTO {archive_table}
            SELECT * FROM moved
        """

        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                # Create archive table
                await conn.execute(create_archive)

                # Move records
                result = await conn.execute(move_query, older_than)

                # Parse result: "INSERT 0 N" or "DELETE N"
                count = int(result.split()[-1]) if result else 0

        return count

    async def prune_scd2_versions(
        self,
        table_name: str,
        keep_versions: int = 10,
        tenant_id: Optional[str] = None,
    ) -> int:
        """
        Keep only N most recent versions per record (SCD2 strategy).

        Args:
            table_name: Table name
            keep_versions: Number of versions to keep
            tenant_id: Optional tenant filter

        Returns:
            Number of versions deleted
        """
        # Find old versions to delete
        where_clause = f"AND tenant_id = '{tenant_id}'" if tenant_id else ""

        delete_query = f"""
            WITH ranked AS (
                SELECT id, version,
                       ROW_NUMBER() OVER (PARTITION BY id ORDER BY version DESC) as rn
                FROM {table_name}
                {where_clause}
            )
            DELETE FROM {table_name}
            WHERE (id, version) IN (
                SELECT id, version FROM ranked WHERE rn > $1
            )
        """

        async with self.db_pool.acquire() as conn:
            result = await conn.execute(delete_query, keep_versions)
            count = int(result.split()[-1]) if result else 0

        return count

    async def purge_soft_deleted(
        self,
        table_name: str,
        older_than: datetime,
        tenant_id: Optional[str] = None,
    ) -> int:
        """
        Permanently delete soft-deleted records older than date.

        Args:
            table_name: Table name
            older_than: Purge records deleted before this date
            tenant_id: Optional tenant filter

        Returns:
            Number of records purged
        """
        where_parts = ["deleted_at IS NOT NULL", "deleted_at < $1"]
        where_values = [older_than]

        if tenant_id:
            where_parts.append(f"tenant_id = ${len(where_values) + 1}")
            where_values.append(tenant_id)

        delete_query = f"""
            DELETE FROM {table_name}
            WHERE {" AND ".join(where_parts)}
        """

        async with self.db_pool.acquire() as conn:
            result = await conn.execute(delete_query, *where_values)
            count = int(result.split()[-1]) if result else 0

        return count

    async def vacuum_table(self, table_name: str):
        """
        Run VACUUM on table to reclaim space.

        Run this after bulk deletions to reclaim disk space.

        Args:
            table_name: Table name
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(f"VACUUM {table_name}")
