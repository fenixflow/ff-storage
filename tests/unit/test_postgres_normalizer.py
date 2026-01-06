"""
Tests for PostgreSQL-specific schema normalization.

Tests PostgresNormalizer handling of PostgreSQL-specific quirks:
- Float type aliases (float8, float4, double, real)
- Integer aliases (int4, int8)
- Boolean type (bool)
"""

from ff_storage.db.schema_sync.models import ColumnDefinition, ColumnType
from ff_storage.db.schema_sync.normalizer import PostgresNormalizer


class TestPostgresFloatTypeNormalization:
    """Test PostgreSQL float type alias normalization."""

    def test_normalize_float8_to_double_precision(self):
        """Test that 'float8' is normalized to 'DOUBLE PRECISION'."""
        normalizer = PostgresNormalizer()
        result = normalizer.normalize_native_type("float8")
        assert result == "DOUBLE PRECISION"

    def test_normalize_double_to_double_precision(self):
        """Test that 'double' is normalized to 'DOUBLE PRECISION'."""
        normalizer = PostgresNormalizer()
        result = normalizer.normalize_native_type("double")
        assert result == "DOUBLE PRECISION"

    def test_normalize_double_precision_unchanged(self):
        """Test that 'DOUBLE PRECISION' remains unchanged."""
        normalizer = PostgresNormalizer()
        result = normalizer.normalize_native_type("DOUBLE PRECISION")
        assert result == "DOUBLE PRECISION"

    def test_normalize_float4_to_real(self):
        """Test that 'float4' is normalized to 'REAL'."""
        normalizer = PostgresNormalizer()
        result = normalizer.normalize_native_type("float4")
        assert result == "REAL"

    def test_normalize_real_unchanged(self):
        """Test that 'real' is normalized to uppercase 'REAL'."""
        normalizer = PostgresNormalizer()
        result = normalizer.normalize_native_type("real")
        assert result == "REAL"


class TestPostgresIntegerTypeNormalization:
    """Test PostgreSQL integer type alias normalization."""

    def test_normalize_int4_to_integer(self):
        """Test that 'int4' is normalized to 'INTEGER'."""
        normalizer = PostgresNormalizer()
        result = normalizer.normalize_native_type("int4")
        assert result == "INTEGER"

    def test_normalize_int8_to_bigint(self):
        """Test that 'int8' is normalized to 'BIGINT'."""
        normalizer = PostgresNormalizer()
        result = normalizer.normalize_native_type("int8")
        assert result == "BIGINT"


class TestPostgresBooleanTypeNormalization:
    """Test PostgreSQL boolean type normalization."""

    def test_normalize_bool_to_boolean(self):
        """Test that 'bool' is normalized to 'BOOLEAN'."""
        normalizer = PostgresNormalizer()
        result = normalizer.normalize_native_type("bool")
        assert result == "BOOLEAN"


class TestPostgresColumnNormalization:
    """Test full column normalization with PostgreSQL types."""

    def test_normalize_float8_column(self):
        """
        Test normalization of column with float8 type.

        This is the production case from PostgreSQL introspection where
        columns are introspected as 'float8' but generated DDL uses
        'DOUBLE PRECISION'.
        """
        normalizer = PostgresNormalizer()

        # Column from database introspection
        col_from_db = ColumnDefinition(
            name="price",
            column_type=ColumnType.DECIMAL,
            nullable=False,
            native_type="float8",  # PostgreSQL internal name
        )

        # Column from generated DDL
        col_from_ddl = ColumnDefinition(
            name="price",
            column_type=ColumnType.DECIMAL,
            nullable=False,
            native_type="DOUBLE PRECISION",  # SQL standard name
        )

        norm_db = normalizer.normalize_column(col_from_db)
        norm_ddl = normalizer.normalize_column(col_from_ddl)

        # After normalization, both should have the same native_type
        assert norm_db.native_type == norm_ddl.native_type == "DOUBLE PRECISION"

    def test_normalize_int4_column(self):
        """Test normalization of column with int4 type."""
        normalizer = PostgresNormalizer()

        col = ColumnDefinition(
            name="count",
            column_type=ColumnType.INTEGER,
            nullable=False,
            native_type="int4",
        )

        normalized = normalizer.normalize_column(col)

        assert normalized.native_type == "INTEGER"

    def test_normalize_bool_column_with_default(self):
        """
        Test normalization of boolean column with default value.

        PostgreSQL returns boolean defaults in various formats:
        - 'false', 'f', '0'
        - 'true', 't', '1'

        All should normalize to 'FALSE' or 'TRUE'.
        """
        normalizer = PostgresNormalizer()

        # Test 'f' → 'FALSE'
        col_f = ColumnDefinition(
            name="active",
            column_type=ColumnType.BOOLEAN,
            nullable=False,
            default="f",
            native_type="bool",
        )

        normalized_f = normalizer.normalize_column(col_f)
        assert normalized_f.default == "FALSE"
        assert normalized_f.native_type == "BOOLEAN"

        # Test 't' → 'TRUE'
        col_t = ColumnDefinition(
            name="active",
            column_type=ColumnType.BOOLEAN,
            nullable=False,
            default="t",
            native_type="bool",
        )

        normalized_t = normalizer.normalize_column(col_t)
        assert normalized_t.default == "TRUE"
        assert normalized_t.native_type == "BOOLEAN"


class TestPostgresNormalizationEquivalence:
    """Test that different PostgreSQL formats normalize to equivalent values."""

    def test_float_types_normalize_equivalently(self):
        """
        Test that all PostgreSQL float type representations normalize to the same value.

        This ensures that columns with any of these types will compare as equal:
        - float8 (PostgreSQL internal)
        - double (shorthand)
        - DOUBLE PRECISION (SQL standard)
        """
        normalizer = PostgresNormalizer()

        types = ["float8", "double", "DOUBLE PRECISION", "Double Precision"]

        normalized = [normalizer.normalize_native_type(t) for t in types]

        # All should normalize to the same value
        assert all(n == "DOUBLE PRECISION" for n in normalized)

    def test_integer_types_normalize_equivalently(self):
        """Test that int4 and INTEGER normalize to the same value."""
        normalizer = PostgresNormalizer()

        types = ["int4", "INTEGER", "integer", "Integer"]

        normalized = [normalizer.normalize_native_type(t) for t in types]

        # All should normalize to the same value
        assert all(n == "INTEGER" for n in normalized)
