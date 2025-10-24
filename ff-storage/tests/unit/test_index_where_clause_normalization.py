"""
Regression tests for index WHERE clause normalization in schema diff.

Tests that index WHERE clauses are normalized before comparison to prevent
unnecessary index drops/recreates due to cosmetic differences.

Issue: PostgreSQL returns WHERE clauses like "(deleted_at IS NULL)" but
generated DDL uses "deleted_at IS NULL", causing schema sync to think
they're different and repeatedly drop/recreate indexes.
"""

from ff_storage.db.schema_sync.base import SchemaDifferBase
from ff_storage.db.schema_sync.models import IndexDefinition


class TestWhereClauseNormalization:
    """Test WHERE clause normalization in schema differ."""

    def test_normalize_where_clause_strips_outer_parens(self):
        """Test that outer parentheses are stripped from WHERE clauses."""
        differ = SchemaDifferBase()

        # Test basic case
        assert differ._normalize_where_clause("(deleted_at IS NULL)") == "deleted_at IS NULL"
        assert differ._normalize_where_clause("deleted_at IS NULL") == "deleted_at IS NULL"

        # Test multiple levels of nesting - strips all balanced outer parens
        assert differ._normalize_where_clause("((deleted_at IS NULL))") == "deleted_at IS NULL"

        # Test compound conditions - strip outer parens only
        assert (
            differ._normalize_where_clause("(deleted_at IS NULL AND valid_to IS NULL)")
            == "deleted_at IS NULL AND valid_to IS NULL"
        )

        # Test that inner parens are preserved
        assert (
            differ._normalize_where_clause("((a IS NULL) AND (b = 1))") == "(a IS NULL) AND (b = 1)"
        )

        # Test None handling
        assert differ._normalize_where_clause(None) is None

        # Test whitespace normalization
        assert differ._normalize_where_clause("  deleted_at IS NULL  ") == "deleted_at IS NULL"

    def test_indexes_equal_with_equivalent_where_clauses(self):
        """
        Test that indexes with equivalent WHERE clauses are considered equal.

        This is the core bug: PostgreSQL returns "(deleted_at IS NULL)" but
        our generated DDL uses "deleted_at IS NULL", causing false positives.
        """
        differ = SchemaDifferBase()

        # Index from database (with parens, as returned by pg_get_expr)
        idx_from_db = IndexDefinition(
            name="idx_products_not_deleted",
            table_name="products",
            columns=["deleted_at"],
            unique=False,
            index_type="btree",
            where_clause="(deleted_at IS NULL)",  # PostgreSQL format
        )

        # Index from generated DDL (without parens)
        idx_from_model = IndexDefinition(
            name="idx_products_not_deleted",
            table_name="products",
            columns=["deleted_at"],
            unique=False,
            index_type="btree",
            where_clause="deleted_at IS NULL",  # Generated format
        )

        # EXPECTED: These should be considered equal
        # ACTUAL (before fix): Returns False, causing index to be dropped/recreated
        assert differ._indexes_equal(idx_from_db, idx_from_model) is True

    def test_indexes_equal_with_compound_where_clauses(self):
        """Test normalization works with compound WHERE clauses."""
        differ = SchemaDifferBase()

        idx1 = IndexDefinition(
            name="idx_current",
            table_name="products",
            columns=["id", "tenant_id"],
            unique=False,
            index_type="btree",
            where_clause="(valid_to IS NULL AND deleted_at IS NULL)",  # DB format
        )

        idx2 = IndexDefinition(
            name="idx_current",
            table_name="products",
            columns=["id", "tenant_id"],
            unique=False,
            index_type="btree",
            where_clause="valid_to IS NULL AND deleted_at IS NULL",  # Generated format
        )

        assert differ._indexes_equal(idx1, idx2) is True

    def test_indexes_not_equal_with_different_conditions(self):
        """Test that genuinely different WHERE clauses are still detected."""
        differ = SchemaDifferBase()

        idx1 = IndexDefinition(
            name="idx_test",
            table_name="products",
            columns=["status"],
            unique=False,
            index_type="btree",
            where_clause="deleted_at IS NULL",
        )

        idx2 = IndexDefinition(
            name="idx_test",
            table_name="products",
            columns=["status"],
            unique=False,
            index_type="btree",
            where_clause="status = 'active'",  # Actually different
        )

        # These should NOT be equal
        assert differ._indexes_equal(idx1, idx2) is False
