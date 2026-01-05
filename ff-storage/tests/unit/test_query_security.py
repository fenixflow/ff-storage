"""
Unit tests for SQL injection prevention in query builder.

Tests cover:
- B1: nulls validation in ordering.py
- B2: on_clause validation in builder.py
- B3: join_type validation in executor.py
- W8: ORDER BY direction and LIMIT/OFFSET validation
"""

import pytest


class TestOrderByClauseValidation:
    """Tests for OrderByClause SQL injection prevention (B1)."""

    def test_valid_direction_asc(self):
        """ASC direction should be accepted."""
        from ff_storage.query.ordering import OrderByClause

        clause = OrderByClause(field="created_at", direction="ASC")
        sql = clause.to_sql()
        assert "ASC" in sql
        assert "created_at" in sql

    def test_valid_direction_desc(self):
        """DESC direction should be accepted."""
        from ff_storage.query.ordering import OrderByClause

        clause = OrderByClause(field="created_at", direction="DESC")
        sql = clause.to_sql()
        assert "DESC" in sql

    def test_invalid_direction_raises(self):
        """Invalid direction should raise ValueError."""
        from ff_storage.query.ordering import OrderByClause

        clause = OrderByClause(field="created_at", direction="DROP TABLE users; --")
        with pytest.raises(ValueError, match="Invalid ORDER BY direction"):
            clause.to_sql()

    def test_valid_nulls_first(self):
        """NULLS FIRST should be accepted."""
        from ff_storage.query.ordering import OrderByClause

        clause = OrderByClause(field="name", direction="ASC", nulls="FIRST")
        sql = clause.to_sql()
        assert "NULLS FIRST" in sql

    def test_valid_nulls_last(self):
        """NULLS LAST should be accepted."""
        from ff_storage.query.ordering import OrderByClause

        clause = OrderByClause(field="name", direction="ASC", nulls="LAST")
        sql = clause.to_sql()
        assert "NULLS LAST" in sql

    def test_invalid_nulls_raises(self):
        """Invalid nulls value should raise ValueError."""
        from ff_storage.query.ordering import OrderByClause

        clause = OrderByClause(field="name", direction="ASC", nulls="DROP TABLE users; --")
        with pytest.raises(ValueError, match="Invalid NULLS value"):
            clause.to_sql()

    def test_sql_injection_in_nulls_blocked(self):
        """SQL injection via nulls parameter should be blocked."""
        from ff_storage.query.ordering import OrderByClause

        # Various SQL injection attempts
        injection_attempts = [
            "'; DROP TABLE users; --",
            "FIRST; DELETE FROM users; --",
            "LAST UNION SELECT * FROM passwords; --",
            "1=1 OR",
        ]

        for injection in injection_attempts:
            clause = OrderByClause(field="name", direction="ASC", nulls=injection)
            with pytest.raises(ValueError):
                clause.to_sql()


class TestJoinTypeValidation:
    """Tests for JOIN type SQL injection prevention (B2, B3)."""

    def test_valid_join_types_accepted(self):
        """Valid join types should be accepted."""
        from ff_storage.query.builder import Query

        # We need a minimal model class for testing
        class MockModel:
            __table_name__ = "test"
            __schema__ = "public"
            __temporal_strategy__ = "none"
            __soft_delete__ = False
            __multi_tenant__ = False

        valid_types = ["INNER", "LEFT", "RIGHT", "FULL", "CROSS"]

        for join_type in valid_types:
            query = Query(MockModel)
            query = query.join(MockModel, join_type=join_type)
            # Should not raise
            assert len(query._joins) == 1
            assert query._joins[0].join_type == join_type

    def test_invalid_join_type_raises(self):
        """Invalid join type should raise ValueError."""
        from ff_storage.query.builder import Query

        class MockModel:
            __table_name__ = "test"
            __schema__ = "public"
            __temporal_strategy__ = "none"
            __soft_delete__ = False
            __multi_tenant__ = False

        query = Query(MockModel)
        with pytest.raises(ValueError, match="Invalid join type"):
            query.join(MockModel, join_type="DROP TABLE; --")

    def test_sql_injection_in_join_type_blocked(self):
        """SQL injection via join_type should be blocked."""
        from ff_storage.query.builder import Query

        class MockModel:
            __table_name__ = "test"
            __schema__ = "public"
            __temporal_strategy__ = "none"
            __soft_delete__ = False
            __multi_tenant__ = False

        injection_attempts = [
            "INNER; DROP TABLE users; --",
            "LEFT UNION SELECT * FROM secrets",
            "'; DELETE FROM users WHERE '1'='1",
        ]

        for injection in injection_attempts:
            query = Query(MockModel)
            with pytest.raises(ValueError):
                query.join(MockModel, join_type=injection)


class TestOnClauseValidation:
    """Tests for ON clause SQL injection prevention (B2)."""

    def test_valid_on_clause_accepted(self):
        """Valid ON clause format should be accepted."""
        from ff_storage.query.builder import Query

        class MockModel:
            __table_name__ = "test"
            __schema__ = "public"
            __temporal_strategy__ = "none"
            __soft_delete__ = False
            __multi_tenant__ = False

        valid_clauses = [
            "t0.id = t1.author_id",
            't0."user_id" = t1."id"',
            "t0.tenant_id = t1.tenant_id",
        ]

        for on_clause in valid_clauses:
            query = Query(MockModel)
            query = query.join(MockModel, on=on_clause)
            # Should not raise
            assert len(query._joins) == 1

    def test_invalid_on_clause_raises(self):
        """Invalid ON clause format should raise ValueError."""
        from ff_storage.query.builder import Query

        class MockModel:
            __table_name__ = "test"
            __schema__ = "public"
            __temporal_strategy__ = "none"
            __soft_delete__ = False
            __multi_tenant__ = False

        invalid_clauses = [
            "1=1",  # Missing table aliases
            "t0.id = t1.id; DROP TABLE users; --",  # SQL injection
            "t0.id = t1.id OR 1=1",  # Extra conditions
            "SELECT * FROM users",  # Full query
        ]

        for on_clause in invalid_clauses:
            query = Query(MockModel)
            with pytest.raises(ValueError, match="Invalid ON clause"):
                query.join(MockModel, on=on_clause)


class TestLimitOffsetValidation:
    """Tests for LIMIT/OFFSET validation (W8)."""

    def test_valid_limit_offset_accepted(self):
        """Valid limit and offset values should be accepted."""
        from ff_storage.db.query_builder.base import QueryBuilder

        # Create a concrete implementation for testing
        class TestQueryBuilder(QueryBuilder):
            def quote_identifier(self, identifier):
                return f'"{identifier}"'

            def build_insert(self, table, data):
                pass

            def build_update(self, table, data, where):
                pass

            def build_where_clause(self, filters, base_param_count=0, operator="AND"):
                return "", []

        builder = TestQueryBuilder()

        # Test valid integer values
        sql, _ = builder.build_select("users", limit=10, offset=0)
        assert "LIMIT 10" in sql
        assert "OFFSET 0" in sql

        # Test large values
        sql, _ = builder.build_select("users", limit=1000000)
        assert "LIMIT 1000000" in sql

    def test_negative_limit_raises(self):
        """Negative limit should raise ValueError."""
        from ff_storage.db.query_builder.base import QueryBuilder

        class TestQueryBuilder(QueryBuilder):
            def quote_identifier(self, identifier):
                return f'"{identifier}"'

            def build_insert(self, table, data):
                pass

            def build_update(self, table, data, where):
                pass

            def build_where_clause(self, filters, base_param_count=0, operator="AND"):
                return "", []

        builder = TestQueryBuilder()

        with pytest.raises(ValueError, match="Must be non-negative"):
            builder.build_select("users", limit=-1)

    def test_invalid_limit_type_raises(self):
        """Non-integer limit should raise ValueError."""
        from ff_storage.db.query_builder.base import QueryBuilder

        class TestQueryBuilder(QueryBuilder):
            def quote_identifier(self, identifier):
                return f'"{identifier}"'

            def build_insert(self, table, data):
                pass

            def build_update(self, table, data, where):
                pass

            def build_where_clause(self, filters, base_param_count=0, operator="AND"):
                return "", []

        builder = TestQueryBuilder()

        with pytest.raises(ValueError, match="Must be a non-negative integer"):
            builder.build_select("users", limit="DROP TABLE users; --")

    def test_order_by_direction_validated(self):
        """ORDER BY direction should be validated."""
        from ff_storage.db.query_builder.base import QueryBuilder

        class TestQueryBuilder(QueryBuilder):
            def quote_identifier(self, identifier):
                return f'"{identifier}"'

            def build_insert(self, table, data):
                pass

            def build_update(self, table, data, where):
                pass

            def build_where_clause(self, filters, base_param_count=0, operator="AND"):
                return "", []

        builder = TestQueryBuilder()

        # Valid directions
        sql, _ = builder.build_select("users", order_by=["name ASC"])
        assert "ASC" in sql

        sql, _ = builder.build_select("users", order_by=["name DESC"])
        assert "DESC" in sql

        # Invalid direction should raise
        with pytest.raises(ValueError, match="Invalid ORDER BY direction"):
            builder.build_select("users", order_by=["name; DROP TABLE users; --"])


class TestLikePatternEscaping:
    """Tests for LIKE pattern escaping (security hardening)."""

    def test_percent_sign_escaped(self):
        """Percent sign should be escaped in LIKE patterns."""
        from ff_storage.query.expressions import FieldProxy

        expr = FieldProxy("discount").contains("100%")
        # The value should have the % escaped
        assert r"\%" in expr.value

    def test_underscore_escaped(self):
        """Underscore should be escaped in LIKE patterns."""
        from ff_storage.query.expressions import FieldProxy

        expr = FieldProxy("name").contains("user_name")
        # The value should have the _ escaped
        assert r"\_" in expr.value

    def test_backslash_escaped(self):
        """Backslash should be escaped in LIKE patterns."""
        from ff_storage.query.expressions import FieldProxy

        expr = FieldProxy("path").contains("C:\\Users")
        # The value should have the backslash escaped
        assert "\\\\" in expr.value

    def test_startswith_escapes_pattern(self):
        """startswith should escape special characters."""
        from ff_storage.query.expressions import FieldProxy

        expr = FieldProxy("name").startswith("100%_off")
        assert r"\%" in expr.value
        assert r"\_" in expr.value

    def test_endswith_escapes_pattern(self):
        """endswith should escape special characters."""
        from ff_storage.query.expressions import FieldProxy

        expr = FieldProxy("name").endswith("%discount")
        assert r"\%" in expr.value

    def test_icontains_escapes_pattern(self):
        """icontains should escape special characters."""
        from ff_storage.query.expressions import FieldProxy

        expr = FieldProxy("name").icontains("50%")
        assert r"\%" in expr.value

    def test_like_does_not_escape(self):
        """like() method should NOT escape (for advanced users)."""
        from ff_storage.query.expressions import FieldProxy

        expr = FieldProxy("name").like("%test%")
        # Raw pattern, no escaping
        assert expr.value == "%test%"


class TestOperatorValidation:
    """Tests for FilterExpression operator validation (security hardening)."""

    def test_valid_operators_accepted(self):
        """Valid operators should be accepted."""
        from ff_storage.query.expressions import FilterExpression

        valid_operators = ["=", "!=", "<", ">", "<=", ">=", "LIKE", "ILIKE", "IN", "NOT IN"]

        for op in valid_operators:
            expr = FilterExpression("field", op, "value")
            # Should not raise - just calling to_sql() triggers validation
            if op in ("IN", "NOT IN"):
                expr.value = ["a", "b"]  # IN requires list
            expr.to_sql(1)  # Should not raise

    def test_invalid_operator_raises(self):
        """Invalid operators should raise ValueError."""
        from ff_storage.query.expressions import FilterExpression

        invalid_operators = [
            "DROP TABLE",
            "; --",
            "= OR 1=1 --",
            "UNION SELECT",
        ]

        for op in invalid_operators:
            expr = FilterExpression("field", op, "value")
            with pytest.raises(ValueError, match="Invalid operator"):
                expr.to_sql(1)

    def test_sql_injection_in_operator_blocked(self):
        """SQL injection via operator should be blocked."""
        from ff_storage.query.expressions import FilterExpression

        # Various SQL injection attempts in operator field
        injection_attempts = [
            "'; DROP TABLE users; --",
            "= 1 UNION SELECT * FROM passwords --",
            "!= 1; DELETE FROM users WHERE 1=1; --",
        ]

        for injection in injection_attempts:
            expr = FilterExpression("field", injection, "value")
            with pytest.raises(ValueError):
                expr.to_sql(1)


class TestStrictValidation:
    """Tests for strict validation mode (B4)."""

    def test_strict_validation_default_true(self):
        """strict_validation should default to True."""
        # Check default value without instantiating (avoid connection)
        import dataclasses

        from ff_storage.db.connections.postgres import PostgresBase

        fields = {f.name: f for f in dataclasses.fields(PostgresBase)}
        assert fields["strict_validation"].default is True
