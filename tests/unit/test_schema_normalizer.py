"""
Comprehensive test suite for schema normalization framework.

Tests the base SchemaNormalizer class and its provider-agnostic normalization logic.
This is the foundation for eliminating false positives in schema drift detection.
"""

from ff_storage.db.schema_sync.models import ColumnDefinition, ColumnType, IndexDefinition
from ff_storage.db.schema_sync.normalizer import SchemaNormalizer


class TestDefaultValueNormalization:
    """Test normalization of default values across different formats."""

    def test_normalize_boolean_true_lowercase(self):
        """Test that lowercase 'true' is normalized to 'TRUE'."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("true", ColumnType.BOOLEAN)
        assert result == "TRUE"

    def test_normalize_boolean_true_uppercase(self):
        """Test that uppercase 'TRUE' remains 'TRUE'."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("TRUE", ColumnType.BOOLEAN)
        assert result == "TRUE"

    def test_normalize_boolean_true_single_char(self):
        """Test that 't' is normalized to 'TRUE'."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("t", ColumnType.BOOLEAN)
        assert result == "TRUE"

    def test_normalize_boolean_true_numeric(self):
        """Test that '1' is normalized to 'TRUE'."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("1", ColumnType.BOOLEAN)
        assert result == "TRUE"

    def test_normalize_boolean_false_lowercase(self):
        """Test that lowercase 'false' is normalized to 'FALSE'."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("false", ColumnType.BOOLEAN)
        assert result == "FALSE"

    def test_normalize_boolean_false_uppercase(self):
        """Test that uppercase 'FALSE' remains 'FALSE'."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("FALSE", ColumnType.BOOLEAN)
        assert result == "FALSE"

    def test_normalize_boolean_false_single_char(self):
        """Test that 'f' is normalized to 'FALSE'."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("f", ColumnType.BOOLEAN)
        assert result == "FALSE"

    def test_normalize_boolean_false_numeric(self):
        """Test that '0' is normalized to 'FALSE'."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("0", ColumnType.BOOLEAN)
        assert result == "FALSE"

    def test_normalize_null_string_to_none(self):
        """Test that 'NULL' string is normalized to None."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("NULL", ColumnType.STRING)
        assert result is None

    def test_normalize_null_lowercase_to_none(self):
        """Test that 'null' string is normalized to None."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("null", ColumnType.STRING)
        assert result is None

    def test_normalize_none_remains_none(self):
        """Test that None value remains None."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value(None, ColumnType.STRING)
        assert result is None

    def test_normalize_empty_string_to_none(self):
        """Test that empty string is normalized to None."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("", ColumnType.STRING)
        assert result is None

    def test_normalize_whitespace_only_to_none(self):
        """Test that whitespace-only string is normalized to None."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("   ", ColumnType.STRING)
        assert result is None

    def test_normalize_non_boolean_default_unchanged(self):
        """Test that non-boolean defaults are preserved (after trimming)."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("  'default_value'  ", ColumnType.STRING)
        assert result == "'default_value'"

    def test_normalize_numeric_default_unchanged(self):
        """Test that numeric defaults are preserved (after trimming)."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("  42  ", ColumnType.INTEGER)
        assert result == "42"

    def test_normalize_now_function_lowercase(self):
        """Test that lowercase 'now()' is normalized to 'NOW()'."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("now()", ColumnType.TIMESTAMP)
        assert result == "NOW()"

    def test_normalize_now_function_uppercase(self):
        """Test that uppercase 'NOW()' remains 'NOW()'."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("NOW()", ColumnType.TIMESTAMP)
        assert result == "NOW()"

    def test_normalize_now_function_mixed_case(self):
        """Test that mixed-case 'Now()' is normalized to 'NOW()'."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("Now()", ColumnType.TIMESTAMP)
        assert result == "NOW()"

    def test_normalize_current_timestamp_lowercase(self):
        """Test that lowercase 'current_timestamp' is normalized."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("current_timestamp", ColumnType.TIMESTAMP)
        assert result == "CURRENT_TIMESTAMP"

    def test_normalize_current_timestamp_uppercase(self):
        """Test that uppercase 'CURRENT_TIMESTAMP' remains unchanged."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("CURRENT_TIMESTAMP", ColumnType.TIMESTAMP)
        assert result == "CURRENT_TIMESTAMP"

    def test_normalize_gen_random_uuid_lowercase(self):
        """Test that lowercase 'gen_random_uuid()' remains lowercase (PG convention)."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("gen_random_uuid()", ColumnType.UUID)
        assert result == "gen_random_uuid()"

    def test_normalize_gen_random_uuid_uppercase(self):
        """Test that uppercase 'GEN_RANDOM_UUID()' is normalized to lowercase."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("GEN_RANDOM_UUID()", ColumnType.UUID)
        assert result == "gen_random_uuid()"

    def test_normalize_current_date_lowercase(self):
        """Test that lowercase 'current_date' is normalized."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("current_date", ColumnType.TIMESTAMP)
        assert result == "CURRENT_DATE"

    def test_normalize_current_time_lowercase(self):
        """Test that lowercase 'current_time' is normalized."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_default_value("current_time", ColumnType.TIME)
        assert result == "CURRENT_TIME"


class TestNativeTypeNormalization:
    """Test normalization of native (provider-specific) type names."""

    def test_normalize_type_case_uppercase(self):
        """Test that type names are normalized to uppercase."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_native_type("varchar")
        assert result == "VARCHAR"

    def test_normalize_type_case_mixed(self):
        """Test that mixed-case types are normalized to uppercase."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_native_type("VarChar")
        assert result == "VARCHAR"

    def test_normalize_type_whitespace_collapsed(self):
        """Test that multiple spaces are collapsed to single space."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_native_type("DOUBLE    PRECISION")
        assert result == "DOUBLE PRECISION"

    def test_normalize_type_leading_trailing_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_native_type("  INTEGER  ")
        assert result == "INTEGER"

    def test_normalize_type_with_parameters(self):
        """Test that types with parameters are normalized."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_native_type("varchar(255)")
        assert result == "VARCHAR(255)"

    def test_normalize_type_with_parameters_whitespace(self):
        """Test that whitespace around parameters is removed."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_native_type("DECIMAL( 10 , 2 )")
        assert result == "DECIMAL(10,2)"

    def test_normalize_none_type(self):
        """Test that None type returns None."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_native_type(None)
        assert result is None


class TestIdentifierNormalization:
    """Test normalization of SQL identifiers (table, column, index names)."""

    def test_normalize_identifier_lowercase(self):
        """Test that identifiers are normalized to lowercase."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_identifier("MyTable")
        assert result == "mytable"

    def test_normalize_identifier_strip_quotes(self):
        """Test that quotes are stripped from identifiers."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_identifier('"my_table"')
        assert result == "my_table"

    def test_normalize_identifier_none(self):
        """Test that None identifier returns None."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_identifier(None)
        assert result is None


class TestReferencesNormalization:
    """Test normalization of foreign key references."""

    def test_normalize_references_case(self):
        """Test that references are normalized to lowercase."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_references("Users(id)")
        assert result == "users(id)"

    def test_normalize_references_with_schema(self):
        """Test that schema-qualified references are normalized."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_references("public.Users(id)")
        assert result == "public.users(id)"

    def test_normalize_references_none(self):
        """Test that None references return None."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_references(None)
        assert result is None


class TestIndexTypeNormalization:
    """Test normalization of index types."""

    def test_normalize_index_type_lowercase(self):
        """Test that index types are normalized to uppercase."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_index_type("btree")
        assert result == "BTREE"

    def test_normalize_index_type_mixed_case(self):
        """Test that mixed-case index types are normalized."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_index_type("BTree")
        assert result == "BTREE"

    def test_normalize_index_type_hash(self):
        """Test that hash index type is normalized."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_index_type("hash")
        assert result == "HASH"


class TestColumnNormalization:
    """Test full column normalization including all properties."""

    def test_normalize_column_all_properties(self):
        """Test that all column properties are normalized."""
        normalizer = SchemaNormalizer()

        col = ColumnDefinition(
            name="MyColumn",
            column_type=ColumnType.BOOLEAN,
            nullable=True,
            default="false",
            native_type="boolean",
        )

        normalized = normalizer.normalize_column(col)

        # Name should be unchanged (preserved for SQL generation)
        assert normalized.name == "MyColumn"
        assert normalized.column_type == ColumnType.BOOLEAN
        assert normalized.nullable is True
        assert normalized.default == "FALSE"  # Normalized
        assert normalized.native_type == "BOOLEAN"  # Normalized

    def test_normalize_column_with_references(self):
        """Test that foreign key references are normalized."""
        normalizer = SchemaNormalizer()

        col = ColumnDefinition(
            name="user_id",
            column_type=ColumnType.UUID,
            nullable=False,
            is_foreign_key=True,
            references="Users(id)",
            native_type="uuid",
        )

        normalized = normalizer.normalize_column(col)

        assert normalized.references == "users(id)"
        assert normalized.native_type == "UUID"

    def test_normalize_column_with_precision(self):
        """Test that decimal columns with precision are normalized."""
        normalizer = SchemaNormalizer()

        col = ColumnDefinition(
            name="price",
            column_type=ColumnType.DECIMAL,
            nullable=False,
            precision=10,
            scale=2,
            native_type="  DECIMAL(10, 2)  ",
        )

        normalized = normalizer.normalize_column(col)

        assert normalized.precision == 10
        assert normalized.scale == 2
        assert normalized.native_type == "DECIMAL(10,2)"


class TestIndexNormalization:
    """Test full index normalization including all properties."""

    def test_normalize_index_basic(self):
        """Test that basic index properties are normalized."""
        normalizer = SchemaNormalizer()

        idx = IndexDefinition(
            name="idx_user_email",
            table_name="users",
            columns=["email"],
            unique=True,
            index_type="btree",
        )

        normalized = normalizer.normalize_index(idx)

        assert normalized.name == "idx_user_email"
        assert normalized.table_name == "users"
        assert normalized.columns == ["email"]
        assert normalized.unique is True
        assert normalized.index_type == "BTREE"  # Normalized

    def test_normalize_index_preserves_column_order(self):
        """Test that column order in indexes is preserved."""
        normalizer = SchemaNormalizer()

        idx = IndexDefinition(
            name="idx_composite",
            table_name="users",
            columns=["tenant_id", "email", "created_at"],
            unique=False,
            index_type="BTREE",
        )

        normalized = normalizer.normalize_index(idx)

        # Column order MUST be preserved (order matters for SQL indexes)
        assert normalized.columns == ["tenant_id", "email", "created_at"]

    def test_normalize_index_with_where_clause(self):
        """Test that indexes with WHERE clauses are normalized."""
        normalizer = SchemaNormalizer()

        idx = IndexDefinition(
            name="idx_active_users",
            table_name="users",
            columns=["email"],
            unique=True,
            index_type="btree",
            where_clause="(deleted_at IS NULL)",  # Will be normalized
        )

        normalized = normalizer.normalize_index(idx)

        # WHERE clause should be normalized (parentheses stripped)
        assert normalized.where_clause == "deleted_at IS NULL"


class TestColumnComparison:
    """Test that normalized columns compare correctly."""

    def test_columns_equal_after_normalization(self):
        """Test that columns with cosmetic differences are equal after normalization."""
        normalizer = SchemaNormalizer()

        col1 = ColumnDefinition(
            name="status",
            column_type=ColumnType.BOOLEAN,
            nullable=False,
            default="false",  # Lowercase
            native_type="boolean",  # Lowercase
        )

        col2 = ColumnDefinition(
            name="status",
            column_type=ColumnType.BOOLEAN,
            nullable=False,
            default="FALSE",  # Uppercase
            native_type="BOOLEAN",  # Uppercase
        )

        norm1 = normalizer.normalize_column(col1)
        norm2 = normalizer.normalize_column(col2)

        # After normalization, they should be identical
        assert norm1.default == norm2.default
        assert norm1.native_type == norm2.native_type

    def test_columns_not_equal_genuine_difference(self):
        """Test that genuinely different columns are not equal."""
        normalizer = SchemaNormalizer()

        col1 = ColumnDefinition(
            name="status",
            column_type=ColumnType.BOOLEAN,
            nullable=False,
            default="TRUE",
            native_type="BOOLEAN",
        )

        col2 = ColumnDefinition(
            name="status",
            column_type=ColumnType.BOOLEAN,
            nullable=False,
            default="FALSE",  # Actually different
            native_type="BOOLEAN",
        )

        norm1 = normalizer.normalize_column(col1)
        norm2 = normalizer.normalize_column(col2)

        # These should remain different
        assert norm1.default != norm2.default


class TestIndexComparison:
    """Test that normalized indexes compare correctly."""

    def test_indexes_equal_after_normalization(self):
        """Test that indexes with cosmetic differences are equal after normalization."""
        normalizer = SchemaNormalizer()

        idx1 = IndexDefinition(
            name="idx_test",
            table_name="users",
            columns=["email"],
            unique=True,
            index_type="btree",  # Lowercase
        )

        idx2 = IndexDefinition(
            name="idx_test",
            table_name="users",
            columns=["email"],
            unique=True,
            index_type="BTREE",  # Uppercase
        )

        norm1 = normalizer.normalize_index(idx1)
        norm2 = normalizer.normalize_index(idx2)

        # After normalization, index types should match
        assert norm1.index_type == norm2.index_type

    def test_indexes_not_equal_genuine_difference(self):
        """Test that genuinely different indexes are not equal."""
        normalizer = SchemaNormalizer()

        idx1 = IndexDefinition(
            name="idx_test",
            table_name="users",
            columns=["email"],
            unique=True,
            index_type="BTREE",
        )

        idx2 = IndexDefinition(
            name="idx_test",
            table_name="users",
            columns=["email"],
            unique=False,  # Actually different
            index_type="BTREE",
        )

        norm1 = normalizer.normalize_index(idx1)
        norm2 = normalizer.normalize_index(idx2)

        # These should remain different
        assert norm1.unique != norm2.unique
