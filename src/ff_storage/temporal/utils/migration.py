"""
Migration utilities for adding temporal to existing tables.
"""

from typing import Optional

from ..enums import TemporalStrategyType


class TemporalMigration:
    """
    Utilities for migrating existing tables to temporal strategies.
    """

    def __init__(self, db_pool):
        self.db_pool = db_pool

    async def add_temporal_fields(
        self,
        table_name: str,
        strategy: TemporalStrategyType,
        soft_delete: bool = True,
        multi_tenant: bool = True,
        tenant_field: str = "tenant_id",
        backfill_tenant_id: Optional[str] = None,
    ):
        """
        Add temporal fields to existing table.

        Args:
            table_name: Existing table name
            strategy: Temporal strategy to apply
            soft_delete: Add soft delete fields
            multi_tenant: Add tenant field
            tenant_field: Name of tenant field
            backfill_tenant_id: If provided, backfill existing rows with this tenant_id
        """
        alter_statements = []

        # Multi-tenant
        if multi_tenant:
            alter_statements.append(
                f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {tenant_field} UUID"
            )

            if backfill_tenant_id:
                alter_statements.append(
                    f"UPDATE {table_name} SET {tenant_field} = '{backfill_tenant_id}' WHERE {tenant_field} IS NULL"
                )

        # Soft delete
        if soft_delete:
            alter_statements.extend(
                [
                    f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ",
                    f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS deleted_by UUID",
                ]
            )

        # Strategy-specific fields
        if strategy == TemporalStrategyType.SCD2:
            alter_statements.extend(
                [
                    f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ DEFAULT NOW()",
                    f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ",
                    f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1",
                ]
            )

            # Backfill version numbers
            alter_statements.append(f"UPDATE {table_name} SET version = 1 WHERE version IS NULL")

        elif strategy == TemporalStrategyType.COPY_ON_CHANGE:
            # Create audit table
            audit_table = f"{table_name}_audit"
            create_audit = f"""
                CREATE TABLE IF NOT EXISTS {audit_table} (
                    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    record_id UUID NOT NULL,
                    {tenant_field} UUID {"NOT NULL" if multi_tenant else ""},
                    field_name VARCHAR(255) NOT NULL,
                    old_value JSONB,
                    new_value JSONB,
                    operation VARCHAR(10) NOT NULL,
                    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    changed_by UUID,
                    transaction_id UUID,
                    metadata JSONB,
                    FOREIGN KEY (record_id) REFERENCES {table_name}(id)
                )
            """
            alter_statements.append(create_audit)

            # Create indexes on audit table
            alter_statements.extend(
                [
                    f"CREATE INDEX IF NOT EXISTS idx_{audit_table}_record_field ON {audit_table}(record_id, field_name)",
                    f"CREATE INDEX IF NOT EXISTS idx_{audit_table}_changed_at ON {audit_table}(changed_at)",
                ]
            )

        # Execute all statements
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                for stmt in alter_statements:
                    await conn.execute(stmt)

    async def create_temporal_indexes(
        self,
        table_name: str,
        strategy: TemporalStrategyType,
        soft_delete: bool = True,
        multi_tenant: bool = True,
        tenant_field: str = "tenant_id",
    ):
        """
        Create indexes for temporal fields.

        Args:
            table_name: Table name
            strategy: Temporal strategy
            soft_delete: Has soft delete fields
            multi_tenant: Has tenant field
            tenant_field: Name of tenant field
        """
        index_statements = []

        # Multi-tenant indexes
        if multi_tenant:
            index_statements.append(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{tenant_field} ON {table_name}({tenant_field})"
            )

            where_clause = "deleted_at IS NULL" if soft_delete else ""
            index_statements.append(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{tenant_field}_created "
                f"ON {table_name}({tenant_field}, created_at DESC) "
                f"{'WHERE ' + where_clause if where_clause else ''}"
            )

        # Soft delete partial index
        if soft_delete:
            index_statements.append(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_not_deleted "
                f"ON {table_name}(deleted_at) WHERE deleted_at IS NULL"
            )

        # SCD2 indexes
        if strategy == TemporalStrategyType.SCD2:
            index_statements.extend(
                [
                    f"CREATE INDEX IF NOT EXISTS idx_{table_name}_valid_period "
                    f"ON {table_name}(valid_from, valid_to)",
                    f"CREATE INDEX IF NOT EXISTS idx_{table_name}_current_version "
                    f"ON {table_name}(id{', ' + tenant_field if multi_tenant else ''}) "
                    f"WHERE valid_to IS NULL AND deleted_at IS NULL",
                    f"CREATE INDEX IF NOT EXISTS idx_{table_name}_versions "
                    f"ON {table_name}(id, version)",
                ]
            )

        # Execute all statements
        async with self.db_pool.acquire() as conn:
            for stmt in index_statements:
                await conn.execute(stmt)
