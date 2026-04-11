"""
Async schema synchronization manager for ff-storage.

This module provides an async version of SchemaManager that works
with PostgresPool instead of sync Postgres connections, enabling
unified async operations for both CRUD and schema management.

Usage:
    from ff_storage.db.schema_sync import AsyncSchemaManager

    pool = PostgresPool(...)
    await pool.connect()

    manager = AsyncSchemaManager(pool, logger=logger)
    changes = await manager.sync_schema(
        models=[Author, Post, Comment],
        allow_destructive=False,
        dry_run=False
    )
"""

import logging
from typing import TYPE_CHECKING, List, Type

from .async_introspector import AsyncPostgresSchemaIntrospector
from .base import SchemaDifferBase
from .models import ChangeType, TableDefinition
from .normalizer import PostgresNormalizer
from .postgres import PostgresMigrationGenerator, PostgresSQLParser

if TYPE_CHECKING:
    from ...pydantic_support.base import PydanticModel
    from ..pool.postgres import PostgresPool


class AsyncSchemaManager:
    """
    Async schema synchronization manager using asyncpg.

    This is the async equivalent of SchemaManager, designed to work
    with PostgresPool for unified async database operations.

    Provides Terraform-like schema management:
    - Automatic detection of schema changes
    - Safe migration generation (additive by default)
    - Destructive changes require explicit opt-in
    - Dry-run mode for previewing changes

    Usage:
        pool = PostgresPool(host=..., dbname=...)
        await pool.connect()

        manager = AsyncSchemaManager(pool, logger=logger)

        # Preview changes
        changes = await manager.sync_schema(models, dry_run=True)

        # Apply changes
        await manager.sync_schema(models, dry_run=False)
    """

    def __init__(
        self,
        db_pool: "PostgresPool",
        logger=None,
    ):
        """
        Initialize async schema manager.

        Args:
            db_pool: PostgresPool instance for async database access
            logger: Optional logger instance
        """
        self.db_pool = db_pool
        self.logger = logger or logging.getLogger(__name__)

        # PostgreSQL-specific components
        self.normalizer = PostgresNormalizer()
        self.introspector = AsyncPostgresSchemaIntrospector(db_pool, self.logger)
        self.parser = PostgresSQLParser()
        self.generator = PostgresMigrationGenerator()
        self.differ = SchemaDifferBase(normalizer=self.normalizer, logger=self.logger)

    def _is_valid_identifier(self, identifier: str) -> bool:
        """Validate that an identifier is safe for SQL."""
        import re

        return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier))

    def _generate_sql_for_change(self, change, table_def: TableDefinition) -> None:
        """Generate SQL for a schema change and populate change.sql."""
        if change.change_type == ChangeType.ADD_COLUMN:
            change.sql = self.generator.generate_add_column(
                table_name=change.table_name,
                schema=table_def.schema,
                column=change.column,
            )
        elif change.change_type == ChangeType.ADD_INDEX:
            change.sql = self.generator.generate_create_index(
                schema=table_def.schema, index=change.index
            )
        elif change.change_type == ChangeType.CREATE_TABLE:
            change.sql = self.generator.generate_create_table(table_def)
        elif change.change_type == ChangeType.DROP_INDEX:
            change.sql = self.generator.generate_drop_index(
                schema=table_def.schema, index=change.index
            )
        elif change.change_type == ChangeType.DROP_COLUMN:
            change.sql = self.generator.generate_drop_column(
                table_name=change.table_name,
                schema=table_def.schema,
                column=change.column,
            )
        elif change.change_type == ChangeType.ALTER_COLUMN_TYPE:
            change.sql = self.generator.generate_alter_column(
                table_name=change.table_name,
                schema=table_def.schema,
                column=change.column,
            )

    async def sync_schema(
        self,
        models: List[Type["PydanticModel"]],
        allow_destructive: bool = False,
        dry_run: bool = False,
    ) -> int:
        """
        Synchronize database schema with model definitions.

        This is the main entry point for schema synchronization.
        Compares model definitions against the current database schema
        and generates/applies necessary migrations.

        Args:
            models: List of PydanticModel classes to sync
            allow_destructive: Allow destructive changes (DROP operations)
            dry_run: Show changes without applying them

        Returns:
            Number of changes applied (0 if dry_run)

        Example:
            manager = AsyncSchemaManager(pool)
            changes = await manager.sync_schema(
                models=[Author, Post, Comment],
                allow_destructive=False,
                dry_run=True
            )
            print(f"Would apply {changes} changes")
        """
        self.logger.info(
            "Async schema sync started",
            extra={
                "models_count": len(models),
                "allow_destructive": allow_destructive,
                "dry_run": dry_run,
            },
        )

        # ==================== PHASE 0: Ensure Required Schemas Exist ====================
        schemas = set()
        for model_class in models:
            if hasattr(model_class, "__schema__"):
                schema = model_class.__schema__
                if schema and schema not in ("public", "pg_catalog", "information_schema"):
                    schemas.add(schema)

        # Create schemas if they don't exist
        for schema in schemas:
            if not self._is_valid_identifier(schema):
                self.logger.error(
                    f"Invalid schema name: {schema}. Must match ^[a-zA-Z_][a-zA-Z0-9_]*$"
                )
                continue

            try:
                self.logger.info(f"Ensuring schema exists: {schema}")
                async with self.db_pool.acquire() as conn:
                    # Use PostgreSQL's format() for safe identifier quoting
                    result = await conn.fetchrow(
                        "SELECT format('CREATE SCHEMA IF NOT EXISTS %I', $1)",
                        schema,
                    )
                    if result:
                        safe_sql = result[0]
                        await conn.execute(safe_sql)
            except Exception as e:
                self.logger.warning(f"Could not create schema {schema}: {e}")

        all_changes = []

        # ==================== PHASE 1: Process Main Tables ====================
        for model_class in models:
            # Get desired state from model
            try:
                if hasattr(model_class, "get_create_table_sql"):
                    sql = model_class.get_create_table_sql()
                elif hasattr(model_class, "create_table_sql"):
                    sql = model_class.create_table_sql()
                else:
                    self.logger.warning(
                        f"Model {model_class.__name__} has no create_table_sql() method"
                    )
                    continue

                desired = self.parser.parse_create_table(sql)
            except Exception as e:
                self.logger.error(
                    f"Failed to parse SQL for model {model_class.__name__}",
                    extra={"error": str(e)},
                )
                continue

            # Get current state from database
            try:
                if hasattr(model_class, "get_table_name"):
                    table_name = model_class.get_table_name()
                elif hasattr(model_class, "table_name"):
                    table_name = model_class.table_name()
                else:
                    table_name = model_class.__name__.lower() + "s"

                model_schema = getattr(model_class, "__schema__", "public")
                current = await self.introspector.get_table_schema(
                    table_name=table_name, schema=model_schema
                )
            except Exception as e:
                self.logger.error(
                    f"Failed to introspect table for model {model_class.__name__}",
                    extra={"error": str(e)},
                )
                continue

            # Compute diff
            changes = self.differ.compute_changes(desired, current)

            # Generate SQL for each change
            for change in changes:
                try:
                    self._generate_sql_for_change(change, desired)
                except Exception as e:
                    self.logger.error(
                        f"Failed to generate SQL for change: {change.description}",
                        extra={"error": str(e)},
                    )
                    continue

            all_changes.extend(changes)

        # ==================== PHASE 2: Process Auxiliary Tables ====================
        for model_class in models:
            if not hasattr(model_class, "get_auxiliary_tables"):
                continue

            try:
                aux_tables = model_class.get_auxiliary_tables()
            except Exception as e:
                self.logger.error(
                    f"Failed to get auxiliary tables for {model_class.__name__}",
                    extra={"error": str(e)},
                )
                continue

            for aux_table_def in aux_tables:
                try:
                    from .models import ColumnDefinition, IndexDefinition

                    aux_table = TableDefinition(
                        name=aux_table_def["name"],
                        schema=aux_table_def.get("schema", "public"),
                        columns=[
                            ColumnDefinition(**col_dict) for col_dict in aux_table_def["columns"]
                        ],
                        indexes=[
                            IndexDefinition(**idx_dict)
                            for idx_dict in aux_table_def.get("indexes", [])
                        ],
                    )

                    try:
                        current_aux = await self.introspector.get_table_schema(
                            table_name=aux_table.name,
                            schema=aux_table.schema,
                        )
                    except Exception:
                        current_aux = None

                    aux_changes = self.differ.compute_changes(aux_table, current_aux)

                    for change in aux_changes:
                        try:
                            self._generate_sql_for_change(change, aux_table)
                        except Exception as e:
                            self.logger.error(
                                f"Failed to generate SQL for auxiliary table change: {change.description}",
                                extra={"error": str(e)},
                            )
                            continue

                    all_changes.extend(aux_changes)

                except Exception as e:
                    self.logger.error(
                        f"Failed to process auxiliary table {aux_table_def.get('name', 'unknown')}",
                        extra={"error": str(e)},
                    )
                    continue

        # ==================== PHASE 3: Filter and Apply Changes ====================
        safe_changes = [c for c in all_changes if not c.is_destructive]
        destructive_changes = [c for c in all_changes if c.is_destructive]

        if destructive_changes and not allow_destructive:
            self.logger.warning(
                "Skipping destructive changes (set allow_destructive=True to apply)",
                extra={
                    "count": len(destructive_changes),
                    "changes": [c.description for c in destructive_changes],
                },
            )

        changes_to_apply = safe_changes
        if allow_destructive:
            changes_to_apply.extend(destructive_changes)

        # Dry run - just log what would be done
        if dry_run:
            if not changes_to_apply:
                self.logger.info("DRY RUN - No schema changes needed")
            else:
                self.logger.info("DRY RUN - Changes that would be applied:")
                for change in changes_to_apply:
                    self.logger.info(f"  {change.description}", extra={"sql": change.sql})
            return 0

        # No changes needed
        if not changes_to_apply:
            self.logger.info("No schema changes needed")
            return 0

        # Apply changes in transaction
        statements = [c.sql for c in changes_to_apply]
        transaction_sql = self.generator.wrap_in_transaction(statements)

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(transaction_sql)

            # Build summary
            changes_by_table = {}
            for change in changes_to_apply:
                table = change.table_name
                if table not in changes_by_table:
                    changes_by_table[table] = []
                changes_by_table[table].append(change.description)

            summary_lines = []
            for table, table_changes in sorted(changes_by_table.items()):
                summary_lines.append(f"\n  {table}: ({len(table_changes)} changes)")
                for desc in table_changes:
                    summary_lines.append(f"    - {desc}")

            self.logger.info(
                f"Applied {len(statements)} schema changes successfully:{''.join(summary_lines)}"
            )
            return len(statements)

        except Exception as e:
            self.logger.error("Async schema sync failed", extra={"error": str(e)}, exc_info=True)
            raise

    async def compare_schemas(
        self,
        desired_schema: dict,
        current_schema: dict,
    ) -> list:
        """
        Compare desired schema against current schema and return list of changes.

        This method is useful for inspecting what changes would be made without
        actually applying them.

        Args:
            desired_schema: Dict of {schema_name: {table_name: TableDefinition}}
            current_schema: Dict of {schema_name: {table_name: TableDefinition}}

        Returns:
            List of SchemaChange objects representing the differences
        """
        all_changes = []

        for schema_name, desired_tables in desired_schema.items():
            current_tables = current_schema.get(schema_name, {})

            for table_name, desired_table in desired_tables.items():
                current_table = current_tables.get(table_name)

                changes = self.differ.compute_changes(desired_table, current_table)

                for change in changes:
                    try:
                        self._generate_sql_for_change(change, desired_table)
                    except Exception as e:
                        self.logger.error(
                            f"Failed to generate SQL for change: {change.description}",
                            extra={"error": str(e)},
                        )
                        continue

                all_changes.extend(changes)

        return all_changes

    async def get_current_schema(self, schema: str = "public") -> dict:
        """
        Get the current database schema for a given schema namespace.

        Args:
            schema: Schema name (default: "public")

        Returns:
            Dict mapping table names to TableDefinition objects
        """
        tables = await self.introspector.get_tables(schema)
        result = {}

        for table_name in tables:
            table_def = await self.introspector.get_table_schema(table_name, schema)
            if table_def:
                result[table_name] = table_def

        return result
