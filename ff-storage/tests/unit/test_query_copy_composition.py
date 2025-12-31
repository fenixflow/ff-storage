"""Unit tests for Query.copy() and AND/OR composition."""

import pytest

from ff_storage.query import Query, F
from ff_storage.query.expressions import AND, OR, CompositeExpression, FilterExpression


class MockModel:
    """Mock model for testing."""

    __table_name__ = "products"
    __schema__ = "public"
    __temporal_strategy__ = "none"
    __soft_delete__ = False
    __multi_tenant__ = False


class TestQueryCopy:
    """Tests for Query.copy() method."""

    def test_copy_creates_independent_instance(self):
        """Copy should create an independent query instance."""
        base = Query(MockModel).filter(F.category == "electronics")
        copied = base.copy()

        # Modifying the copy should not affect the base
        copied.filter(F.price > 100)

        assert len(base._filters) == 1
        assert len(copied._filters) == 2

    def test_copy_preserves_filters(self):
        """Copy should preserve existing filters."""
        base = Query(MockModel).filter(F.status == "active")
        copied = base.copy()

        assert len(copied._filters) == 1
        assert copied._filters[0].field == "status"

    def test_copy_preserves_limit_offset(self):
        """Copy should preserve limit and offset."""
        base = Query(MockModel).limit(10).offset(20)
        copied = base.copy()

        assert copied._limit == 10
        assert copied._offset == 20

    def test_copy_preserves_order_by(self):
        """Copy should preserve order by clauses."""
        base = Query(MockModel).order_by(F.created_at.desc())
        copied = base.copy()

        assert len(copied._order_by) == 1
        assert copied._order_by[0].field == "created_at"

    def test_copy_preserves_eager_load(self):
        """Copy should preserve eager load configuration."""
        base = Query(MockModel).load(["author", "comments"])
        copied = base.copy()

        assert copied._eager_load == ["author", "comments"]

    def test_copy_enables_safe_branching(self):
        """Copy should enable creating independent query branches."""
        base = Query(MockModel).filter(F.category == "electronics")

        expensive = base.copy().filter(F.price > 1000)
        cheap = base.copy().filter(F.price < 100)
        featured = base.copy().filter(F.featured.is_not_null())

        # All queries should be independent
        assert len(base._filters) == 1
        assert len(expensive._filters) == 2
        assert len(cheap._filters) == 2
        assert len(featured._filters) == 2

        # Verify the specific filters
        assert expensive._filters[1].field == "price"
        assert expensive._filters[1].operator == ">"
        assert cheap._filters[1].field == "price"
        assert cheap._filters[1].operator == "<"


class TestCompositeExpression:
    """Tests for CompositeExpression class."""

    def test_and_expression(self):
        """AND should combine expressions with AND logic."""
        expr = AND(F.status == "active", F.price > 100)

        assert isinstance(expr, CompositeExpression)
        assert expr.operator == "AND"
        assert len(expr.expressions) == 2

    def test_or_expression(self):
        """OR should combine expressions with OR logic."""
        expr = OR(F.status == "active", F.status == "pending")

        assert isinstance(expr, CompositeExpression)
        assert expr.operator == "OR"
        assert len(expr.expressions) == 2

    def test_and_to_sql(self):
        """AND expression should generate correct SQL."""
        expr = AND(F.status == "active", F.price > 100)
        sql, params, next_idx = expr.to_sql(1)

        assert sql == '(t0."status" = $1 AND t0."price" > $2)'
        assert params == ["active", 100]
        assert next_idx == 3

    def test_or_to_sql(self):
        """OR expression should generate correct SQL."""
        expr = OR(F.status == "active", F.status == "pending")
        sql, params, next_idx = expr.to_sql(1)

        assert sql == '(t0."status" = $1 OR t0."status" = $2)'
        assert params == ["active", "pending"]
        assert next_idx == 3

    def test_nested_and_or(self):
        """Nested AND/OR should generate correct SQL."""
        expr = AND(
            F.category == "electronics",
            OR(F.price > 100, F.featured == True),  # noqa: E712 - testing boolean equality SQL generation
        )
        sql, params, next_idx = expr.to_sql(1)

        assert sql == '(t0."category" = $1 AND (t0."price" > $2 OR t0."featured" = $3))'
        assert params == ["electronics", 100, True]  # noqa: E712
        assert next_idx == 4

    def test_complex_nesting(self):
        """Complex nested expressions should generate correct SQL."""
        expr = OR(
            AND(F.status == "active", F.price > 100), AND(F.status == "featured", F.price > 50)
        )
        sql, params, next_idx = expr.to_sql(1)

        assert sql == (
            '((t0."status" = $1 AND t0."price" > $2) OR ' '(t0."status" = $3 AND t0."price" > $4))'
        )
        assert params == ["active", 100, "featured", 50]
        assert next_idx == 5

    def test_invalid_operator_raises(self):
        """Invalid operator should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid composite operator"):
            CompositeExpression((F.a == 1, F.b == 2), "XOR")

    def test_single_expression_raises(self):
        """Single expression should raise ValueError."""
        with pytest.raises(ValueError, match="requires at least 2 expressions"):
            AND(F.status == "active")

    def test_three_expressions(self):
        """Three expressions should work correctly."""
        expr = AND(F.a == 1, F.b == 2, F.c == 3)
        sql, params, next_idx = expr.to_sql(1)

        assert sql == '(t0."a" = $1 AND t0."b" = $2 AND t0."c" = $3)'
        assert params == [1, 2, 3]
        assert next_idx == 4

    def test_with_alias(self):
        """with_alias should propagate to all expressions."""
        expr = AND(F.status == "active", F.price > 100)
        aliased = expr.with_alias("t5")
        sql, params, _ = aliased.to_sql(1)

        assert 't5."status"' in sql
        assert 't5."price"' in sql


class TestQueryWithCompositeFilters:
    """Tests for Query with composite filters."""

    def test_filter_accepts_composite(self):
        """Query.filter() should accept CompositeExpression."""
        query = Query(MockModel).filter(OR(F.status == "active", F.status == "pending"))

        assert len(query._filters) == 1
        assert isinstance(query._filters[0], CompositeExpression)

    def test_filter_with_mixed_expressions(self):
        """Query.filter() should accept mixed expressions."""
        query = Query(MockModel).filter(
            F.category == "electronics",
            OR(F.price > 100, F.featured == True),  # noqa: E712 - testing boolean equality SQL generation
        )

        assert len(query._filters) == 2
        assert isinstance(query._filters[0], FilterExpression)
        assert isinstance(query._filters[1], CompositeExpression)

    def test_multiple_composite_filters(self):
        """Multiple composite filters should be ANDed together."""
        query = (
            Query(MockModel)
            .filter(OR(F.status == "active", F.status == "pending"))
            .filter(OR(F.category == "a", F.category == "b"))
        )

        assert len(query._filters) == 2


class TestParameterIndexing:
    """Tests for correct parameter indexing in composite expressions."""

    def test_parameter_index_continues_correctly(self):
        """Parameter indices should continue correctly through nested expressions."""
        expr1 = AND(F.a == 1, F.b == 2)
        expr2 = OR(F.c == 3, F.d == 4)

        sql1, params1, next_idx1 = expr1.to_sql(1)
        sql2, params2, next_idx2 = expr2.to_sql(next_idx1)

        assert sql1 == '(t0."a" = $1 AND t0."b" = $2)'
        assert sql2 == '(t0."c" = $3 OR t0."d" = $4)'
        assert params1 == [1, 2]
        assert params2 == [3, 4]
        assert next_idx2 == 5

    def test_in_clause_within_composite(self):
        """IN clauses within composite expressions should work correctly."""
        expr = AND(F.category.in_(["a", "b", "c"]), F.status == "active")
        sql, params, next_idx = expr.to_sql(1)

        assert sql == '(t0."category" IN ($1, $2, $3) AND t0."status" = $4)'
        assert params == ["a", "b", "c", "active"]
        assert next_idx == 5
