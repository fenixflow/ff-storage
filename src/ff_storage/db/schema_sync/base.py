"""
Abstract base classes for provider-specific implementations.

Each database provider (PostgreSQL, MySQL, SQL Server) implements these
interfaces to provide schema introspection, SQL parsing, and migration generation.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from .models import ColumnDefinition, IndexDefinition, SchemaChange, TableDefinition


class SchemaIntrospectorBase(ABC):
    """
    Read current database schema from information_schema or equivalent.

    Each provider implements this to query their system tables.
    """

    def __init__(self, db_connection, logger=None):
        """
        Initialize introspector.

        Args:
            db_connection: Database connection (Postgres, MySQL, SQLServer)
            logger: Optional logger instance
        """
        self.db = db_connection
        self.logger = logger

    @abstractmethod
    def get_tables(self, schema: str) -> List[str]:
        """
        Get list of table names in schema.

        Args:
            schema: Schema name (e.g., "public", "dbo")

        Returns:
            List of table names
        """
        pass

    @abstractmethod
    def get_columns(self, table_name: str, schema: str) -> List[ColumnDefinition]:
        """
        Get column definitions for a table.

        Args:
            table_name: Table name
            schema: Schema name

        Returns:
            List of column definitions with types, nullability, defaults, etc.
        """
        pass

    @abstractmethod
    def get_indexes(self, table_name: str, schema: str) -> List[IndexDefinition]:
        """
        Get index definitions for a table.

        Args:
            table_name: Table name
            schema: Schema name

        Returns:
            List of index definitions
        """
        pass

    @abstractmethod
    def table_exists(self, table_name: str, schema: str) -> bool:
        """
        Check if table exists.

        Args:
            table_name: Table name
            schema: Schema name

        Returns:
            True if table exists, False otherwise
        """
        pass

    def get_table_schema(self, table_name: str, schema: str) -> Optional[TableDefinition]:
        """
        Get complete table schema (default implementation).

        Args:
            table_name: Table name
            schema: Schema name

        Returns:
            TableDefinition or None if table doesn't exist
        """
        if not self.table_exists(table_name, schema):
            return None

        return TableDefinition(
            name=table_name,
            schema=schema,
            columns=self.get_columns(table_name, schema),
            indexes=self.get_indexes(table_name, schema),
        )


class SQLParserBase(ABC):
    """
    Parse CREATE TABLE SQL into structured definitions.

    Each provider implements this for provider-specific SQL syntax.
    """

    @abstractmethod
    def parse_create_table(self, sql: str) -> TableDefinition:
        """
        Parse CREATE TABLE statement into TableDefinition.

        Args:
            sql: Full CREATE TABLE SQL (may include indexes, triggers)

        Returns:
            TableDefinition with columns and indexes
        """
        pass

    @abstractmethod
    def parse_columns_from_sql(self, sql: str) -> List[ColumnDefinition]:
        """
        Extract column definitions from CREATE TABLE SQL.

        Args:
            sql: CREATE TABLE SQL

        Returns:
            List of column definitions
        """
        pass

    @abstractmethod
    def parse_indexes_from_sql(self, sql: str) -> List[IndexDefinition]:
        """
        Extract index definitions from SQL (CREATE INDEX statements).

        Args:
            sql: SQL containing CREATE INDEX statements

        Returns:
            List of index definitions
        """
        pass


class MigrationGeneratorBase(ABC):
    """
    Generate provider-specific DDL statements.

    Each provider implements this to generate ALTER TABLE, CREATE INDEX, etc.
    """

    @abstractmethod
    def generate_add_column(self, table_name: str, schema: str, column: ColumnDefinition) -> str:
        """
        Generate ALTER TABLE ADD COLUMN statement.

        Args:
            table_name: Table name
            schema: Schema name
            column: Column definition

        Returns:
            SQL statement (e.g., "ALTER TABLE schema.table ADD COLUMN ...")
        """
        pass

    @abstractmethod
    def generate_create_index(self, schema: str, index: IndexDefinition) -> str:
        """
        Generate CREATE INDEX statement.

        Args:
            schema: Schema name
            index: Index definition

        Returns:
            SQL statement (e.g., "CREATE INDEX idx_name ON schema.table ...")
        """
        pass

    @abstractmethod
    def generate_create_table(self, table: TableDefinition) -> str:
        """
        Generate CREATE TABLE statement.

        Args:
            table: Complete table definition

        Returns:
            SQL statement
        """
        pass

    @abstractmethod
    def generate_drop_index(self, schema: str, index: IndexDefinition) -> str:
        """
        Generate DROP INDEX statement.

        Args:
            schema: Schema name
            index: Index definition

        Returns:
            SQL statement (e.g., "DROP INDEX schema.idx_name;")
        """
        pass

    @abstractmethod
    def generate_drop_column(self, table_name: str, schema: str, column: ColumnDefinition) -> str:
        """
        Generate ALTER TABLE DROP COLUMN statement.

        Args:
            table_name: Table name
            schema: Schema name
            column: Column definition

        Returns:
            SQL statement (e.g., "ALTER TABLE schema.table DROP COLUMN col_name;")
        """
        pass

    @abstractmethod
    def generate_alter_column(self, table_name: str, schema: str, column: ColumnDefinition) -> str:
        """
        Generate ALTER TABLE ALTER COLUMN statement.

        Args:
            table_name: Table name
            schema: Schema name
            column: New column definition

        Returns:
            SQL statement (e.g., "ALTER TABLE schema.table ALTER COLUMN ...")
        """
        pass

    @abstractmethod
    def wrap_in_transaction(self, statements: List[str]) -> str:
        """
        Wrap multiple statements in a transaction.

        Args:
            statements: List of SQL statements

        Returns:
            Transaction-wrapped SQL (e.g., "BEGIN; ... COMMIT;")
        """
        pass


class SchemaDifferBase:
    """
    Compute differences between desired and current schema.

    Mostly provider-agnostic (can be overridden if needed).

    Uses SchemaNormalizer for consistent comparison across all schema elements.
    """

    def __init__(self, normalizer=None, logger=None):
        """
        Initialize schema differ.

        Args:
            normalizer: SchemaNormalizer instance for consistent comparison
            logger: Optional logger instance
        """
        from .normalizer import SchemaNormalizer

        self.normalizer = normalizer or SchemaNormalizer()
        self.logger = logger

    def _columns_equal(self, col1: ColumnDefinition, col2: ColumnDefinition) -> bool:
        """
        Deep comparison of column definitions using normalization.

        Normalizes both columns before comparison to eliminate cosmetic differences.
        Compares all properties: type, nullable, default, max_length, precision, scale.

        Args:
            col1: First column definition
            col2: Second column definition

        Returns:
            True if columns are identical after normalization, False if any property differs
        """
        # Normalize both columns for comparison
        norm1 = self.normalizer.normalize_column(col1)
        norm2 = self.normalizer.normalize_column(col2)

        return (
            norm1.column_type == norm2.column_type
            and norm1.nullable == norm2.nullable
            and norm1.default == norm2.default
            and norm1.max_length == norm2.max_length
            and norm1.precision == norm2.precision
            and norm1.scale == norm2.scale
            and norm1.is_primary_key == norm2.is_primary_key
            and norm1.is_foreign_key == norm2.is_foreign_key
            and norm1.references == norm2.references
            and norm1.native_type == norm2.native_type  # Also compare native_type
        )

    def _indexes_equal(self, idx1: IndexDefinition, idx2: IndexDefinition) -> bool:
        """
        Deep comparison of index definitions using normalization.

        Normalizes both indexes before comparison to eliminate cosmetic differences.
        Compares all properties: columns, unique, index_type, where_clause.
        WHERE clauses are normalized using SQL AST parsing to handle PostgreSQL's
        pg_get_expr() adding extra parentheses.

        Args:
            idx1: First index definition
            idx2: Second index definition

        Returns:
            True if indexes are identical after normalization, False if any property differs
        """
        # Normalize both indexes for comparison
        norm1 = self.normalizer.normalize_index(idx1)
        norm2 = self.normalizer.normalize_index(idx2)

        # WHERE clause comparison: Both None (full index) or both normalized strings (partial index)
        # Empty strings are normalized to None to avoid false positives (None != "")
        return (
            norm1.columns == norm2.columns
            and norm1.unique == norm2.unique
            and norm1.index_type == norm2.index_type
            and norm1.where_clause == norm2.where_clause  # None == None for full indexes
        )

    def compute_changes(
        self, desired: TableDefinition, current: Optional[TableDefinition]
    ) -> List[SchemaChange]:
        """
        Compute schema changes needed to transform current → desired.

        Args:
            desired: Desired table schema from model
            current: Current table schema from database (None if doesn't exist)

        Returns:
            List of SchemaChange objects (additive and destructive)
        """
        from .models import ChangeType, SchemaChange

        changes = []

        # Table doesn't exist - create it
        if current is None:
            changes.append(
                SchemaChange(
                    change_type=ChangeType.CREATE_TABLE,
                    table_name=desired.name,
                    is_destructive=False,
                    sql="",  # Generator will create this
                    description=f"Create table {desired.schema}.{desired.name}",
                )
            )
            return changes

        # Compare columns
        current_cols = {col.name: col for col in current.columns}
        desired_cols = {col.name: col for col in desired.columns}

        # Missing columns (ADD - safe)
        for col_name, col_def in desired_cols.items():
            if col_name not in current_cols:
                changes.append(
                    SchemaChange(
                        change_type=ChangeType.ADD_COLUMN,
                        table_name=desired.name,
                        is_destructive=False,
                        sql="",
                        description=f"Add column {col_name}",
                        column=col_def,
                    )
                )

        # Extra columns (DROP - destructive)
        for col_name in current_cols:
            if col_name not in desired_cols:
                changes.append(
                    SchemaChange(
                        change_type=ChangeType.DROP_COLUMN,
                        table_name=desired.name,
                        is_destructive=True,
                        sql="",
                        description=f"Drop column {col_name} (DESTRUCTIVE)",
                        column=current_cols[col_name],
                    )
                )

        # Changed columns (ALTER - destructive, may cause data loss)
        for col_name in set(current_cols.keys()) & set(desired_cols.keys()):
            current_col = current_cols[col_name]
            desired_col = desired_cols[col_name]

            if not self._columns_equal(current_col, desired_col):
                # Build detailed change description
                differences = []
                if current_col.column_type != desired_col.column_type:
                    differences.append(
                        f"type: {current_col.column_type.value} → {desired_col.column_type.value}"
                    )
                if current_col.nullable != desired_col.nullable:
                    # SPECIAL HANDLING: nullable → NOT NULL change
                    if current_col.nullable and not desired_col.nullable:
                        # This is destructive because existing NULL values cannot be made NOT NULL
                        if desired_col.default is None:
                            # FAIL - cannot convert NULL values without a DEFAULT
                            raise ValueError(
                                f"Cannot alter column '{col_name}' from nullable to NOT NULL without DEFAULT value.\n"
                                f"Existing NULL values in table '{desired.name}' cannot be converted.\n\n"
                                f"Options:\n"
                                f"  1. Add DEFAULT value to the field definition:\n"
                                f'     {col_name}: <type> = Field(default="value")\n\n'
                                f"  2. Backfill NULL values manually, then re-run migration:\n"
                                f"     UPDATE {desired.schema}.{desired.name} SET {col_name} = 'value' WHERE {col_name} IS NULL;\n\n"
                                f"  3. Drop and recreate the column (DATA LOSS):\n"
                                f"     ALTER TABLE {desired.schema}.{desired.name} DROP COLUMN {col_name};"
                            )
                        # If we reach here, DEFAULT exists - will backfill
                        differences.append(
                            f"nullable: {current_col.nullable} → {desired_col.nullable} (will backfill with DEFAULT)"
                        )
                    else:
                        differences.append(
                            f"nullable: {current_col.nullable} → {desired_col.nullable}"
                        )

                if current_col.default != desired_col.default:
                    differences.append(f"default: {current_col.default} → {desired_col.default}")
                if current_col.max_length != desired_col.max_length:
                    differences.append(
                        f"max_length: {current_col.max_length} → {desired_col.max_length}"
                    )
                if current_col.precision != desired_col.precision:
                    differences.append(
                        f"precision: {current_col.precision} → {desired_col.precision}"
                    )
                if current_col.scale != desired_col.scale:
                    differences.append(f"scale: {current_col.scale} → {desired_col.scale}")

                change_desc = f"Alter column {col_name} ({', '.join(differences)}) - DESTRUCTIVE, may cause data loss"

                changes.append(
                    SchemaChange(
                        change_type=ChangeType.ALTER_COLUMN_TYPE,
                        table_name=desired.name,
                        is_destructive=True,
                        sql="",
                        description=change_desc,
                        column=desired_col,
                    )
                )

        # Compare indexes
        current_idxs = {idx.name: idx for idx in current.indexes}
        desired_idxs = {idx.name: idx for idx in desired.indexes}

        # Missing indexes (ADD - safe)
        for idx_name, idx_def in desired_idxs.items():
            if idx_name not in current_idxs:
                changes.append(
                    SchemaChange(
                        change_type=ChangeType.ADD_INDEX,
                        table_name=desired.name,
                        is_destructive=False,
                        sql="",
                        description=f"Add index {idx_name}",
                        index=idx_def,
                    )
                )

        # Extra indexes (DROP - destructive)
        for idx_name in current_idxs:
            if idx_name not in desired_idxs:
                changes.append(
                    SchemaChange(
                        change_type=ChangeType.DROP_INDEX,
                        table_name=desired.name,
                        is_destructive=True,
                        sql="",
                        description=f"Drop index {idx_name} (DESTRUCTIVE)",
                        index=current_idxs[idx_name],
                    )
                )

        # Changed indexes (DROP + CREATE - destructive)
        for idx_name in set(current_idxs.keys()) & set(desired_idxs.keys()):
            current_idx = current_idxs[idx_name]
            desired_idx = desired_idxs[idx_name]

            if not self._indexes_equal(current_idx, desired_idx):
                # Build detailed change description
                differences = []
                if current_idx.columns != desired_idx.columns:
                    differences.append(f"columns: {current_idx.columns} → {desired_idx.columns}")
                if current_idx.unique != desired_idx.unique:
                    differences.append(f"unique: {current_idx.unique} → {desired_idx.unique}")
                if current_idx.index_type != desired_idx.index_type:
                    differences.append(f"type: {current_idx.index_type} → {desired_idx.index_type}")
                if current_idx.where_clause != desired_idx.where_clause:
                    differences.append(
                        f"where: {current_idx.where_clause} → {desired_idx.where_clause}"
                    )

                # Need to drop and recreate index
                changes.append(
                    SchemaChange(
                        change_type=ChangeType.DROP_INDEX,
                        table_name=desired.name,
                        is_destructive=True,
                        sql="",
                        description=f"Drop index {idx_name} (changed: {', '.join(differences)}) - DESTRUCTIVE",
                        index=current_idx,
                    )
                )
                changes.append(
                    SchemaChange(
                        change_type=ChangeType.ADD_INDEX,
                        table_name=desired.name,
                        is_destructive=False,
                        sql="",
                        description=f"Recreate index {idx_name} with new definition",
                        index=desired_idx,
                    )
                )

        return changes
