"""Unit tests for GIN index SQL parsing with operator classes.

Tests that the SQL parser correctly extracts operator classes from
GIN index CREATE statements, enabling proper schema sync roundtrips.
"""

import pytest

from ff_storage.db.schema_sync.models import IndexDefinition
from ff_storage.db.schema_sync.postgres import PostgresMigrationGenerator, PostgresSQLParser


class TestParseColumnWithOpclass:
    """Tests for _parse_column_with_opclass helper method."""

    @pytest.fixture
    def parser(self):
        return PostgresSQLParser()

    def test_column_with_gin_trgm_ops(self, parser):
        """Parse column with gin_trgm_ops operator class."""
        col_name, opclass = parser._parse_column_with_opclass('"description" gin_trgm_ops')

        assert col_name == "description"
        assert opclass == "gin_trgm_ops"

    def test_column_with_jsonb_ops(self, parser):
        """Parse column with jsonb_ops operator class."""
        col_name, opclass = parser._parse_column_with_opclass('"metadata" jsonb_ops')

        assert col_name == "metadata"
        assert opclass == "jsonb_ops"

    def test_column_with_jsonb_path_ops(self, parser):
        """Parse column with jsonb_path_ops operator class."""
        col_name, opclass = parser._parse_column_with_opclass('"data" jsonb_path_ops')

        assert col_name == "data"
        assert opclass == "jsonb_path_ops"

    def test_column_without_opclass(self, parser):
        """Parse column without operator class."""
        col_name, opclass = parser._parse_column_with_opclass('"name"')

        assert col_name == "name"
        assert opclass is None

    def test_unquoted_column_with_opclass(self, parser):
        """Parse unquoted column with operator class."""
        col_name, opclass = parser._parse_column_with_opclass("description gin_trgm_ops")

        assert col_name == "description"
        assert opclass == "gin_trgm_ops"

    def test_unquoted_column_without_opclass(self, parser):
        """Parse unquoted column without operator class."""
        col_name, opclass = parser._parse_column_with_opclass("name")

        assert col_name == "name"
        assert opclass is None

    def test_case_insensitive_opclass(self, parser):
        """Operator class matching should be case-insensitive."""
        col_name, opclass = parser._parse_column_with_opclass('"col" GIN_TRGM_OPS')

        assert col_name == "col"
        assert opclass == "gin_trgm_ops"

    def test_whitespace_handling(self, parser):
        """Handle extra whitespace gracefully."""
        col_name, opclass = parser._parse_column_with_opclass('  "description"   gin_trgm_ops  ')

        assert col_name == "description"
        assert opclass == "gin_trgm_ops"


class TestParseGinIndexFromSQL:
    """Tests for parsing GIN index CREATE statements."""

    @pytest.fixture
    def parser(self):
        return PostgresSQLParser()

    def test_parse_gin_index_with_opclass(self, parser):
        """Parse GIN index with operator class."""
        sql = """CREATE INDEX IF NOT EXISTS "idx_products_name"
                 ON "public"."products"
                 USING gin ("name" gin_trgm_ops);"""

        indexes = parser.parse_indexes_from_sql(sql)

        assert len(indexes) == 1
        assert indexes[0].name == "idx_products_name"
        assert indexes[0].columns == ["name"]
        assert indexes[0].opclass == "gin_trgm_ops"
        assert indexes[0].index_type == "gin"

    def test_parse_gin_index_with_where_clause(self, parser):
        """Parse GIN index with operator class and WHERE clause."""
        sql = """CREATE INDEX "idx_desc_gin"
                 ON "public"."products"
                 USING gin ("description" gin_trgm_ops)
                 WHERE deleted_at IS NULL;"""

        indexes = parser.parse_indexes_from_sql(sql)

        assert len(indexes) == 1
        assert indexes[0].columns == ["description"]
        assert indexes[0].opclass == "gin_trgm_ops"
        assert indexes[0].where_clause == "deleted_at IS NULL"

    def test_parse_gin_index_without_opclass(self, parser):
        """Parse GIN index without explicit operator class."""
        sql = """CREATE INDEX "idx_tags_gin"
                 ON "public"."products"
                 USING gin ("tags");"""

        indexes = parser.parse_indexes_from_sql(sql)

        assert len(indexes) == 1
        assert indexes[0].columns == ["tags"]
        assert indexes[0].opclass is None
        assert indexes[0].index_type == "gin"

    def test_parse_btree_index_unchanged(self, parser):
        """Btree indexes should still work correctly."""
        sql = """CREATE INDEX "idx_name"
                 ON "public"."products" ("name");"""

        indexes = parser.parse_indexes_from_sql(sql)

        assert len(indexes) == 1
        assert indexes[0].columns == ["name"]
        assert indexes[0].opclass is None
        assert indexes[0].index_type == "btree"

    def test_parse_jsonb_ops_index(self, parser):
        """Parse JSONB index with jsonb_ops operator class."""
        sql = """CREATE INDEX "idx_metadata_gin"
                 ON "public"."products"
                 USING gin ("metadata" jsonb_ops);"""

        indexes = parser.parse_indexes_from_sql(sql)

        assert len(indexes) == 1
        assert indexes[0].columns == ["metadata"]
        assert indexes[0].opclass == "jsonb_ops"


class TestGinIndexRoundtrip:
    """Tests for generate -> parse roundtrip consistency."""

    @pytest.fixture
    def generator(self):
        return PostgresMigrationGenerator()

    @pytest.fixture
    def parser(self):
        return PostgresSQLParser()

    def test_roundtrip_gin_with_opclass(self, generator, parser):
        """Generated GIN index SQL should parse back correctly."""
        original = IndexDefinition(
            name="idx_test_gin",
            table_name="test",
            columns=["description"],
            index_type="gin",
            opclass="gin_trgm_ops",
        )

        sql = generator.generate_create_index("public", original)
        parsed = parser.parse_indexes_from_sql(sql)

        assert len(parsed) == 1
        assert parsed[0].name == original.name
        assert parsed[0].columns == original.columns
        assert parsed[0].opclass == original.opclass
        assert parsed[0].index_type == original.index_type

    def test_roundtrip_gin_with_where_clause(self, generator, parser):
        """GIN index with WHERE clause should roundtrip correctly."""
        original = IndexDefinition(
            name="idx_partial_gin",
            table_name="products",
            columns=["description"],
            index_type="gin",
            opclass="gin_trgm_ops",
            where_clause="deleted_at IS NULL",
        )

        sql = generator.generate_create_index("public", original)
        parsed = parser.parse_indexes_from_sql(sql)

        assert len(parsed) == 1
        assert parsed[0].columns == original.columns
        assert parsed[0].opclass == original.opclass
        assert parsed[0].where_clause == original.where_clause

    def test_roundtrip_jsonb_index(self, generator, parser):
        """JSONB GIN index should roundtrip correctly."""
        original = IndexDefinition(
            name="idx_meta_gin",
            table_name="products",
            columns=["metadata"],
            index_type="gin",
            opclass="jsonb_ops",
        )

        sql = generator.generate_create_index("public", original)
        parsed = parser.parse_indexes_from_sql(sql)

        assert len(parsed) == 1
        assert parsed[0].opclass == "jsonb_ops"

    def test_roundtrip_btree_unchanged(self, generator, parser):
        """Btree indexes should still roundtrip correctly."""
        original = IndexDefinition(
            name="idx_name",
            table_name="products",
            columns=["name"],
            index_type="btree",
        )

        sql = generator.generate_create_index("public", original)
        parsed = parser.parse_indexes_from_sql(sql)

        assert len(parsed) == 1
        assert parsed[0].columns == original.columns
        assert parsed[0].opclass is None
        assert parsed[0].index_type == "btree"


class TestSchemaSyncIdempotency:
    """Tests ensuring schema sync doesn't create infinite loops."""

    @pytest.fixture
    def generator(self):
        return PostgresMigrationGenerator()

    @pytest.fixture
    def parser(self):
        return PostgresSQLParser()

    def test_model_and_parsed_indexes_match(self, generator, parser):
        """Model-defined index should match parsed index from generated SQL.

        This is the core test for preventing schema sync infinite loops.
        If the parsed index doesn't match the model's index definition,
        schema sync will keep trying to recreate the index.
        """
        # Simulate model-defined index
        model_index = IndexDefinition(
            name="idx_programs_description_gin",
            table_name="programs",
            columns=["program_description"],
            index_type="gin",
            opclass="gin_trgm_ops",
            where_clause="valid_to IS NULL AND deleted_at IS NULL",
        )

        # Generate SQL
        sql = generator.generate_create_index("broker_wb", model_index)

        # Parse SQL back
        parsed_indexes = parser.parse_indexes_from_sql(sql)

        assert len(parsed_indexes) == 1
        parsed_index = parsed_indexes[0]

        # Critical assertions for schema sync idempotency
        assert (
            parsed_index.columns == model_index.columns
        ), f"Column mismatch: {parsed_index.columns} != {model_index.columns}"
        assert (
            parsed_index.opclass == model_index.opclass
        ), f"Opclass mismatch: {parsed_index.opclass} != {model_index.opclass}"
        assert (
            parsed_index.index_type == model_index.index_type
        ), f"Index type mismatch: {parsed_index.index_type} != {model_index.index_type}"
