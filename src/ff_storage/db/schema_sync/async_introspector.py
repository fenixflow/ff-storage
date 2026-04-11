"""
Async PostgreSQL schema introspection using asyncpg.

This module provides an async version of PostgresSchemaIntrospector
that works with PostgresPool instead of sync Postgres connections.
"""

from typing import TYPE_CHECKING, List, Optional

from .models import ColumnDefinition, ColumnType, IndexDefinition, TableDefinition

if TYPE_CHECKING:
    from ..pool.postgres import PostgresPool


class AsyncPostgresSchemaIntrospector:
    """
    Async PostgreSQL schema introspection using asyncpg.

    This is the async equivalent of PostgresSchemaIntrospector,
    designed to work with PostgresPool instead of sync Postgres connections.

    Usage:
        introspector = AsyncPostgresSchemaIntrospector(db_pool)
        tables = await introspector.get_tables("public")
        columns = await introspector.get_columns("users", "public")
    """

    def __init__(self, db_pool: "PostgresPool", logger=None):
        """
        Initialize async introspector.

        Args:
            db_pool: PostgresPool instance for async database access
            logger: Optional logger instance
        """
        self.db_pool = db_pool
        self.logger = logger

    async def get_tables(self, schema: str) -> List[str]:
        """Get list of table names in schema."""
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = $1
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, schema)
        return [row["table_name"] for row in rows]

    async def get_columns(self, table_name: str, schema: str) -> List[ColumnDefinition]:
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
            WHERE table_schema = $1
            AND table_name = $2
            ORDER BY ordinal_position
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, schema, table_name)

        columns = []
        for row in rows:
            col_name = row["column_name"]
            data_type = row["data_type"]
            nullable = row["is_nullable"]
            default = row["column_default"]
            max_len = row["character_maximum_length"]
            precision = row["numeric_precision"]
            scale = row["numeric_scale"]
            udt_name = row["udt_name"]

            # Map PostgreSQL type to generic type
            column_type = self._map_postgres_type(data_type, udt_name)

            # Normalize boolean defaults for consistent comparison
            if default and column_type == ColumnType.BOOLEAN:
                default_lower = default.lower().strip()
                if default_lower in ("false", "f", "0", "no"):
                    default = "FALSE"
                elif default_lower in ("true", "t", "1", "yes"):
                    default = "TRUE"

            # Determine native_type representation and precision handling
            native_type_raw = udt_name or data_type
            native_lower = native_type_raw.lower()

            # Normalize types and determine precision handling
            if native_lower in ("float8", "double precision", "double"):
                native_type_normalized = "DOUBLE PRECISION"
                final_precision = None
                final_scale = None
            elif native_lower in ("float4", "real"):
                native_type_normalized = "REAL"
                final_precision = None
                final_scale = None
            elif native_lower.startswith("_") or data_type.upper() == "ARRAY":
                # Array type: udt_name is like "_text", "_int4", etc.
                if native_lower.startswith("_"):
                    element_type = native_lower[1:]
                    element_display = {
                        "text": "TEXT",
                        "int4": "INTEGER",
                        "int8": "BIGINT",
                        "varchar": "VARCHAR",
                        "uuid": "UUID",
                    }.get(element_type, element_type.upper())
                    native_type_normalized = f"{element_display}[]"
                else:
                    native_type_normalized = "TEXT[]"
                final_precision = None
                final_scale = None
            elif native_lower == "timestamptz":
                native_type_normalized = "TIMESTAMPTZ"
                final_precision = None
                final_scale = None
            else:
                native_type_normalized = native_type_raw.upper()
                # Only NUMERIC/DECIMAL have user-specified precision/scale
                if column_type == ColumnType.DECIMAL:
                    final_precision = precision
                    final_scale = scale
                else:
                    final_precision = None
                    final_scale = None

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

        # Enrich columns with constraint information (primary keys, foreign keys)
        constraints = await self.get_column_constraints(table_name, schema)
        for col in columns:
            if col.name in constraints:
                col_constraints = constraints[col.name]
                col.is_primary_key = col_constraints.get("is_primary_key", False)
                col.is_foreign_key = col_constraints.get("is_foreign_key", False)
                col.references = col_constraints.get("references")

        return columns

    async def get_column_constraints(self, table_name: str, schema: str) -> dict:
        """Get primary key and foreign key constraints for table columns.

        Returns a dict mapping column names to their constraint info:
        {
            "column_name": {
                "is_primary_key": bool,
                "is_foreign_key": bool,
                "references": "schema.table(column)" or None
            }
        }
        """
        # Query for primary key columns
        pk_query = """
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            JOIN pg_class c ON c.oid = i.indrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE i.indisprimary
              AND n.nspname = $1
              AND c.relname = $2
        """
        async with self.db_pool.acquire() as conn:
            pk_results = await conn.fetch(pk_query, schema, table_name)
        pk_columns = {row["attname"] for row in pk_results}

        # Query for foreign key columns with their references
        fk_query = """
            SELECT
                kcu.column_name,
                ccu.table_schema || '.' || ccu.table_name || '(' || ccu.column_name || ')' as references
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
                AND tc.table_schema = ccu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = $1
              AND tc.table_name = $2
        """
        async with self.db_pool.acquire() as conn:
            fk_results = await conn.fetch(fk_query, schema, table_name)
        fk_map = {row["column_name"]: row["references"] for row in fk_results}

        # Build combined constraints dict
        constraints = {}
        all_columns = pk_columns | set(fk_map.keys())

        for col_name in all_columns:
            constraints[col_name] = {
                "is_primary_key": col_name in pk_columns,
                "is_foreign_key": col_name in fk_map,
                "references": fk_map.get(col_name),
            }

        return constraints

    async def get_indexes(self, table_name: str, schema: str) -> List[IndexDefinition]:
        """Get index definitions for a table.

        Note: This excludes indexes that back constraints (PRIMARY KEY, UNIQUE, EXCLUDE)
        as these are managed implicitly through their constraints.
        """
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
            LEFT JOIN pg_constraint co ON co.conindid = ix.indexrelid
            WHERE n.nspname = $1
            AND t.relname = $2
            AND t.relkind = 'r'
            AND NOT ix.indisprimary  -- Exclude primary key indexes
            AND co.conindid IS NULL  -- Exclude indexes backing constraints
            GROUP BY i.relname, ix.indisunique, am.amname, ix.indpred, ix.indrelid
            ORDER BY i.relname
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, schema, table_name)

        indexes = []
        for row in rows:
            idx_name = row["index_name"]
            col_names = row["column_names"]
            is_unique = row["is_unique"]
            idx_type = row["index_type"]
            where_clause = row["where_clause"]

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

    async def table_exists(self, table_name: str, schema: str) -> bool:
        """Check if table exists."""
        query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = $1
                AND table_name = $2
            )
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, schema, table_name)
        return row[0] if row else False

    async def get_table_schema(self, table_name: str, schema: str) -> Optional[TableDefinition]:
        """
        Get complete table schema.

        Args:
            table_name: Table name
            schema: Schema name

        Returns:
            TableDefinition or None if table doesn't exist
        """
        if not await self.table_exists(table_name, schema):
            return None

        columns = await self.get_columns(table_name, schema)
        indexes = await self.get_indexes(table_name, schema)

        return TableDefinition(
            name=table_name,
            schema=schema,
            columns=columns,
            indexes=indexes,
        )

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
            "time": ColumnType.TIME,
            "time without time zone": ColumnType.TIME,
            "interval": ColumnType.INTERVAL,
            "bytea": ColumnType.BINARY,
            "jsonb": ColumnType.JSONB,
            "numeric": ColumnType.DECIMAL,
            "decimal": ColumnType.DECIMAL,
            # Float types
            "float8": ColumnType.DECIMAL,
            "double precision": ColumnType.DECIMAL,
            "float4": ColumnType.DECIMAL,
            "real": ColumnType.DECIMAL,
            "double": ColumnType.DECIMAL,
        }

        # Check for array types
        if type_str.endswith("[]") or data_type.upper() == "ARRAY" or type_str.startswith("_"):
            return ColumnType.ARRAY

        return type_map.get(type_str, ColumnType.STRING)
