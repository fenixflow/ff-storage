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
        index_pattern = r'CREATE\s+(UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s+ON\s+([a-zA-Z_][a-zA-Z0-9_]*\\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:USING\s+([a-zA-Z]+))?\s*\(([^)]+)\)(?:\s+WHERE\s+(.+?))?;'

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
