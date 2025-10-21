"""
Schema synchronization orchestrator.

Automatically detects database provider and uses appropriate implementations
to sync schema from model definitions.
"""

import logging
from typing import List, Type

from .base import (
    MigrationGeneratorBase,
    SchemaDifferBase,
    SchemaIntrospectorBase,
    SQLParserBase,
)
from .models import ChangeType


class SchemaManager:
    """
    Main orchestrator for Terraform-like schema synchronization.

    Usage:
        manager = SchemaManager(db_connection, logger=logger)
        changes = manager.sync_schema(
            models=get_all_models(),
            allow_destructive=False,
            dry_run=False
        )
    """

    def __init__(self, db_connection, logger=None):
        """
        Initialize schema manager.

        Args:
            db_connection: Database connection (Postgres, MySQL, SQLServer)
            logger: Optional logger instance
        """
        self.db = db_connection
        self.logger = logger or logging.getLogger(__name__)

        # Auto-detect provider
        self.provider = self._detect_provider()

        # Initialize components
        self.introspector = self._create_introspector()
        self.parser = self._create_parser()
        self.generator = self._create_generator()
        self.differ = SchemaDifferBase(logger=self.logger)

    def _detect_provider(self) -> str:
        """
        Detect database provider from connection object.

        Returns:
            Provider name: 'postgres', 'mysql', or 'sqlserver'
        """
        # Check db_type attribute
        db_type = getattr(self.db, "db_type", None)
        if db_type:
            return db_type

        # Fallback: check class name
        class_name = self.db.__class__.__name__.lower()
        if "postgres" in class_name:
            return "postgres"
        elif "mysql" in class_name:
            return "mysql"
        elif "sqlserver" in class_name or "mssql" in class_name:
            return "sqlserver"

        raise ValueError(f"Could not detect database provider from connection: {type(self.db)}")

    def _create_introspector(self) -> SchemaIntrospectorBase:
        """Factory method for provider-specific introspector."""
        if self.provider == "postgres":
            from .postgres import PostgresSchemaIntrospector

            return PostgresSchemaIntrospector(self.db, self.logger)
        elif self.provider == "mysql":
            from .mysql import MySQLSchemaIntrospector

            return MySQLSchemaIntrospector(self.db, self.logger)
        elif self.provider == "sqlserver":
            from .sqlserver import SQLServerSchemaIntrospector

            return SQLServerSchemaIntrospector(self.db, self.logger)
        else:
            raise ValueError(f"Unsupported database provider: {self.provider}")

    def _create_parser(self) -> SQLParserBase:
        """Factory method for provider-specific SQL parser."""
        if self.provider == "postgres":
            from .postgres import PostgresSQLParser

            return PostgresSQLParser()
        elif self.provider == "mysql":
            from .mysql import MySQLSQLParser

            return MySQLSQLParser()
        elif self.provider == "sqlserver":
            from .sqlserver import SQLServerSQLParser

            return SQLServerSQLParser()
        else:
            raise ValueError(f"Unsupported database provider: {self.provider}")

    def _create_generator(self) -> MigrationGeneratorBase:
        """Factory method for provider-specific migration generator."""
        if self.provider == "postgres":
            from .postgres import PostgresMigrationGenerator

            return PostgresMigrationGenerator()
        elif self.provider == "mysql":
            from .mysql import MySQLMigrationGenerator

            return MySQLMigrationGenerator()
        elif self.provider == "sqlserver":
            from .sqlserver import SQLServerMigrationGenerator

            return SQLServerMigrationGenerator()
        else:
            raise ValueError(f"Unsupported database provider: {self.provider}")

    def sync_schema(
        self, models: List[Type], allow_destructive: bool = False, dry_run: bool = False
    ) -> int:
        """
        Synchronize database schema with model definitions.

        Args:
            models: List of model classes with get_create_table_sql() method
            allow_destructive: Allow destructive changes (DROP operations)
            dry_run: Show changes without applying them

        Returns:
            Number of changes applied (0 if dry_run)
        """
        self.logger.info(
            "Schema sync started",
            extra={
                "provider": self.provider,
                "models_count": len(models),
                "allow_destructive": allow_destructive,
                "dry_run": dry_run,
            },
        )

        # ==================== PHASE 0: Ensure Required Schemas Exist ====================
        # Extract unique schemas from all models and ensure they exist
        schemas = set()
        for model_class in models:
            if hasattr(model_class, "__schema__"):
                schema = model_class.__schema__
                if schema and schema not in ("public", "pg_catalog", "information_schema"):
                    schemas.add(schema)

        # Create schemas if they don't exist
        # Note: DDL is safe because schema names come from model __schema__ attributes
        for schema in schemas:
            try:
                self.logger.info(f"Ensuring schema exists: {schema}")
                # Use trusted_source context for internally-generated DDL
                self.db.execute(
                    f"CREATE SCHEMA IF NOT EXISTS {schema}",
                    context={"trusted_source": True, "source": "schema_manager.ensure_schemas"},
                )
            except Exception as e:
                self.logger.warning(f"Could not create schema {schema}: {e}")

        all_changes = []

        # Process each model
        for model_class in models:
            # Get desired state from model
            try:
                # Support both get_create_table_sql() and create_table_sql()
                if hasattr(model_class, "get_create_table_sql"):
                    sql = model_class.get_create_table_sql()
                elif hasattr(model_class, "create_table_sql"):
                    sql = model_class.create_table_sql()
                else:
                    self.logger.warning(
                        f"Model {model_class.__name__} has no create_table_sql() or get_create_table_sql() method"
                    )
                    continue

                desired = self.parser.parse_create_table(sql)
            except Exception as e:
                self.logger.error(
                    f"Failed to parse SQL for model {model_class.__name__}", extra={"error": str(e)}
                )
                continue

            # Get current state from database
            try:
                # Support both table_name() and get_table_name()
                if hasattr(model_class, "get_table_name"):
                    table_name = model_class.get_table_name()
                elif hasattr(model_class, "table_name"):
                    table_name = model_class.table_name()
                else:
                    table_name = model_class.__name__.lower() + "s"

                current = self.introspector.get_table_schema(
                    table_name=table_name, schema=model_class.__schema__
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
                    if change.change_type == ChangeType.ADD_COLUMN:
                        change.sql = self.generator.generate_add_column(
                            table_name=change.table_name,
                            schema=desired.schema,
                            column=change.column,
                        )
                    elif change.change_type == ChangeType.ADD_INDEX:
                        change.sql = self.generator.generate_create_index(
                            schema=desired.schema, index=change.index
                        )
                    elif change.change_type == ChangeType.CREATE_TABLE:
                        change.sql = self.generator.generate_create_table(desired)
                except Exception as e:
                    self.logger.error(
                        f"Failed to generate SQL for change: {change.description}",
                        extra={"error": str(e)},
                    )
                    continue

            all_changes.extend(changes)

        # ==================== PHASE 2: Process Auxiliary Tables (NEW in v3.0.0) ====================

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

            # Process each auxiliary table (e.g., audit tables)
            for aux_table_def in aux_tables:
                try:
                    # Convert dict → TableDefinition
                    from .models import ColumnDefinition, IndexDefinition, TableDefinition

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

                    # Check if auxiliary table exists
                    try:
                        current_aux = self.introspector.get_table_schema(
                            table_name=aux_table.name,
                            schema=aux_table.schema,
                        )
                    except Exception:
                        current_aux = None  # Table doesn't exist

                    # Compute diff
                    aux_changes = self.differ.compute_changes(aux_table, current_aux)

                    # Generate SQL
                    for change in aux_changes:
                        try:
                            if change.change_type == ChangeType.CREATE_TABLE:
                                change.sql = self.generator.generate_create_table(aux_table)
                            elif change.change_type == ChangeType.ADD_COLUMN:
                                change.sql = self.generator.generate_add_column(
                                    table_name=aux_table.name,
                                    schema=aux_table.schema,
                                    column=change.column,
                                )
                            elif change.change_type == ChangeType.ADD_INDEX:
                                change.sql = self.generator.generate_create_index(
                                    schema=aux_table.schema,
                                    index=change.index,
                                )
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

        # Filter destructive changes
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

        # Determine changes to apply
        changes_to_apply = safe_changes
        if allow_destructive:
            changes_to_apply.extend(destructive_changes)

        # Dry run?
        if dry_run:
            self.logger.info("DRY RUN - Changes that would be applied:")
            for change in changes_to_apply:
                self.logger.info(f"  {change.description}", extra={"sql": change.sql})
            return 0

        # Apply changes in transaction
        if not changes_to_apply:
            self.logger.info("No schema changes needed")
            return 0

        statements = [c.sql for c in changes_to_apply]
        transaction_sql = self.generator.wrap_in_transaction(statements)

        try:
            # Use trusted_source context for internally-generated DDL wrapped in transaction
            self.db.execute(
                transaction_sql,
                context={"trusted_source": True, "source": "schema_manager.apply_changes"},
            )
            self.logger.info(
                f"Applied {len(statements)} schema changes successfully",
                extra={"changes": [c.description for c in changes_to_apply]},
            )
            return len(statements)
        except Exception as e:
            self.logger.error("Schema sync failed", extra={"error": str(e)}, exc_info=True)
            raise
