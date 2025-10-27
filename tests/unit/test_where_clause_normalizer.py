"""
Comprehensive tests for WHERE clause normalization using SQL AST parsing.

This is critical for preventing false positives when PostgreSQL returns WHERE clauses
with extra parentheses (from pg_get_expr()) while generated DDL uses minimal form.
"""

from ff_storage.db.schema_sync.normalizer import SchemaNormalizer


class TestWhereClauseSimple:
    """Test normalization of simple WHERE clauses."""

    def test_normalize_simple_condition_no_parens(self):
        """Test that simple condition without parens remains unchanged."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("deleted_at IS NULL")
        assert result == "deleted_at IS NULL"

    def test_normalize_simple_condition_with_outer_parens(self):
        """Test that outer parentheses are stripped from simple conditions."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(deleted_at IS NULL)")
        assert result == "deleted_at IS NULL"

    def test_normalize_simple_condition_with_double_parens(self):
        """Test that double outer parentheses are stripped."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("((deleted_at IS NULL))")
        assert result == "deleted_at IS NULL"

    def test_normalize_equality_condition(self):
        """Test normalization of equality condition."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(status = 'active')")
        assert result == "status = 'active'"

    def test_normalize_comparison_condition(self):
        """Test normalization of comparison condition."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(age > 18)")
        assert result == "age > 18"

    def test_normalize_none_where_clause(self):
        """Test that None WHERE clause returns None."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause(None)
        assert result is None

    def test_normalize_empty_where_clause(self):
        """Test that empty WHERE clause returns None."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("")
        assert result is None

    def test_normalize_whitespace_only_where_clause(self):
        """Test that whitespace-only WHERE clause returns None."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("   ")
        assert result is None


class TestWhereClauseCompound:
    """Test normalization of compound WHERE clauses with AND/OR."""

    def test_normalize_and_condition_no_parens(self):
        """Test that AND condition without parens remains unchanged."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("valid_to IS NULL AND deleted_at IS NULL")
        assert result == "valid_to IS NULL AND deleted_at IS NULL"

    def test_normalize_and_condition_with_outer_parens(self):
        """Test that outer parens are stripped from AND condition."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(valid_to IS NULL AND deleted_at IS NULL)")
        assert result == "valid_to IS NULL AND deleted_at IS NULL"

    def test_normalize_and_condition_with_individual_parens(self):
        """
        Test that individual condition parens are stripped when not needed.

        PostgreSQL pg_get_expr() returns: ((valid_to IS NULL) AND (deleted_at IS NULL))
        Generated DDL uses: valid_to IS NULL AND deleted_at IS NULL

        These should be normalized to the same form.
        """
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("((valid_to IS NULL) AND (deleted_at IS NULL))")
        assert result == "valid_to IS NULL AND deleted_at IS NULL"

    def test_normalize_or_condition_no_parens(self):
        """Test that OR condition without parens remains unchanged."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("status = 'active' OR status = 'pending'")
        assert result == "status = 'active' OR status = 'pending'"

    def test_normalize_or_condition_with_outer_parens(self):
        """Test that outer parens are stripped from OR condition."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(status = 'active' OR status = 'pending')")
        assert result == "status = 'active' OR status = 'pending'"

    def test_normalize_triple_and_condition(self):
        """Test normalization of three conditions joined by AND."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("((a IS NULL) AND (b IS NULL) AND (c IS NULL))")
        assert result == "a IS NULL AND b IS NULL AND c IS NULL"


class TestWhereClausePrecedence:
    """Test that logical precedence is preserved (CRITICAL for correctness)."""

    def test_preserve_precedence_or_then_and(self):
        """
        Test that parentheses are preserved when needed for precedence.

        "(a OR b) AND c" is NOT the same as "a OR b AND c"
        Due to operator precedence (AND binds tighter than OR):
        - "(a OR b) AND c" means: (a OR b) AND c
        - "a OR b AND c" means: a OR (b AND c)

        The parentheses MUST be preserved.
        """
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(a OR b) AND c")
        # Parentheses MUST remain to preserve precedence
        assert result == "(a OR b) AND c"

    def test_preserve_precedence_and_then_or(self):
        """
        Test precedence with AND inside OR.

        "a OR (b AND c)" can be simplified to "a OR b AND c"
        because AND binds tighter than OR anyway.
        """
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("a OR (b AND c)")
        # Parens can be removed (AND binds tighter anyway)
        assert result == "a OR b AND c"

    def test_preserve_precedence_complex_mixed(self):
        """Test complex mixed precedence."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(a OR b) AND (c OR d)")
        # Both sets of parens needed for precedence
        assert result == "(a OR b) AND (c OR d)"

    def test_strip_unnecessary_parens_same_operator(self):
        """Test that unnecessary parens with same operator are stripped."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(a AND b) AND c")
        # Parens not needed (AND is associative, same precedence)
        assert result == "a AND b AND c"

    def test_strip_unnecessary_parens_nested_same_operator(self):
        """Test that nested unnecessary parens are stripped."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("((a OR b) OR c)")
        # Parens not needed (OR is associative, same precedence)
        assert result == "a OR b OR c"


class TestWhereClauseCase:
    """Test case normalization in WHERE clauses."""

    def test_normalize_keywords_uppercase(self):
        """Test that SQL keywords are normalized to uppercase."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("deleted_at is null and valid_to is null")
        assert result == "deleted_at IS NULL AND valid_to IS NULL"

    def test_normalize_identifiers_lowercase(self):
        """Test that identifiers are normalized to lowercase."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("DELETED_AT IS NULL")
        assert result == "deleted_at IS NULL"

    def test_normalize_mixed_case(self):
        """Test normalization of mixed case WHERE clause."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(Status = 'active' AND DeletedAt IS null)")
        assert result == "status = 'active' AND deletedat IS NULL"


class TestWhereClauseWhitespace:
    """Test whitespace normalization in WHERE clauses."""

    def test_normalize_extra_spaces(self):
        """Test that extra spaces are collapsed to single space."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("deleted_at    IS    NULL")
        assert result == "deleted_at IS NULL"

    def test_normalize_leading_trailing_spaces(self):
        """Test that leading/trailing spaces are stripped."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("  deleted_at IS NULL  ")
        assert result == "deleted_at IS NULL"

    def test_normalize_spaces_around_operators(self):
        """Test that spaces around operators are normalized."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("age>18")
        assert result == "age > 18"

    def test_normalize_spaces_around_parentheses(self):
        """Test that spaces around parentheses are normalized."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("( deleted_at IS NULL )")
        assert result == "deleted_at IS NULL"


class TestWhereClauseRealWorldCases:
    """Test real-world WHERE clauses from production databases."""

    def test_postgresql_pg_get_expr_format(self):
        """
        Test the exact format returned by PostgreSQL pg_get_expr().

        This is the production bug case from InsurX data service.
        """
        normalizer = SchemaNormalizer()

        # Format from pg_get_expr (what DB returns)
        from_db = "((valid_to IS NULL) AND (deleted_at IS NULL))"

        # Format from generated DDL (what we generate)
        from_ddl = "valid_to IS NULL AND deleted_at IS NULL"

        # Both should normalize to the same form
        assert normalizer.normalize_where_clause(from_db) == normalizer.normalize_where_clause(
            from_ddl
        )

    def test_postgresql_single_condition(self):
        """Test PostgreSQL single condition with outer parens."""
        normalizer = SchemaNormalizer()

        from_db = "(deleted_at IS NULL)"
        from_ddl = "deleted_at IS NULL"

        assert normalizer.normalize_where_clause(from_db) == normalizer.normalize_where_clause(
            from_ddl
        )

    def test_soft_delete_pattern(self):
        """Test common soft-delete WHERE clause pattern."""
        normalizer = SchemaNormalizer()

        # Various formats of the same condition
        format1 = "(deleted_at IS NULL)"
        format2 = "deleted_at IS NULL"
        format3 = "((deleted_at IS NULL))"

        norm1 = normalizer.normalize_where_clause(format1)
        norm2 = normalizer.normalize_where_clause(format2)
        norm3 = normalizer.normalize_where_clause(format3)

        assert norm1 == norm2 == norm3 == "deleted_at IS NULL"

    def test_current_version_pattern_scd2(self):
        """Test SCD2 current version WHERE clause pattern."""
        normalizer = SchemaNormalizer()

        # PostgreSQL format
        from_db = "((valid_to IS NULL) AND (deleted_at IS NULL))"

        # Generated format (from scd2.py line 98)
        from_ddl = "valid_to IS NULL AND deleted_at IS NULL"

        norm_db = normalizer.normalize_where_clause(from_db)
        norm_ddl = normalizer.normalize_where_clause(from_ddl)

        assert norm_db == norm_ddl == "valid_to IS NULL AND deleted_at IS NULL"

    def test_partial_index_with_status(self):
        """Test partial index with status filter."""
        normalizer = SchemaNormalizer()

        from_db = "(status = 'active')"
        from_ddl = "status = 'active'"

        assert normalizer.normalize_where_clause(from_db) == normalizer.normalize_where_clause(
            from_ddl
        )

    def test_complex_multi_tenant_filter(self):
        """Test complex multi-tenant WHERE clause."""
        normalizer = SchemaNormalizer()

        where = "((tenant_id = current_tenant_id()) AND (deleted_at IS NULL))"
        result = normalizer.normalize_where_clause(where)

        # Should strip outer parens but preserve structure
        # Function calls should be preserved (may be uppercased)
        assert "current_tenant_id()" in result.lower()
        assert "deleted_at IS NULL" in result
        assert "AND" in result


class TestWhereClauseEdgeCases:
    """Test edge cases and unusual WHERE clause formats."""

    def test_normalize_with_function_calls(self):
        """Test WHERE clause with function calls."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(LOWER(email) = 'test@example.com')")
        assert result == "LOWER(email) = 'test@example.com'"

    def test_normalize_with_nested_functions(self):
        """Test WHERE clause with nested function calls."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(LENGTH(TRIM(name)) > 0)")
        assert result == "LENGTH(TRIM(name)) > 0"

    def test_normalize_with_in_clause(self):
        """Test WHERE clause with IN operator - must produce valid SQL."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(status IN ('active', 'pending'))")
        # Must produce complete, valid SQL with closing parenthesis
        assert result == "status IN ( 'active' , 'pending' )"

    def test_normalize_with_between(self):
        """Test WHERE clause with BETWEEN operator."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(age BETWEEN 18 AND 65)")
        assert result == "age BETWEEN 18 AND 65"

    def test_normalize_with_like(self):
        """Test WHERE clause with LIKE operator."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(email LIKE '%@example.com')")
        assert result == "email LIKE '%@example.com'"

    def test_normalize_with_not(self):
        """Test WHERE clause with NOT operator."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(NOT deleted)")
        assert result == "NOT deleted"

    def test_normalize_with_is_not_null(self):
        """Test WHERE clause with IS NOT NULL."""
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("(email IS NOT NULL)")
        assert result == "email IS NOT NULL"


class TestWhereClauseAtomicConditionsWithParentheses:
    """
    Test atomic conditions that contain internal parentheses.

    These tests expose the bug in _parse_condition that stops at ')'
    without tracking parenthesis depth, causing truncated output.
    """

    def test_normalize_in_clause_preserves_closing_paren(self):
        """
        Test that IN clause with string values preserves closing parenthesis.

        Bug: _parse_condition stops at first ')' inside the IN list,
        producing invalid SQL: "status IN ( 'active' , 'pending'"

        Expected: "status IN ( 'active' , 'pending' )"
        """
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("status IN ('active','pending')")
        assert result == "status IN ( 'active' , 'pending' )"
        # Verify it's valid SQL by counting parentheses
        assert result.count("(") == result.count(")")

    def test_normalize_in_clause_numeric(self):
        """
        Test that IN clause with numeric values preserves closing parenthesis.

        Bug: Same as above but with numbers instead of strings.

        Expected: "age IN ( 18 , 21 , 65 )"
        """
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("age IN (18, 21, 65)")
        assert result == "age IN ( 18 , 21 , 65 )"
        # Verify it's valid SQL by counting parentheses
        assert result.count("(") == result.count(")")

    def test_normalize_not_with_or_expression(self):
        """
        Test that NOT with internal OR expression preserves structure.

        Bug: _parse_condition stops at ')' and treats 'OR' as binary operator,
        producing invalid SQL: "NOT ( deleted_at IS NULL OR disabled"

        Expected: "NOT ( deleted_at IS NULL OR disabled )"
        """
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("NOT (deleted_at IS NULL OR disabled)")
        assert result == "NOT ( deleted_at IS NULL OR disabled )"
        # Verify it's valid SQL by counting parentheses
        assert result.count("(") == result.count(")")

    def test_normalize_not_with_and_expression(self):
        """
        Test that NOT with internal AND expression preserves structure.

        Bug: Same as above but with AND instead of OR.

        Expected: "NOT ( active AND verified )"
        """
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("NOT (active AND verified)")
        assert result == "NOT ( active AND verified )"
        # Verify it's valid SQL by counting parentheses
        assert result.count("(") == result.count(")")

    def test_normalize_between_in_not(self):
        """
        Test that NOT BETWEEN preserves closing parenthesis.

        Bug: BETWEEN contains 'AND' keyword which might cause early termination.

        Expected: "NOT ( age BETWEEN 18 AND 65 )"
        """
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("NOT (age BETWEEN 18 AND 65)")
        assert result == "NOT ( age BETWEEN 18 AND 65 )"
        # Verify it's valid SQL by counting parentheses
        assert result.count("(") == result.count(")")

    def test_normalize_nested_function_with_in(self):
        """
        Test complex case: function call with IN clause.

        Expected: "LOWER ( status ) IN ( 'active' , 'pending' )"
        """
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause("LOWER(status) IN ('active', 'pending')")
        # Verify both function and IN clause have matching parens
        assert result.count("(") == result.count(")")
        assert "LOWER" in result
        assert "IN" in result

    def test_normalize_in_clause_with_outer_and(self):
        """
        Test IN clause combined with AND to ensure correct precedence.

        Expected: "status IN ( 'active' , 'pending' ) AND deleted_at IS NULL"
        """
        normalizer = SchemaNormalizer()
        result = normalizer.normalize_where_clause(
            "status IN ('active', 'pending') AND deleted_at IS NULL"
        )
        assert result.count("(") == result.count(")")
        assert "IN" in result
        assert "AND" in result
        assert "deleted_at IS NULL" in result
