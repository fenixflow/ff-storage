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

        # Create provider-specific normalizer for consistent schema comparison
        self.normalizer = self._create_normalizer()

        # Initialize components
        self.introspector = self._create_introspector()
        self.parser = self._create_parser()
        self.generator = self._create_generator()
        self.differ = SchemaDifferBase(normalizer=self.normalizer, logger=self.logger)

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

    def _create_normalizer(self):
        """
        Factory method for provider-specific normalizer.

        Returns provider-specific normalizer that handles database-specific quirks:
            - PostgreSQL: float8/float4 aliases, boolean formats
            - MySQL: (future implementation)
            - SQL Server: (future implementation)

        Returns:
            SchemaNormalizer subclass for the detected provider
        """
        if self.provider == "postgres":
            from .normalizer import PostgresNormalizer

            return PostgresNormalizer()
        elif self.provider == "mysql":
            from .normalizer import MySQLNormalizer

            return MySQLNormalizer()
        elif self.provider == "sqlserver":
            from .normalizer import SQLServerNormalizer

            return SQLServerNormalizer()
        else:
            # Generic fallback
            from .normalizer import SchemaNormalizer

            return SchemaNormalizer()

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

    def _is_valid_identifier(self, identifier: str) -> bool:
        """
        Validate that an identifier is safe for SQL.

        Args:
            identifier: Schema, table, or column name

        Returns:
            True if valid, False otherwise
        """
        import re

        # Must start with letter or underscore, followed by alphanumeric or underscore
        return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier))

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
        for schema in schemas:
            try:
                # Validate schema name (must be valid PostgreSQL identifier)
                if not self._is_valid_identifier(schema):
                    self.logger.error(
                        f"Invalid schema name: {schema}. Must match ^[a-zA-Z_][a-zA-Z0-9_]*$"
                    )
                    continue

                self.logger.info(f"Ensuring schema exists: {schema}")
                # Use format() with %I for safe identifier quoting
                if self.provider == "postgres":
                    # Use PostgreSQL's format() function for safe identifier quoting
                    sql = f"SELECT format('CREATE SCHEMA IF NOT EXISTS %I', '{schema}')"
                    result = self.db.read_query(sql, as_dict=False)
                    safe_sql = result[0][0] if result else None
                    if safe_sql:
                        self.db.execute(
                            safe_sql,
                            context={
                                "trusted_source": True,
                                "source": "schema_manager.ensure_schemas",
                            },
                        )
                else:
                    # For other providers, use validated identifier directly
                    self.db.execute(
                        f"CREATE SCHEMA IF NOT EXISTS {schema}",
                        context={
                            "trusted_source": True,
                            "source": "schema_manager.ensure_schemas",
                        },
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
                    elif change.change_type == ChangeType.DROP_INDEX:
                        change.sql = self.generator.generate_drop_index(
                            schema=desired.schema, index=change.index
                        )
                    elif change.change_type == ChangeType.DROP_COLUMN:
                        change.sql = self.generator.generate_drop_column(
                            table_name=change.table_name,
                            schema=desired.schema,
                            column=change.column,
                        )
                    elif change.change_type == ChangeType.ALTER_COLUMN_TYPE:
                        change.sql = self.generator.generate_alter_column(
                            table_name=change.table_name,
                            schema=desired.schema,
                            column=change.column,
                        )
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
                            elif change.change_type == ChangeType.DROP_INDEX:
                                change.sql = self.generator.generate_drop_index(
                                    schema=aux_table.schema, index=change.index
                                )
                            elif change.change_type == ChangeType.DROP_COLUMN:
                                change.sql = self.generator.generate_drop_column(
                                    table_name=aux_table.name,
                                    schema=aux_table.schema,
                                    column=change.column,
                                )
                            elif change.change_type == ChangeType.ALTER_COLUMN_TYPE:
                                change.sql = self.generator.generate_alter_column(
                                    table_name=aux_table.name,
                                    schema=aux_table.schema,
                                    column=change.column,
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

            # Group changes by table for better readability
            changes_by_table = {}
            for change in changes_to_apply:
                table = change.table_name
                if table not in changes_by_table:
                    changes_by_table[table] = []
                changes_by_table[table].append(change.description)

            # Build formatted summary
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
            self.logger.error("Schema sync failed", extra={"error": str(e)}, exc_info=True)
            raise
