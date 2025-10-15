# Schema Sync Implementation Task

## Context

You are working in the **ff-storage** repository on branch `v1.0.0-schema-sync`.

This branch has already completed:
- ✅ Reorganization: Connection files moved to `connections/` subfolder
- ✅ Import updates: All imports fixed (`..sql` instead of `.sql`)
- ✅ Package structure: `connections/__init__.py` created with exports
- ✅ migrations.py: Deleted (being replaced by schema_sync system)

## Current State

```
ff-storage/src/ff_storage/db/
├── __init__.py              # Updated with connections imports
├── models.py                # Base model classes (existing)
├── sql.py                   # SQL base class (existing)
├── connections/             # ✅ COMPLETED - Connection implementations
│   ├── __init__.py          # ✅ Exports Postgres, MySQL, SQLServer
│   ├── postgres.py          # ✅ Moved and imports fixed
│   ├── mysql.py             # ✅ Moved and imports fixed
│   └── sqlserver.py         # ✅ Moved and imports fixed
└── schema_sync/             # ⚠️  TO BE CREATED - Schema synchronization
    ├── __init__.py
    ├── models.py
    ├── base.py
    ├── manager.py
    ├── postgres.py
    ├── mysql.py
    └── sqlserver.py
```

## Your Task

Implement a **Terraform-like schema synchronization system** with:
- Provider-agnostic design using abstract base classes
- Full PostgreSQL implementation
- MySQL/SQL Server stubs (NotImplementedError)
- Automatic schema sync from model definitions

---

## Implementation Plan

### Phase 1: Create Schema Sync Data Models

**File**: `src/ff_storage/db/schema_sync/models.py`

Create provider-agnostic data models:

```python
"""
Provider-agnostic schema data models.

These models represent database schema elements in a way that works
across PostgreSQL, MySQL, and SQL Server.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ColumnType(Enum):
    """Database-agnostic column types."""
    UUID = "uuid"
    STRING = "string"
    TEXT = "text"
    INTEGER = "integer"
    BIGINT = "bigint"
    BOOLEAN = "boolean"
    TIMESTAMP = "timestamp"
    TIMESTAMPTZ = "timestamptz"
    JSONB = "jsonb"
    ARRAY = "array"
    DECIMAL = "decimal"


class ChangeType(Enum):
    """Schema change types."""
    # Additive (safe - auto-apply)
    CREATE_TABLE = "create_table"
    ADD_COLUMN = "add_column"
    ADD_INDEX = "add_index"
    ADD_CONSTRAINT = "add_constraint"

    # Destructive (dangerous - require confirmation)
    DROP_TABLE = "drop_table"
    DROP_COLUMN = "drop_column"
    DROP_INDEX = "drop_index"
    ALTER_COLUMN_TYPE = "alter_column_type"
    DROP_CONSTRAINT = "drop_constraint"


@dataclass
class ColumnDefinition:
    """Database-agnostic column definition."""
    name: str
    column_type: ColumnType
    nullable: bool = True
    default: Optional[str] = None
    max_length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None
    is_primary_key: bool = False
    is_foreign_key: bool = False
    references: Optional[str] = None
    native_type: Optional[str] = None  # Provider-specific (e.g., "UUID", "VARCHAR(255)")


@dataclass
class IndexDefinition:
    """Database-agnostic index definition."""
    name: str
    table_name: str
    columns: List[str]
    unique: bool = False
    index_type: str = "btree"
    where_clause: Optional[str] = None


@dataclass
class TableDefinition:
    """Complete table schema."""
    name: str
    schema: str
    columns: List[ColumnDefinition] = field(default_factory=list)
    indexes: List[IndexDefinition] = field(default_factory=list)


@dataclass
class SchemaChange:
    """Represents a schema change to be applied."""
    change_type: ChangeType
    table_name: str
    is_destructive: bool
    sql: str
    description: str
    column: Optional[ColumnDefinition] = None
    index: Optional[IndexDefinition] = None
```

**Key Points**:
- Provider-agnostic types (ColumnType enum)
- Change classification (additive vs destructive)
- Native type tracking for provider-specific SQL generation

---

### Phase 2: Create Abstract Base Classes

**File**: `src/ff_storage/db/schema_sync/base.py`

Define interfaces that each database provider must implement:

```python
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
```

**Key Points**:
- Abstract methods force provider implementations
- Default `get_table_schema` combines columns + indexes
- Default `SchemaDiffer` handles common logic
- Clear separation of concerns

---

### Phase 3: Implement PostgreSQL Provider (FULL IMPLEMENTATION)

**File**: `src/ff_storage/db/schema_sync/postgres.py`

This is the **complete, production-ready implementation** for PostgreSQL:

#### 3.1 SchemaIntrospector

```python
"""
PostgreSQL implementation of schema sync system.

This module provides complete PostgreSQL support for:
- Schema introspection (reading information_schema)
- SQL parsing (parsing CREATE TABLE statements)
- Migration generation (generating ALTER TABLE, CREATE INDEX, etc.)
"""

import re
from typing import List, Optional

from .base import MigrationGeneratorBase, SQLParserBase, SchemaIntrospectorBase
from .models import ColumnDefinition, ColumnType, IndexDefinition, TableDefinition


class PostgresSchemaIntrospector(SchemaIntrospectorBase):
    """PostgreSQL-specific schema introspection using information_schema."""

    def get_tables(self, schema: str) -> List[str]:
        """Get list of table names in schema."""
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        results = self.db.read_query(query, (schema,), as_dict=False)
        return [row[0] for row in results] if results else []

    def get_columns(self, table_name: str, schema: str) -> List[ColumnDefinition]:
        """Get column definitions for a table."""
        query = """
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length,
                numeric_precision,
                numeric_scale,
                udt_name
            FROM information_schema.columns
            WHERE table_schema = %s
            AND table_name = %s
            ORDER BY ordinal_position
        """
        results = self.db.read_query(query, (schema, table_name), as_dict=False)

        columns = []
        for row in results:
            col_name, data_type, nullable, default, max_len, precision, scale, udt_name = row

            # Map PostgreSQL type to generic type
            column_type = self._map_postgres_type(data_type, udt_name)

            columns.append(ColumnDefinition(
                name=col_name,
                column_type=column_type,
                nullable=(nullable == 'YES'),
                default=default,
                max_length=max_len,
                precision=precision,
                scale=scale,
                native_type=udt_name or data_type
            ))

        return columns

    def get_indexes(self, table_name: str, schema: str) -> List[IndexDefinition]:
        """Get index definitions for a table."""
        query = """
            SELECT
                i.relname as index_name,
                ARRAY_AGG(a.attname ORDER BY a.attnum) as column_names,
                ix.indisunique as is_unique,
                am.amname as index_type
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            JOIN pg_am am ON i.relam = am.oid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = %s
            AND t.relname = %s
            AND t.relkind = 'r'
            GROUP BY i.relname, ix.indisunique, am.amname
            ORDER BY i.relname
        """
        results = self.db.read_query(query, (schema, table_name), as_dict=False)

        indexes = []
        for row in results:
            idx_name, col_names, is_unique, idx_type = row
            indexes.append(IndexDefinition(
                name=idx_name,
                table_name=table_name,
                columns=col_names if isinstance(col_names, list) else [col_names],
                unique=is_unique,
                index_type=idx_type
            ))

        return indexes

    def table_exists(self, table_name: str, schema: str) -> bool:
        """Check if table exists."""
        query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = %s
                AND table_name = %s
            )
        """
        result = self.db.read_query(query, (schema, table_name), as_dict=False)
        return result[0][0] if result else False

    def _map_postgres_type(self, data_type: str, udt_name: str) -> ColumnType:
        """Map PostgreSQL type to generic ColumnType."""
        # Use udt_name for more accurate type mapping
        type_str = (udt_name or data_type).lower()

        type_map = {
            'uuid': ColumnType.UUID,
            'character varying': ColumnType.STRING,
            'varchar': ColumnType.STRING,
            'text': ColumnType.TEXT,
            'integer': ColumnType.INTEGER,
            'int4': ColumnType.INTEGER,
            'bigint': ColumnType.BIGINT,
            'int8': ColumnType.BIGINT,
            'boolean': ColumnType.BOOLEAN,
            'bool': ColumnType.BOOLEAN,
            'timestamp without time zone': ColumnType.TIMESTAMP,
            'timestamp': ColumnType.TIMESTAMP,
            'timestamp with time zone': ColumnType.TIMESTAMPTZ,
            'timestamptz': ColumnType.TIMESTAMPTZ,
            'jsonb': ColumnType.JSONB,
            'numeric': ColumnType.DECIMAL,
            'decimal': ColumnType.DECIMAL,
        }

        # Check for array types
        if type_str.endswith('[]') or data_type == 'ARRAY':
            return ColumnType.ARRAY

        return type_map.get(type_str, ColumnType.STRING)
```

#### 3.2 SQL Parser

```python
class PostgresSQLParser(SQLParserBase):
    """Parse PostgreSQL CREATE TABLE statements."""

    def parse_create_table(self, sql: str) -> TableDefinition:
        """Parse CREATE TABLE statement into TableDefinition."""
        # Extract schema and table name
        table_match = re.search(
            r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*\.)?([a-zA-Z_][a-zA-Z0-9_]*)',
            sql,
            re.IGNORECASE
        )

        if not table_match:
            raise ValueError(f"Could not parse table name from SQL: {sql[:100]}")

        schema_part = table_match.group(1)
        table_name = table_match.group(2)
        schema = schema_part.rstrip('.') if schema_part else 'public'

        # Parse columns and indexes
        columns = self.parse_columns_from_sql(sql)
        indexes = self.parse_indexes_from_sql(sql)

        return TableDefinition(
            name=table_name,
            schema=schema,
            columns=columns,
            indexes=indexes
        )

    def parse_columns_from_sql(self, sql: str) -> List[ColumnDefinition]:
        """Extract column definitions from CREATE TABLE SQL."""
        # Extract the content inside CREATE TABLE (...)
        table_match = re.search(r'CREATE\s+TABLE[^(]+\((.*?)\);', sql, re.IGNORECASE | re.DOTALL)
        if not table_match:
            return []

        table_content = table_match.group(1)

        columns = []
        # Split by lines, look for column definitions
        for line in table_content.split('\n'):
            line = line.strip()

            # Skip comments, constraints, empty lines
            if not line or line.startswith('--') or line.upper().startswith(('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE', 'CHECK', 'CONSTRAINT')):
                continue

            # Parse column definition: column_name TYPE [NULL/NOT NULL] [DEFAULT ...]
            col_match = re.match(
                r'([a-zA-Z_][a-zA-Z0-9_]*)\s+([A-Z0-9_\(\)]+)(?:\s+(NOT\s+NULL|NULL))?(?:\s+DEFAULT\s+(.+?))?(?:,|$)',
                line,
                re.IGNORECASE
            )

            if col_match:
                col_name = col_match.group(1)
                col_type_str = col_match.group(2)
                nullable_str = col_match.group(3)
                default_str = col_match.group(4)

                # Map type string to ColumnType
                column_type = self._parse_column_type(col_type_str)
                nullable = not (nullable_str and 'NOT NULL' in nullable_str.upper())

                columns.append(ColumnDefinition(
                    name=col_name,
                    column_type=column_type,
                    nullable=nullable,
                    default=default_str.rstrip(',') if default_str else None,
                    native_type=col_type_str
                ))

        return columns

    def parse_indexes_from_sql(self, sql: str) -> List[IndexDefinition]:
        """Extract index definitions from SQL (CREATE INDEX statements)."""
        indexes = []

        # Find all CREATE INDEX statements
        index_pattern = r'CREATE\s+(UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s+ON\s+([a-zA-Z_][a-zA-Z0-9_]*\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:USING\s+([a-zA-Z]+))?\s*\(([^)]+)\)(?:\s+WHERE\s+(.+?))?;'

        for match in re.finditer(index_pattern, sql, re.IGNORECASE):
            is_unique = match.group(1) is not None
            index_name = match.group(2)
            table_name = match.group(4)
            index_type = match.group(5) or 'btree'
            columns_str = match.group(6)
            where_clause = match.group(7)

            # Parse column list
            columns = [col.strip() for col in columns_str.split(',')]

            indexes.append(IndexDefinition(
                name=index_name,
                table_name=table_name,
                columns=columns,
                unique=is_unique,
                index_type=index_type.lower(),
                where_clause=where_clause
            ))

        return indexes

    def _parse_column_type(self, type_str: str) -> ColumnType:
        """Parse PostgreSQL type string to ColumnType."""
        type_upper = type_str.upper()

        if type_upper == 'UUID':
            return ColumnType.UUID
        elif type_upper.startswith('VARCHAR') or type_upper.startswith('CHARACTER VARYING'):
            return ColumnType.STRING
        elif type_upper == 'TEXT':
            return ColumnType.TEXT
        elif type_upper in ('INTEGER', 'INT', 'INT4'):
            return ColumnType.INTEGER
        elif type_upper in ('BIGINT', 'INT8'):
            return ColumnType.BIGINT
        elif type_upper == 'BOOLEAN':
            return ColumnType.BOOLEAN
        elif 'TIMESTAMP WITH TIME ZONE' in type_upper or type_upper == 'TIMESTAMPTZ':
            return ColumnType.TIMESTAMPTZ
        elif 'TIMESTAMP' in type_upper:
            return ColumnType.TIMESTAMP
        elif type_upper == 'JSONB':
            return ColumnType.JSONB
        elif type_upper.endswith('[]'):
            return ColumnType.ARRAY
        elif type_upper in ('NUMERIC', 'DECIMAL'):
            return ColumnType.DECIMAL
        else:
            return ColumnType.STRING  # Default fallback
```

#### 3.3 Migration Generator

```python
class PostgresMigrationGenerator(MigrationGeneratorBase):
    """Generate PostgreSQL-specific migration SQL."""

    def generate_add_column(self, table_name: str, schema: str, column: ColumnDefinition) -> str:
        """Generate ALTER TABLE ADD COLUMN statement."""
        full_table = f"{schema}.{table_name}"
        nullable = "NULL" if column.nullable else "NOT NULL"
        default = f"DEFAULT {column.default}" if column.default else ""

        sql = f"ALTER TABLE {full_table} ADD COLUMN IF NOT EXISTS {column.name} {column.native_type}"

        if not column.nullable:
            sql += f" {nullable}"

        if default:
            sql += f" {default}"

        return sql + ";"

    def generate_create_index(self, schema: str, index: IndexDefinition) -> str:
        """Generate CREATE INDEX statement."""
        unique = "UNIQUE " if index.unique else ""
        columns = ", ".join(index.columns)
        full_table = f"{schema}.{index.table_name}"

        sql = f"CREATE {unique}INDEX IF NOT EXISTS {index.name} ON {full_table}"

        if index.index_type and index.index_type != "btree":
            sql += f" USING {index.index_type}"

        sql += f" ({columns})"

        if index.where_clause:
            sql += f" WHERE {index.where_clause}"

        return sql + ";"

    def generate_create_table(self, table: TableDefinition) -> str:
        """Generate CREATE TABLE statement."""
        full_table = f"{table.schema}.{table.name}"

        # Generate column definitions
        col_defs = []
        for col in table.columns:
            col_def = f"{col.name} {col.native_type}"

            if not col.nullable:
                col_def += " NOT NULL"

            if col.default:
                col_def += f" DEFAULT {col.default}"

            col_defs.append(col_def)

        sql = f"CREATE TABLE IF NOT EXISTS {full_table} (\n  "
        sql += ",\n  ".join(col_defs)
        sql += "\n);"

        return sql

    def wrap_in_transaction(self, statements: List[str]) -> str:
        """Wrap multiple statements in a transaction."""
        if not statements:
            return ""

        return "BEGIN;\n" + "\n".join(statements) + "\nCOMMIT;"
```

**Key Points**:
- Full PostgreSQL information_schema queries
- Regex-based SQL parsing for CREATE TABLE
- IF NOT EXISTS for safe migrations
- Transaction support for atomic changes

---

### Phase 4: Create MySQL/SQL Server Stubs

**File**: `src/ff_storage/db/schema_sync/mysql.py`

```python
"""
MySQL schema sync stubs (not yet implemented).

Contributions welcome! See postgres.py for reference implementation.
"""

from .base import MigrationGeneratorBase, SQLParserBase, SchemaIntrospectorBase


class MySQLSchemaIntrospector(SchemaIntrospectorBase):
    """MySQL schema introspector (stub)."""

    def get_tables(self, schema: str):
        raise NotImplementedError(
            "MySQL schema sync not yet implemented. "
            "See ff_storage.db.schema_sync.postgres.PostgresSchemaIntrospector for reference. "
            "Contributions welcome!"
        )

    def get_columns(self, table_name: str, schema: str):
        raise NotImplementedError("MySQL schema sync not yet implemented")

    def get_indexes(self, table_name: str, schema: str):
        raise NotImplementedError("MySQL schema sync not yet implemented")

    def table_exists(self, table_name: str, schema: str):
        raise NotImplementedError("MySQL schema sync not yet implemented")


class MySQLSQLParser(SQLParserBase):
    """MySQL SQL parser (stub)."""

    def parse_create_table(self, sql: str):
        raise NotImplementedError("MySQL schema sync not yet implemented")

    def parse_columns_from_sql(self, sql: str):
        raise NotImplementedError("MySQL schema sync not yet implemented")

    def parse_indexes_from_sql(self, sql: str):
        raise NotImplementedError("MySQL schema sync not yet implemented")


class MySQLMigrationGenerator(MigrationGeneratorBase):
    """MySQL migration generator (stub)."""

    def generate_add_column(self, table_name: str, schema: str, column):
        raise NotImplementedError("MySQL schema sync not yet implemented")

    def generate_create_index(self, schema: str, index):
        raise NotImplementedError("MySQL schema sync not yet implemented")

    def generate_create_table(self, table):
        raise NotImplementedError("MySQL schema sync not yet implemented")

    def wrap_in_transaction(self, statements):
        raise NotImplementedError("MySQL schema sync not yet implemented")
```

**File**: `src/ff_storage/db/schema_sync/sqlserver.py`

```python
"""
SQL Server schema sync stubs (not yet implemented).

Contributions welcome! See postgres.py for reference implementation.
"""

from .base import MigrationGeneratorBase, SQLParserBase, SchemaIntrospectorBase


class SQLServerSchemaIntrospector(SchemaIntrospectorBase):
    """SQL Server schema introspector (stub)."""

    def get_tables(self, schema: str):
        raise NotImplementedError(
            "SQL Server schema sync not yet implemented. "
            "See ff_storage.db.schema_sync.postgres.PostgresSchemaIntrospector for reference. "
            "Contributions welcome!"
        )

    def get_columns(self, table_name: str, schema: str):
        raise NotImplementedError("SQL Server schema sync not yet implemented")

    def get_indexes(self, table_name: str, schema: str):
        raise NotImplementedError("SQL Server schema sync not yet implemented")

    def table_exists(self, table_name: str, schema: str):
        raise NotImplementedError("SQL Server schema sync not yet implemented")


class SQLServerSQLParser(SQLParserBase):
    """SQL Server SQL parser (stub)."""

    def parse_create_table(self, sql: str):
        raise NotImplementedError("SQL Server schema sync not yet implemented")

    def parse_columns_from_sql(self, sql: str):
        raise NotImplementedError("SQL Server schema sync not yet implemented")

    def parse_indexes_from_sql(self, sql: str):
        raise NotImplementedError("SQL Server schema sync not yet implemented")


class SQLServerMigrationGenerator(MigrationGeneratorBase):
    """SQL Server migration generator (stub)."""

    def generate_add_column(self, table_name: str, schema: str, column):
        raise NotImplementedError("SQL Server schema sync not yet implemented")

    def generate_create_index(self, schema: str, index):
        raise NotImplementedError("SQL Server schema sync not yet implemented")

    def generate_create_table(self, table):
        raise NotImplementedError("SQL Server schema sync not yet implemented")

    def wrap_in_transaction(self, statements):
        raise NotImplementedError("SQL Server schema sync not yet implemented")
```

---

### Phase 5: Implement SchemaManager Orchestrator

**File**: `src/ff_storage/db/schema_sync/manager.py`

```python
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
        db_type = getattr(self.db, 'db_type', None)
        if db_type:
            return db_type

        # Fallback: check class name
        class_name = self.db.__class__.__name__.lower()
        if 'postgres' in class_name:
            return 'postgres'
        elif 'mysql' in class_name:
            return 'mysql'
        elif 'sqlserver' in class_name or 'mssql' in class_name:
            return 'sqlserver'

        raise ValueError(f"Could not detect database provider from connection: {type(self.db)}")

    def _create_introspector(self) -> SchemaIntrospectorBase:
        """Factory method for provider-specific introspector."""
        if self.provider == 'postgres':
            from .postgres import PostgresSchemaIntrospector
            return PostgresSchemaIntrospector(self.db, self.logger)
        elif self.provider == 'mysql':
            from .mysql import MySQLSchemaIntrospector
            return MySQLSchemaIntrospector(self.db, self.logger)
        elif self.provider == 'sqlserver':
            from .sqlserver import SQLServerSchemaIntrospector
            return SQLServerSchemaIntrospector(self.db, self.logger)
        else:
            raise ValueError(f"Unsupported database provider: {self.provider}")

    def _create_parser(self) -> SQLParserBase:
        """Factory method for provider-specific SQL parser."""
        if self.provider == 'postgres':
            from .postgres import PostgresSQLParser
            return PostgresSQLParser()
        elif self.provider == 'mysql':
            from .mysql import MySQLSQLParser
            return MySQLSQLParser()
        elif self.provider == 'sqlserver':
            from .sqlserver import SQLServerSQLParser
            return SQLServerSQLParser()
        else:
            raise ValueError(f"Unsupported database provider: {self.provider}")

    def _create_generator(self) -> MigrationGeneratorBase:
        """Factory method for provider-specific migration generator."""
        if self.provider == 'postgres':
            from .postgres import PostgresMigrationGenerator
            return PostgresMigrationGenerator()
        elif self.provider == 'mysql':
            from .mysql import MySQLMigrationGenerator
            return MySQLMigrationGenerator()
        elif self.provider == 'sqlserver':
            from .sqlserver import SQLServerMigrationGenerator
            return SQLServerMigrationGenerator()
        else:
            raise ValueError(f"Unsupported database provider: {self.provider}")

    def sync_schema(
        self,
        models: List[Type],
        allow_destructive: bool = False,
        dry_run: bool = False
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
                "dry_run": dry_run
            }
        )

        all_changes = []

        # Process each model
        for model_class in models:
            # Get desired state from model
            try:
                sql = model_class.get_create_table_sql()
                desired = self.parser.parse_create_table(sql)
            except Exception as e:
                self.logger.error(
                    f"Failed to parse SQL for model {model_class.__name__}",
                    extra={"error": str(e)}
                )
                continue

            # Get current state from database
            try:
                current = self.introspector.get_table_schema(
                    table_name=model_class.get_table_name(),
                    schema=model_class.__schema__
                )
            except Exception as e:
                self.logger.error(
                    f"Failed to introspect table {model_class.get_table_name()}",
                    extra={"error": str(e)}
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
                            column=change.column
                        )
                    elif change.change_type == ChangeType.ADD_INDEX:
                        change.sql = self.generator.generate_create_index(
                            schema=desired.schema,
                            index=change.index
                        )
                    elif change.change_type == ChangeType.CREATE_TABLE:
                        change.sql = self.generator.generate_create_table(desired)
                except Exception as e:
                    self.logger.error(
                        f"Failed to generate SQL for change: {change.description}",
                        extra={"error": str(e)}
                    )
                    continue

            all_changes.extend(changes)

        # Filter destructive changes
        safe_changes = [c for c in all_changes if not c.is_destructive]
        destructive_changes = [c for c in all_changes if c.is_destructive]

        if destructive_changes and not allow_destructive:
            self.logger.warning(
                "Skipping destructive changes (set allow_destructive=True to apply)",
                extra={
                    "count": len(destructive_changes),
                    "changes": [c.description for c in destructive_changes]
                }
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
            self.db.execute(transaction_sql)
            self.logger.info(
                f"Applied {len(statements)} schema changes successfully",
                extra={"changes": [c.description for c in changes_to_apply]}
            )
            return len(statements)
        except Exception as e:
            self.logger.error(
                "Schema sync failed",
                extra={"error": str(e)},
                exc_info=True
            )
            raise
```

---

### Phase 6: Create Package Exports

**File**: `src/ff_storage/db/schema_sync/__init__.py`

```python
"""
Schema synchronization system for ff-storage.

Provides Terraform-like schema management with automatic detection
of schema changes and safe migration generation.

Usage:
    from ff_storage.db import Postgres, SchemaManager

    db = Postgres(...)
    db.connect()

    manager = SchemaManager(db, logger=logger)
    changes = manager.sync_schema(
        models=get_all_models(),
        allow_destructive=False,
        dry_run=False
    )
"""

from .manager import SchemaManager
from .models import (
    ChangeType,
    ColumnDefinition,
    ColumnType,
    IndexDefinition,
    SchemaChange,
    TableDefinition,
)

__all__ = [
    # Main orchestrator
    "SchemaManager",
    # Data models
    "ColumnDefinition",
    "IndexDefinition",
    "TableDefinition",
    "SchemaChange",
    # Enums
    "ColumnType",
    "ChangeType",
]
```

**Update**: `src/ff_storage/db/__init__.py`

Add SchemaManager to exports:

```python
# Add to imports
from .schema_sync import SchemaManager

# Add to __all__
__all__ = [
    # ... existing exports ...
    # Schema Sync
    "SchemaManager",
]
```

---

### Phase 7: Update CHANGELOG and Version

**File**: `CHANGELOG.md`

Add at the top:

```markdown
## [1.0.0] - 2025-10-XX

### Added
- **Schema Sync System**: Terraform-like automatic schema synchronization
  - `SchemaManager`: Main orchestrator for schema sync
  - Provider-agnostic design with abstract base classes
  - Full PostgreSQL implementation (introspection, parsing, generation)
  - MySQL/SQL Server stubs for future implementation
  - Automatic detection of schema changes
  - Safe by default (destructive changes require explicit approval)
  - Dry-run mode for previewing changes
  - Transaction-wrapped migrations for atomicity

### Changed
- **BREAKING**: Reorganized `db` module structure
  - Moved connection classes to `db.connections/` subfolder
  - Updated import paths (users must update: `from ff_storage.db.postgres` → `from ff_storage.db.connections.postgres`)
  - Backward compatible imports available via `from ff_storage.db import Postgres`

### Removed
- **BREAKING**: Removed file-based migrations (`MigrationManager`)
  - Replaced by automatic schema sync from model definitions
  - Migration: Define schema in model `get_create_table_sql()` methods
  - Schema sync automatically applies changes on startup

### Migration Guide
For users upgrading from 0.x.x:

**Old way** (file-based migrations):
```python
from ff_storage.db import MigrationManager
manager = MigrationManager(db, "./migrations")
manager.migrate()
```

**New way** (schema sync):
```python
from ff_storage.db import SchemaManager
manager = SchemaManager(db, logger=logger)
manager.sync_schema(models=get_all_models(), dry_run=False)
```
```

**File**: `pyproject.toml`

Update version:

```toml
[project]
name = "ff-storage"
version = "1.0.0"
# ... rest of config
```

---

## Testing Instructions

After implementation, test with:

1. **Unit tests**: Test each component in isolation
2. **Integration test**: Test with real PostgreSQL database
3. **Real-world test**: Test with fenix-agents IXRDocument model

Example test:

```python
from ff_storage.db import Postgres, SchemaManager

# Connect to test database
db = Postgres(dbname="test_db", user="test", password="test", host="localhost", port=5432)
db.connect()

# Create manager
manager = SchemaManager(db)

# Test introspection
tables = manager.introspector.get_tables("public")
print(f"Tables: {tables}")

# Test with model classes
from models import get_all_models
changes = manager.sync_schema(
    models=get_all_models(),
    allow_destructive=False,
    dry_run=True  # Preview changes
)
```

---

## Success Criteria

✅ All files created with proper structure
✅ PostgreSQL implementation complete and tested
✅ MySQL/SQL Server stubs with helpful NotImplementedError
✅ SchemaManager auto-detects provider
✅ Dry-run mode works
✅ Transaction wrapping prevents partial failures
✅ Additive changes apply automatically
✅ Destructive changes blocked unless allowed
✅ Package exports updated
✅ Version bumped to 1.0.0
✅ CHANGELOG updated

---

## Notes

- **Current branch**: `v1.0.0-schema-sync` (already created)
- **Files already completed**: connections/ reorganization, migrations.py deletion
- **Your task**: Implement schema_sync/ package as specified above
- **Testing**: Test with fenix-agents repository after completion

Good luck! This will make ff-storage a truly professional, holistic database abstraction layer.