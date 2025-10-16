"""
MySQL schema sync stubs (not yet implemented).

Contributions welcome! See postgres.py for reference implementation.
"""

from .base import MigrationGeneratorBase, SchemaIntrospectorBase, SQLParserBase


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
