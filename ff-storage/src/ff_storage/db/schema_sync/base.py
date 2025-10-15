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
            indexes=self.get_indexes(table_name, schema)
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
    """

    def __init__(self, logger=None):
        self.logger = logger

    def compute_changes(
        self,
        desired: TableDefinition,
        current: Optional[TableDefinition]
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
            changes.append(SchemaChange(
                change_type=ChangeType.CREATE_TABLE,
                table_name=desired.name,
                is_destructive=False,
                sql="",  # Generator will create this
                description=f"Create table {desired.schema}.{desired.name}"
            ))
            return changes

        # Compare columns
        current_cols = {col.name: col for col in current.columns}
        desired_cols = {col.name: col for col in desired.columns}

        # Missing columns (ADD - safe)
        for col_name, col_def in desired_cols.items():
            if col_name not in current_cols:
                changes.append(SchemaChange(
                    change_type=ChangeType.ADD_COLUMN,
                    table_name=desired.name,
                    is_destructive=False,
                    sql="",
                    description=f"Add column {col_name}",
                    column=col_def
                ))

        # Extra columns (DROP - destructive)
        for col_name in current_cols:
            if col_name not in desired_cols:
                changes.append(SchemaChange(
                    change_type=ChangeType.DROP_COLUMN,
                    table_name=desired.name,
                    is_destructive=True,
                    sql="",
                    description=f"Drop column {col_name} (DESTRUCTIVE)",
                    column=current_cols[col_name]
                ))

        # Compare indexes
        current_idxs = {idx.name: idx for idx in current.indexes}
        desired_idxs = {idx.name: idx for idx in desired.indexes}

        # Missing indexes (ADD - safe)
        for idx_name, idx_def in desired_idxs.items():
            if idx_name not in current_idxs:
                changes.append(SchemaChange(
                    change_type=ChangeType.ADD_INDEX,
                    table_name=desired.name,
                    is_destructive=False,
                    sql="",
                    description=f"Add index {idx_name}",
                    index=idx_def
                ))

        return changes
