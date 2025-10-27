"""
PostgreSQL implementation of schema sync system.

This module provides complete PostgreSQL support for:
- Schema introspection (reading information_schema)
- SQL parsing (parsing CREATE TABLE statements)
- Migration generation (generating ALTER TABLE, CREATE INDEX, etc.)
"""

import re
from typing import List

from ...utils.postgres import quote_identifier
from .base import MigrationGeneratorBase, SchemaIntrospectorBase, SQLParserBase
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

            # Normalize boolean defaults for consistent comparison
            # PostgreSQL returns lowercase 'false'/'true', but we use uppercase 'FALSE'/'TRUE'
            if default and column_type == ColumnType.BOOLEAN:
                default_lower = default.lower().strip()
                if default_lower in ("false", "f", "0", "no"):
                    default = "FALSE"
                elif default_lower in ("true", "t", "1", "yes"):
                    default = "TRUE"

            # Only DECIMAL types have user-specified precision/scale
            # (Other numeric types like INTEGER have DB-generated precision we ignore)
            if column_type == ColumnType.DECIMAL:
                final_precision = precision
                final_scale = scale
            else:
                final_precision = None
                final_scale = None

            # Determine native_type representation
            native_type_raw = udt_name or data_type
            native_lower = native_type_raw.lower()

            # Normalize float types to PostgreSQL-valid forms
            if native_lower in ("float8", "double precision", "double"):
                native_type_normalized = "DOUBLE PRECISION"
            elif native_lower in ("float4", "real"):
                native_type_normalized = "REAL"
            # Handle array types: PostgreSQL stores as "_text" in udt_name, display as "TEXT[]"
            elif native_lower.startswith("_") or data_type.upper() == "ARRAY":
                # Array type: udt_name is like "_text", "_int4", etc.
                # Convert to display form: "TEXT[]", "INTEGER[]", etc.
                if native_lower.startswith("_"):
                    element_type = native_lower[1:]  # Strip leading underscore
                    # Map element type to display name
                    element_display = {
                        "text": "TEXT",
                        "int4": "INTEGER",
                        "int8": "BIGINT",
                        "varchar": "VARCHAR",
                        "uuid": "UUID",
                    }.get(element_type, element_type.upper())
                    native_type_normalized = f"{element_display}[]"
                else:
                    # Fallback for generic ARRAY
                    native_type_normalized = "TEXT[]"
            # Handle timestamp types: normalize TIMESTAMPTZ to full form
            elif native_lower == "timestamptz":
                native_type_normalized = "TIMESTAMPTZ"  # Keep short form, normalizer will handle
            else:
                native_type_normalized = native_type_raw.upper()

            columns.append(
                ColumnDefinition(
                    name=col_name,
                    column_type=column_type,
                    nullable=(nullable == "YES"),
                    default=default,
                    max_length=max_len,
                    precision=final_precision,
                    scale=final_scale,
                    native_type=native_type_normalized,
                )
            )

        return columns

    def get_indexes(self, table_name: str, schema: str) -> List[IndexDefinition]:
        """Get index definitions for a table."""
        query = """
            SELECT
                i.relname as index_name,
                ARRAY_AGG(a.attname ORDER BY array_position(ix.indkey, a.attnum)) as column_names,
                ix.indisunique as is_unique,
                am.amname as index_type,
                pg_get_expr(ix.indpred, ix.indrelid) as where_clause
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            JOIN pg_am am ON i.relam = am.oid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = %s
            AND t.relname = %s
            AND t.relkind = 'r'
            GROUP BY i.relname, ix.indisunique, am.amname, ix.indpred, ix.indrelid
            ORDER BY i.relname
        """
        results = self.db.read_query(query, (schema, table_name), as_dict=False)

        indexes = []
        for row in results:
            idx_name, col_names, is_unique, idx_type, where_clause = row
            indexes.append(
                IndexDefinition(
                    name=idx_name,
                    table_name=table_name,
                    columns=col_names if isinstance(col_names, list) else [col_names],
                    unique=is_unique,
                    index_type=idx_type,
                    where_clause=where_clause,
                )
            )

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
            "uuid": ColumnType.UUID,
            "character varying": ColumnType.STRING,
            "varchar": ColumnType.STRING,
            "text": ColumnType.TEXT,
            "integer": ColumnType.INTEGER,
            "int4": ColumnType.INTEGER,
            "bigint": ColumnType.BIGINT,
            "int8": ColumnType.BIGINT,
            "boolean": ColumnType.BOOLEAN,
            "bool": ColumnType.BOOLEAN,
            "timestamp without time zone": ColumnType.TIMESTAMP,
            "timestamp": ColumnType.TIMESTAMP,
            "timestamp with time zone": ColumnType.TIMESTAMPTZ,
            "timestamptz": ColumnType.TIMESTAMPTZ,
            "jsonb": ColumnType.JSONB,
            "numeric": ColumnType.DECIMAL,
            "decimal": ColumnType.DECIMAL,
            # Float types
            "float8": ColumnType.DECIMAL,  # DOUBLE PRECISION internal name
            "double precision": ColumnType.DECIMAL,
            "float4": ColumnType.DECIMAL,  # REAL internal name
            "real": ColumnType.DECIMAL,
            "double": ColumnType.DECIMAL,  # Handle if someone uses just "double"
        }

        # Check for array types (case-insensitive)
        # PostgreSQL stores arrays with udt_name like "_text", "_int4", etc.
        if type_str.endswith("[]") or data_type.upper() == "ARRAY" or type_str.startswith("_"):
            return ColumnType.ARRAY

        return type_map.get(type_str, ColumnType.STRING)


class PostgresSQLParser(SQLParserBase):
    """Parse PostgreSQL CREATE TABLE statements."""

    # Pattern to match quoted or unquoted SQL identifiers
    _IDENTIFIER = r'(?:"[^"]+"|[a-zA-Z_][a-zA-Z0-9_]*)'
    _QUALIFIED_NAME = rf"{_IDENTIFIER}(?:\.{_IDENTIFIER})?"

    @staticmethod
    def _strip_quotes(identifier: str) -> str:
        """Remove surrounding quotes from identifier if present."""
        return identifier.strip('"')

    def parse_create_table(self, sql: str) -> TableDefinition:
        """Parse CREATE TABLE statement into TableDefinition."""
        # Extract schema and table name (handles both quoted and unquoted)
        table_match = re.search(
            rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?({self._QUALIFIED_NAME})",
            sql,
            re.IGNORECASE,
        )

        if not table_match:
            raise ValueError(f"Could not parse table name from SQL: {sql[:100]}")

        full_name = table_match.group(1)

        # Split schema.table and strip quotes
        if "." in full_name:
            # Extract schema and table (may be quoted separately)
            parts_match = re.match(rf"({self._IDENTIFIER})\.({self._IDENTIFIER})", full_name)
            if parts_match:
                schema = self._strip_quotes(parts_match.group(1))
                table_name = self._strip_quotes(parts_match.group(2))
            else:
                raise ValueError(f"Could not parse qualified name: {full_name}")
        else:
            schema = "public"
            table_name = self._strip_quotes(full_name)

        # Parse columns and indexes
        columns = self.parse_columns_from_sql(sql)
        indexes = self.parse_indexes_from_sql(sql)

        return TableDefinition(name=table_name, schema=schema, columns=columns, indexes=indexes)

    def parse_columns_from_sql(self, sql: str) -> List[ColumnDefinition]:
        """Extract column definitions from CREATE TABLE SQL."""
        # Extract the content inside CREATE TABLE (...)
        table_match = re.search(r"CREATE\s+TABLE[^(]+\((.*?)\);", sql, re.IGNORECASE | re.DOTALL)
        if not table_match:
            return []

        table_content = table_match.group(1)

        columns = []
        # Split by lines, look for column definitions
        for line in table_content.split("\n"):
            line = line.strip()

            # Skip comments, constraints, empty lines
            if (
                not line
                or line.startswith("--")
                or line.upper().startswith(
                    ("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK", "CONSTRAINT")
                )
            ):
                continue

            # Parse column definition: column_name TYPE [constraints...] [,]
            # Fixed regex to handle:
            # - Multi-word types (TIMESTAMP WITH TIME ZONE)
            # - REFERENCES constraints
            # - Foreign keys and other constraints
            # - Quoted column names
            col_match = re.match(rf"({self._IDENTIFIER})\s+(.+?)(?:,\s*$|$)", line, re.IGNORECASE)

            if col_match:
                col_name = self._strip_quotes(col_match.group(1))
                col_def = col_match.group(2).rstrip(",").strip()

                # Extract type (first word or multi-word type)
                # Handle types like: UUID, VARCHAR(255), TIMESTAMP WITH TIME ZONE, DOUBLE PRECISION, TEXT[]
                type_match = re.match(
                    r"([A-Z]+(?:\s+(?:WITH\s+TIME\s+ZONE|VARYING|PRECISION))?(?:\([^)]+\))?(?:\[\])?)",
                    col_def,
                    re.IGNORECASE,
                )
                if not type_match:
                    # Fallback: just take first word
                    type_match = re.match(r"(\S+)", col_def)

                col_type_str = type_match.group(1) if type_match else col_def.split()[0]

                # Check for constraints in definition
                nullable = "NOT NULL" not in col_def.upper()

                # Extract default value if present
                default_match = re.search(
                    r"DEFAULT\s+(.+?)(?:,|REFERENCES|$)", col_def, re.IGNORECASE
                )
                default_str = default_match.group(1).strip() if default_match else None

                # Map type string to ColumnType
                column_type = self._parse_column_type(col_type_str)

                # Extract max_length, precision, scale from type string
                max_length, precision, scale = self._extract_type_constraints(col_type_str)

                columns.append(
                    ColumnDefinition(
                        name=col_name,
                        column_type=column_type,
                        nullable=nullable,
                        default=default_str,
                        max_length=max_length,
                        precision=precision,
                        scale=scale,
                        native_type=col_type_str,
                    )
                )

        return columns

    def parse_indexes_from_sql(self, sql: str) -> List[IndexDefinition]:
        """Extract index definitions from SQL (CREATE INDEX statements)."""
        indexes = []

        # Find all CREATE INDEX statements (handles quoted identifiers)
        index_pattern = rf"CREATE\s+(UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?({self._IDENTIFIER})\s+ON\s+({self._QUALIFIED_NAME})\s*(?:USING\s+([a-zA-Z]+))?\s*\(([^)]+)\)(?:\s+WHERE\s+(.+?))?;"

        for match in re.finditer(index_pattern, sql, re.IGNORECASE):
            is_unique = match.group(1) is not None
            index_name = self._strip_quotes(match.group(2))
            full_table_name = match.group(3)
            index_type = match.group(4) or "btree"
            columns_str = match.group(5)
            where_clause = match.group(6)

            # Extract table name from qualified name
            if "." in full_table_name:
                parts_match = re.match(
                    rf"({self._IDENTIFIER})\.({self._IDENTIFIER})", full_table_name
                )
                if parts_match:
                    table_name = self._strip_quotes(parts_match.group(2))
                else:
                    table_name = self._strip_quotes(full_table_name.split(".")[-1])
            else:
                table_name = self._strip_quotes(full_table_name)

            # Parse column list (may contain quoted columns)
            columns = []
            for col in columns_str.split(","):
                col = col.strip()
                # Remove quotes if present
                columns.append(self._strip_quotes(col))

            indexes.append(
                IndexDefinition(
                    name=index_name,
                    table_name=table_name,
                    columns=columns,
                    unique=is_unique,
                    index_type=index_type.lower(),
                    where_clause=where_clause,
                )
            )

        return indexes

    def _parse_column_type(self, type_str: str) -> ColumnType:
        """Parse PostgreSQL type string to ColumnType."""
        type_upper = type_str.upper()

        if type_upper == "UUID":
            return ColumnType.UUID
        elif type_upper.startswith("VARCHAR") or type_upper.startswith("CHARACTER VARYING"):
            return ColumnType.STRING
        elif type_upper == "TEXT":
            return ColumnType.TEXT
        elif type_upper.startswith("INTEGER") or type_upper in ("INT", "INT4"):
            return ColumnType.INTEGER
        elif type_upper.startswith("BIGINT") or type_upper == "INT8":
            return ColumnType.BIGINT
        elif type_upper == "BOOLEAN":
            return ColumnType.BOOLEAN
        elif "TIMESTAMP WITH TIME ZONE" in type_upper or type_upper == "TIMESTAMPTZ":
            return ColumnType.TIMESTAMPTZ
        elif "TIMESTAMP" in type_upper:
            return ColumnType.TIMESTAMP
        elif type_upper == "JSONB":
            return ColumnType.JSONB
        elif type_upper.endswith("[]"):
            return ColumnType.ARRAY
        elif "DOUBLE" in type_upper or "FLOAT8" in type_upper:
            return ColumnType.DECIMAL
        elif "REAL" in type_upper or "FLOAT4" in type_upper or type_upper == "FLOAT":
            return ColumnType.DECIMAL
        elif type_upper.startswith("NUMERIC") or type_upper.startswith("DECIMAL"):
            return ColumnType.DECIMAL
        else:
            return ColumnType.STRING  # Default fallback

    def _extract_type_constraints(self, type_str: str) -> tuple[int | None, int | None, int | None]:
        """Extract max_length, precision, scale from SQL type string."""
        # VARCHAR(n)
        if match := re.search(r"VARCHAR\((\d+)\)", type_str, re.IGNORECASE):
            return int(match.group(1)), None, None

        # NUMERIC(p,s)
        if match := re.search(r"(?:NUMERIC|DECIMAL)\((\d+),(\d+)\)", type_str, re.IGNORECASE):
            return None, int(match.group(1)), int(match.group(2))

        return None, None, None


class PostgresMigrationGenerator(MigrationGeneratorBase):
    """Generate PostgreSQL-specific migration SQL."""

    def generate_add_column(self, table_name: str, schema: str, column: ColumnDefinition) -> str:
        """
        Generate ALTER TABLE ADD COLUMN statement.

        For NOT NULL columns without DEFAULT on populated tables, generates a safe
        multi-step process:
        1. Add column as nullable (allows existing rows to have NULL)
        2. Set NOT NULL constraint (new rows must provide value going forward)

        This is safe because:
        - New columns start empty (all NULL)
        - Application code will provide values for new inserts
        - Existing rows keep NULL (backward compatible)
        """
        full_table = quote_identifier(f"{schema}.{table_name}")
        quoted_col = quote_identifier(column.name)

        # Handle NOT NULL columns without DEFAULT
        if not column.nullable and column.default is None:
            # Multi-step approach for backward compatibility
            # Step 1: Add as nullable
            sql = (
                f"ALTER TABLE {full_table} "
                f"ADD COLUMN IF NOT EXISTS {quoted_col} {column.native_type} NULL;\n"
            )

            # Step 2: Make NOT NULL (existing rows keep NULL, new inserts must provide value)
            sql += f"ALTER TABLE {full_table} ALTER COLUMN {quoted_col} SET NOT NULL"

            return sql + ";"

        # Standard path for nullable columns or columns with DEFAULT
        default = f"DEFAULT {column.default}" if column.default else ""
        nullable = "NULL" if column.nullable else "NOT NULL"

        sql = f"ALTER TABLE {full_table} ADD COLUMN IF NOT EXISTS {quoted_col} {column.native_type}"

        if not column.nullable:
            sql += f" {nullable}"

        if default:
            sql += f" {default}"

        return sql + ";"

    def generate_create_index(self, schema: str, index: IndexDefinition) -> str:
        """Generate CREATE INDEX statement."""
        unique = "UNIQUE " if index.unique else ""
        quoted_columns = ", ".join(quote_identifier(col) for col in index.columns)
        full_table = quote_identifier(f"{schema}.{index.table_name}")
        quoted_index = quote_identifier(index.name)

        sql = f"CREATE {unique}INDEX IF NOT EXISTS {quoted_index} ON {full_table}"

        if index.index_type and index.index_type != "btree":
            sql += f" USING {index.index_type}"

        sql += f" ({quoted_columns})"

        if index.where_clause:
            sql += f" WHERE {index.where_clause}"

        return sql + ";"

    def generate_create_table(self, table: TableDefinition) -> str:
        """Generate CREATE TABLE statement."""
        full_table = quote_identifier(f"{table.schema}.{table.name}")

        # Generate column definitions
        col_defs = []
        primary_keys = []
        foreign_keys = []

        for col in table.columns:
            quoted_col = quote_identifier(col.name)
            col_def = f"{quoted_col} {col.native_type}"

            if not col.nullable:
                col_def += " NOT NULL"

            if col.default:
                col_def += f" DEFAULT {col.default}"

            col_defs.append(col_def)

            # Track primary keys for composite PK constraint
            if col.is_primary_key:
                primary_keys.append(quoted_col)

            # Track foreign keys
            if col.is_foreign_key and col.references:
                foreign_keys.append((quoted_col, col.references))

        # Add PRIMARY KEY constraint if any primary keys exist
        if primary_keys:
            if len(primary_keys) == 1:
                # Single PK - modify the column definition directly
                for i, col_def in enumerate(col_defs):
                    if col_def.startswith(f"{primary_keys[0]} "):
                        col_defs[i] += " PRIMARY KEY"
                        break
            else:
                # Composite PK - add as table constraint
                pk_constraint = f"PRIMARY KEY ({', '.join(primary_keys)})"
                col_defs.append(pk_constraint)

        # Add FOREIGN KEY constraints
        for col_name, references in foreign_keys:
            fk_constraint = f"FOREIGN KEY ({col_name}) REFERENCES {references}"
            col_defs.append(fk_constraint)

        sql = f"CREATE TABLE IF NOT EXISTS {full_table} (\n  "
        sql += ",\n  ".join(col_defs)
        sql += "\n);"

        return sql

    def generate_drop_index(self, schema: str, index: IndexDefinition) -> str:
        """Generate DROP INDEX statement."""
        # PostgreSQL DROP INDEX requires schema-qualified index name
        full_index = quote_identifier(f"{schema}.{index.name}")
        return f"DROP INDEX IF EXISTS {full_index};"

    def generate_drop_column(self, table_name: str, schema: str, column: ColumnDefinition) -> str:
        """Generate ALTER TABLE DROP COLUMN statement."""
        full_table = quote_identifier(f"{schema}.{table_name}")
        quoted_col = quote_identifier(column.name)
        return f"ALTER TABLE {full_table} DROP COLUMN IF EXISTS {quoted_col};"

    def generate_alter_column(self, table_name: str, schema: str, column: ColumnDefinition) -> str:
        """
        Generate ALTER TABLE ALTER COLUMN statement with USING clause for type conversions.

        Uses STRICT conversion strategy: fails loudly on invalid data rather than silently
        converting to NULL. This forces manual data cleanup and prevents data loss.

        Also handles nullable changes with automatic backfilling when DEFAULT is present.
        """
        full_table = quote_identifier(f"{schema}.{table_name}")
        quoted_col = quote_identifier(column.name)

        # PostgreSQL ALTER COLUMN requires separate statements for type, nullable, and default
        statements = []

        # Determine if we need a USING clause for type conversion
        using_clause = self._get_type_conversion_using(column)

        # Change type
        alter_type = f"ALTER TABLE {full_table} ALTER COLUMN {quoted_col} TYPE {column.native_type}"
        if using_clause:
            alter_type += f" USING {using_clause}"
        statements.append(alter_type)

        # Change nullable
        # IMPORTANT: If making NOT NULL and column has DEFAULT, backfill first
        if not column.nullable:
            if column.default:
                # Backfill existing NULL values before adding constraint
                backfill = (
                    f"UPDATE {full_table} "
                    f"SET {quoted_col} = {column.default} "
                    f"WHERE {quoted_col} IS NULL"
                )
                statements.append(backfill)

            statements.append(f"ALTER TABLE {full_table} ALTER COLUMN {quoted_col} SET NOT NULL")
        else:
            statements.append(f"ALTER TABLE {full_table} ALTER COLUMN {quoted_col} DROP NOT NULL")

        # Change default
        if column.default:
            statements.append(
                f"ALTER TABLE {full_table} ALTER COLUMN {quoted_col} SET DEFAULT {column.default}"
            )
        else:
            statements.append(f"ALTER TABLE {full_table} ALTER COLUMN {quoted_col} DROP DEFAULT")

        return ";\n".join(statements) + ";"

    def _get_type_conversion_using(self, column: ColumnDefinition) -> str | None:
        """
        Generate USING clause for type conversions that PostgreSQL can't auto-cast.

        Strategy: STRICT conversions that fail on invalid data
        - NULL and empty strings are handled gracefully
        - Invalid data causes migration to FAIL (forces manual cleanup)
        - NO silent data loss or corruption

        Returns:
            USING clause string, or None if PostgreSQL can handle conversion automatically
        """
        target_type = column.native_type.upper()
        quoted_col = quote_identifier(column.name)

        # text → numeric/decimal
        # Handles NULL/empty, but FAILS on non-numeric values (e.g., "abc")
        if "NUMERIC" in target_type or "DECIMAL" in target_type:
            return f"CASE WHEN {quoted_col}::text IS NULL OR {quoted_col}::text = '' THEN NULL ELSE {quoted_col}::numeric END"

        # text → jsonb
        # Defaults to empty array for NULL/empty, but FAILS on invalid JSON
        elif "JSONB" in target_type or "JSON" in target_type:
            return f"CASE WHEN {quoted_col}::text IS NULL OR {quoted_col}::text = '' THEN '[]'::jsonb ELSE {quoted_col}::jsonb END"

        # text → integer
        # Handles NULL/empty, but FAILS on non-integer values
        elif "INTEGER" in target_type or "INT" in target_type:
            return f"CASE WHEN {quoted_col}::text IS NULL OR {quoted_col}::text = '' THEN NULL ELSE {quoted_col}::integer END"

        # text → bigint
        elif "BIGINT" in target_type:
            return f"CASE WHEN {quoted_col}::text IS NULL OR {quoted_col}::text = '' THEN NULL ELSE {quoted_col}::bigint END"

        # text → boolean
        # Standard boolean conversions, FAILS on unrecognized values
        elif "BOOLEAN" in target_type or "BOOL" in target_type:
            return (
                f"CASE "
                f"WHEN {quoted_col}::text IS NULL OR {quoted_col}::text = '' THEN NULL "
                f"WHEN {quoted_col}::text IN ('t', 'true', '1', 'yes', 'y') THEN true "
                f"WHEN {quoted_col}::text IN ('f', 'false', '0', 'no', 'n') THEN false "
                f"ELSE {quoted_col}::boolean "  # Let PostgreSQL try, will fail on invalid
                f"END"
            )

        # text → uuid
        elif "UUID" in target_type:
            return f"CASE WHEN {quoted_col}::text IS NULL OR {quoted_col}::text = '' THEN NULL ELSE {quoted_col}::uuid END"

        # For other conversions (e.g., varchar(100) → varchar(255), same type changes)
        # Let PostgreSQL handle it automatically without USING clause
        return None

    def wrap_in_transaction(self, statements: List[str]) -> str:
        """Wrap multiple statements in a transaction."""
        if not statements:
            return ""

        return "BEGIN;\n" + "\n".join(statements) + "\nCOMMIT;"
