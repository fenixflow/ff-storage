"""
SQL Server schema sync stubs (not yet implemented).

Contributions welcome! See postgres.py for reference implementation.
"""

from .base import MigrationGeneratorBase, SchemaIntrospectorBase, SQLParserBase


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
