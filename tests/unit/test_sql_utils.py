"""Unit tests for SQL utilities."""

from ff_storage.query.sql_utils import (
    ColumnRef,
    ParameterTracker,
    build_between_clause,
    build_in_clause,
    build_not_in_clause,
)


class TestColumnRef:
    """Tests for ColumnRef utility class."""

    def test_format_default_alias(self):
        """Format should use t0 as default alias."""
        result = ColumnRef.format("price")
        assert result == 't0."price"'

    def test_format_custom_alias(self):
        """Format should use custom alias when provided."""
        result = ColumnRef.format("name", "t1")
        assert result == 't1."name"'

    def test_format_qualified(self):
        """Format_qualified should quote all parts."""
        result = ColumnRef.format_qualified("public", "users", "id")
        assert result == '"public"."users"."id"'

    def test_format_table(self):
        """Format_table should quote schema and table."""
        result = ColumnRef.format_table("public", "products")
        assert result == '"public"."products"'

    def test_quote_identifier_simple(self):
        """Quote_identifier should quote simple names."""
        result = ColumnRef.quote_identifier("users")
        assert result == '"users"'

    def test_quote_identifier_dotted(self):
        """Quote_identifier should handle dotted names."""
        result = ColumnRef.quote_identifier("public.users")
        assert result == '"public"."users"'

    def test_quote_identifier_reserved_word(self):
        """Quote_identifier should handle reserved words safely."""
        result = ColumnRef.quote_identifier("order")
        assert result == '"order"'

    def test_escape_embedded_quotes_in_format(self):
        """Format should escape embedded double quotes (Issue #6)."""
        result = ColumnRef.format('col"name')
        assert result == 't0."col""name"'

    def test_escape_embedded_quotes_in_quote_identifier(self):
        """Quote_identifier should escape embedded double quotes."""
        result = ColumnRef.quote_identifier('foo"bar')
        assert result == '"foo""bar"'

    def test_escape_embedded_quotes_in_dotted_identifier(self):
        """Quote_identifier should escape quotes in dotted identifiers."""
        result = ColumnRef.quote_identifier('schema"x.table"y')
        assert result == '"schema""x"."table""y"'

    def test_escape_embedded_quotes_in_format_qualified(self):
        """Format_qualified should escape embedded quotes in all parts."""
        result = ColumnRef.format_qualified('my"schema', 'my"table', 'my"column')
        assert result == '"my""schema"."my""table"."my""column"'

    def test_escape_embedded_quotes_in_format_table(self):
        """Format_table should escape embedded quotes."""
        result = ColumnRef.format_table('sch"ema', 'tab"le')
        assert result == '"sch""ema"."tab""le"'

    def test_escape_identifier_helper(self):
        """_escape_identifier should double quotes."""
        result = ColumnRef._escape_identifier('test"value"here')
        assert result == 'test""value""here'

    def test_escape_identifier_no_quotes(self):
        """_escape_identifier should pass through clean names."""
        result = ColumnRef._escape_identifier("clean_name")
        assert result == "clean_name"


class TestParameterTracker:
    """Tests for ParameterTracker utility class."""

    def test_next_starts_at_one(self):
        """Next should start at $1 by default."""
        tracker = ParameterTracker()
        assert tracker.next() == "$1"
        assert tracker.next() == "$2"
        assert tracker.next() == "$3"

    def test_next_custom_start(self):
        """Next should respect custom start index."""
        tracker = ParameterTracker(start=5)
        assert tracker.next() == "$5"
        assert tracker.next() == "$6"

    def test_next_n(self):
        """Next_n should generate comma-separated placeholders."""
        tracker = ParameterTracker()
        result = tracker.next_n(3)
        assert result == "$1, $2, $3"
        assert tracker.current == 4

    def test_next_n_zero(self):
        """Next_n with zero count should return empty string."""
        tracker = ParameterTracker()
        result = tracker.next_n(0)
        assert result == ""
        assert tracker.current == 1

    def test_next_n_negative(self):
        """Next_n with negative count should return empty string."""
        tracker = ParameterTracker()
        result = tracker.next_n(-5)
        assert result == ""
        assert tracker.current == 1

    def test_next_list(self):
        """Next_list should generate list of placeholders."""
        tracker = ParameterTracker()
        result = tracker.next_list(3)
        assert result == ["$1", "$2", "$3"]
        assert tracker.current == 4

    def test_next_list_empty(self):
        """Next_list with zero count should return empty list."""
        tracker = ParameterTracker()
        result = tracker.next_list(0)
        assert result == []

    def test_current_property(self):
        """Current property should track index."""
        tracker = ParameterTracker()
        assert tracker.current == 1
        tracker.next()
        assert tracker.current == 2
        tracker.next_n(3)
        assert tracker.current == 5

    def test_add_param(self):
        """Add_param should track value and return placeholder."""
        tracker = ParameterTracker()
        p1 = tracker.add_param("hello")
        p2 = tracker.add_param(42)
        assert p1 == "$1"
        assert p2 == "$2"
        assert tracker.params == ["hello", 42]

    def test_add_params(self):
        """Add_params should track multiple values."""
        tracker = ParameterTracker()
        result = tracker.add_params(["a", "b", "c"])
        assert result == "$1, $2, $3"
        assert tracker.params == ["a", "b", "c"]

    def test_reset(self):
        """Reset should clear state."""
        tracker = ParameterTracker()
        tracker.next()
        tracker.next()
        tracker.add_param("test")
        tracker.reset()
        assert tracker.current == 1
        assert tracker.params == []

    def test_reset_custom_start(self):
        """Reset should accept custom start index."""
        tracker = ParameterTracker()
        tracker.next()
        tracker.reset(start=10)
        assert tracker.current == 10


class TestBuildInClause:
    """Tests for build_in_clause helper."""

    def test_basic_in_clause(self):
        """Build IN clause with values."""
        tracker = ParameterTracker()
        sql, params = build_in_clause("status", ["a", "b", "c"], tracker)
        assert sql == 't0."status" IN ($1, $2, $3)'
        assert params == ["a", "b", "c"]
        assert tracker.current == 4

    def test_empty_in_clause(self):
        """Empty IN clause should return FALSE."""
        tracker = ParameterTracker()
        sql, params = build_in_clause("status", [], tracker)
        assert sql == "FALSE"
        assert params == []
        assert tracker.current == 1

    def test_custom_alias(self):
        """IN clause with custom table alias."""
        tracker = ParameterTracker()
        sql, params = build_in_clause("id", [1, 2], tracker, table_alias="t5")
        assert sql == 't5."id" IN ($1, $2)'


class TestBuildNotInClause:
    """Tests for build_not_in_clause helper."""

    def test_basic_not_in_clause(self):
        """Build NOT IN clause with values."""
        tracker = ParameterTracker()
        sql, params = build_not_in_clause("status", ["x", "y"], tracker)
        assert sql == 't0."status" NOT IN ($1, $2)'
        assert params == ["x", "y"]

    def test_empty_not_in_clause(self):
        """Empty NOT IN clause should return TRUE."""
        tracker = ParameterTracker()
        sql, params = build_not_in_clause("status", [], tracker)
        assert sql == "TRUE"
        assert params == []


class TestBuildBetweenClause:
    """Tests for build_between_clause helper."""

    def test_basic_between_clause(self):
        """Build BETWEEN clause."""
        tracker = ParameterTracker()
        sql, params = build_between_clause("price", 10, 100, tracker)
        assert sql == 't0."price" BETWEEN $1 AND $2'
        assert params == [10, 100]
        assert tracker.current == 3

    def test_custom_alias(self):
        """BETWEEN clause with custom table alias."""
        tracker = ParameterTracker()
        sql, params = build_between_clause(
            "created_at", "2024-01-01", "2024-12-31", tracker, table_alias="orders"
        )
        assert sql == 'orders."created_at" BETWEEN $1 AND $2'
