"""
Tests for PostgreSQL float type normalization.

Regression tests for the bug where introspecting DOUBLE PRECISION columns
stored raw native types (e.g., "float8", "DOUBLE") which caused
"type does not exist" errors when generating DDL.
"""

from unittest.mock import Mock

from ff_storage.db.schema_sync.models import ColumnDefinition, ColumnType
from ff_storage.db.schema_sync.postgres import (
    PostgresMigrationGenerator,
    PostgresSchemaIntrospector,
    PostgresSQLParser,
)
from ff_storage.pydantic_support.type_mapping import map_pydantic_type_to_column_type
from pydantic import Field
from pydantic.fields import FieldInfo


class TestPydanticFloatMapping:
    """Test that Pydantic float fields map to valid PostgreSQL types."""

    def test_float_field_maps_to_double_precision(self):
        """Test that Python float type maps to DOUBLE PRECISION."""
        field_info = FieldInfo(annotation=float, default=None)
        column_type, native_type = map_pydantic_type_to_column_type(float, field_info)

        assert column_type == ColumnType.DECIMAL
        assert native_type == "DOUBLE PRECISION"

    def test_float_field_with_field_info(self):
        """Test float with Pydantic Field() metadata."""
        field_info = Field(default=0.0, description="A float field")
        column_type, native_type = map_pydantic_type_to_column_type(float, field_info)

        assert column_type == ColumnType.DECIMAL
        assert native_type == "DOUBLE PRECISION"


class TestIntrospectorFloatNormalization:
    """Test that schema introspection normalizes float types."""

    def test_float8_normalizes_to_double_precision(self):
        """Test that float8 (internal name) normalizes to DOUBLE PRECISION."""
        # Mock database connection
        mock_db = Mock()
        mock_db.read_query.return_value = [
            (
                "price",  # column_name
                "double precision",  # data_type
                "NO",  # is_nullable
                None,  # column_default
                None,  # character_maximum_length
                53,  # numeric_precision (ignored for float)
                None,  # numeric_scale
                "float8",  # udt_name
            )
        ]

        introspector = PostgresSchemaIntrospector(mock_db)
        columns = introspector.get_columns("products", "public")

        assert len(columns) == 1
        col = columns[0]
        assert col.name == "price"
        assert col.column_type == ColumnType.DECIMAL
        assert col.native_type == "DOUBLE PRECISION"  # Normalized!
        assert not col.nullable

    def test_float4_normalizes_to_real(self):
        """Test that float4 (internal name) normalizes to REAL."""
        mock_db = Mock()
        mock_db.read_query.return_value = [
            (
                "weight",
                "real",
                "YES",
                None,
                None,
                24,  # numeric_precision (ignored for float)
                None,
                "float4",  # udt_name
            )
        ]

        introspector = PostgresSchemaIntrospector(mock_db)
        columns = introspector.get_columns("items", "public")

        assert len(columns) == 1
        col = columns[0]
        assert col.name == "weight"
        assert col.column_type == ColumnType.DECIMAL
        assert col.native_type == "REAL"  # Normalized!
        assert col.nullable

    def test_double_precision_data_type_normalizes(self):
        """Test that 'double precision' data_type normalizes."""
        mock_db = Mock()
        mock_db.read_query.return_value = [
            (
                "ratio",
                "double precision",  # data_type
                "NO",
                None,
                None,
                53,
                None,
                "float8",
            )
        ]

        introspector = PostgresSchemaIntrospector(mock_db)
        columns = introspector.get_columns("stats", "public")

        assert len(columns) == 1
        col = columns[0]
        assert col.column_type == ColumnType.DECIMAL
        assert col.native_type == "DOUBLE PRECISION"


class TestSQLParserFloatTypes:
    """Test that SQL parser handles float types correctly."""

    def test_parse_double_precision_column(self):
        """Test parsing CREATE TABLE with DOUBLE PRECISION column."""
        sql = """
        CREATE TABLE public.products (
            id UUID PRIMARY KEY,
            price DOUBLE PRECISION NOT NULL,
            discount REAL
        );
        """

        parser = PostgresSQLParser()
        table_def = parser.parse_create_table(sql)

        assert table_def.name == "products"
        assert table_def.schema == "public"
        assert len(table_def.columns) == 3

        # Check DOUBLE PRECISION column
        price_col = next(c for c in table_def.columns if c.name == "price")
        assert price_col.column_type == ColumnType.DECIMAL
        assert price_col.native_type == "DOUBLE PRECISION"
        assert not price_col.nullable

        # Check REAL column
        discount_col = next(c for c in table_def.columns if c.name == "discount")
        assert discount_col.column_type == ColumnType.DECIMAL
        assert discount_col.native_type == "REAL"
        assert discount_col.nullable

    def test_parse_real_column(self):
        """Test parsing REAL type."""
        sql = """
        CREATE TABLE test (
            value REAL NOT NULL
        );
        """

        parser = PostgresSQLParser()
        columns = parser.parse_columns_from_sql(sql)

        assert len(columns) == 1
        col = columns[0]
        assert col.name == "value"
        assert col.column_type == ColumnType.DECIMAL
        assert col.native_type == "REAL"


class TestDDLGenerationWithFloats:
    """Test that DDL generation works with normalized float types."""

    def test_generate_add_column_double_precision(self):
        """Test ADD COLUMN with DOUBLE PRECISION."""
        generator = PostgresMigrationGenerator()

        column = ColumnDefinition(
            name="price",
            column_type=ColumnType.DECIMAL,
            nullable=False,
            native_type="DOUBLE PRECISION",
        )

        sql = generator.generate_add_column("products", "public", column)

        # Should generate valid SQL with multi-step approach for NOT NULL without DEFAULT
        assert "DOUBLE PRECISION" in sql
        assert '"public"."products"' in sql or "public.products" in sql
        assert "price" in sql

    def test_generate_add_column_real(self):
        """Test ADD COLUMN with REAL."""
        generator = PostgresMigrationGenerator()

        column = ColumnDefinition(
            name="weight",
            column_type=ColumnType.DECIMAL,
            nullable=True,
            native_type="REAL",
        )

        sql = generator.generate_add_column("items", "public", column)

        assert "REAL" in sql
        assert "weight" in sql

    def test_generate_create_table_with_float_columns(self):
        """Test CREATE TABLE with float columns."""
        from ff_storage.db.schema_sync.models import TableDefinition

        generator = PostgresMigrationGenerator()

        columns = [
            ColumnDefinition(
                name="id",
                column_type=ColumnType.UUID,
                nullable=False,
                native_type="UUID",
                is_primary_key=True,
            ),
            ColumnDefinition(
                name="price",
                column_type=ColumnType.DECIMAL,
                nullable=False,
                native_type="DOUBLE PRECISION",
            ),
            ColumnDefinition(
                name="weight",
                column_type=ColumnType.DECIMAL,
                nullable=True,
                native_type="REAL",
            ),
        ]

        table = TableDefinition(name="products", schema="public", columns=columns)

        sql = generator.generate_create_table(table)

        # Verify SQL contains correct types
        assert "DOUBLE PRECISION" in sql
        assert "REAL" in sql
        assert "UUID" in sql
        assert "CREATE TABLE" in sql
        assert "products" in sql


class TestTypeMapperFloatTypes:
    """Test the _map_postgres_type method handles float types."""

    def test_map_float8_type(self):
        """Test mapping float8 to ColumnType.DECIMAL."""
        mock_db = Mock()
        introspector = PostgresSchemaIntrospector(mock_db)

        column_type = introspector._map_postgres_type("double precision", "float8")
        assert column_type == ColumnType.DECIMAL

    def test_map_float4_type(self):
        """Test mapping float4 to ColumnType.DECIMAL."""
        mock_db = Mock()
        introspector = PostgresSchemaIntrospector(mock_db)

        column_type = introspector._map_postgres_type("real", "float4")
        assert column_type == ColumnType.DECIMAL

    def test_map_double_precision_type(self):
        """Test mapping 'double precision' string."""
        mock_db = Mock()
        introspector = PostgresSchemaIntrospector(mock_db)

        column_type = introspector._map_postgres_type("double precision", None)
        assert column_type == ColumnType.DECIMAL

    def test_map_real_type(self):
        """Test mapping 'real' string."""
        mock_db = Mock()
        introspector = PostgresSchemaIntrospector(mock_db)

        column_type = introspector._map_postgres_type("real", None)
        assert column_type == ColumnType.DECIMAL


class TestSQLParserColumnType:
    """Test _parse_column_type method handles float types."""

    def test_parse_double_precision_type(self):
        """Test parsing DOUBLE PRECISION type string."""
        parser = PostgresSQLParser()

        column_type = parser._parse_column_type("DOUBLE PRECISION")
        assert column_type == ColumnType.DECIMAL

    def test_parse_real_type(self):
        """Test parsing REAL type string."""
        parser = PostgresSQLParser()

        column_type = parser._parse_column_type("REAL")
        assert column_type == ColumnType.DECIMAL

    def test_parse_float8_type(self):
        """Test parsing FLOAT8 type string."""
        parser = PostgresSQLParser()

        column_type = parser._parse_column_type("FLOAT8")
        assert column_type == ColumnType.DECIMAL

    def test_parse_float4_type(self):
        """Test parsing FLOAT4 type string."""
        parser = PostgresSQLParser()

        column_type = parser._parse_column_type("FLOAT4")
        assert column_type == ColumnType.DECIMAL

    def test_parse_generic_float_type(self):
        """Test parsing generic FLOAT type string."""
        parser = PostgresSQLParser()

        column_type = parser._parse_column_type("FLOAT")
        assert column_type == ColumnType.DECIMAL
