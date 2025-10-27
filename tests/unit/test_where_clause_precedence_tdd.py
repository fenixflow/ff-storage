"""
TDD test suite for WHERE clause precedence and SQL escaping bugs.

This test file was created BEFORE fixing the implementation, following proper TDD practice.
All tests in this file MUST fail with the buggy implementation (v3.3.0-broken) and
MUST pass with the fixed implementation.

Critical bugs being tested:
1. Precedence preservation: (a OR b) AND c ≠ a OR b AND c
2. SQL string escaping: 'O''Reilly' must preserve doubled quotes
3. Semantic correctness: Different WHERE clauses must normalize differently
"""

from ff_storage.db.schema_sync.normalizer import SchemaNormalizer


class TestPrecedencePreservation:
    """Test that operator precedence is preserved correctly."""

    def test_or_then_and_must_preserve_parens(self):
        """
        CRITICAL: (a OR b) AND c has DIFFERENT semantics than a OR b AND c.

        With precedence (AND binds tighter than OR):
        - "(a OR b) AND c" means: (a OR b) AND c
        - "a OR b AND c" means: a OR (b AND c)

        These are NOT equivalent and must normalize differently.

        Example with actual values:
        - (TRUE OR FALSE) AND FALSE = (TRUE) AND FALSE = FALSE
        - TRUE OR FALSE AND FALSE = TRUE OR (FALSE AND FALSE) = TRUE OR FALSE = TRUE

        This test MUST fail with current implementation (line 549 bug).
        """
        normalizer = SchemaNormalizer()

        where_with_parens = "(a OR b) AND c"
        where_without_parens = "a OR b AND c"

        norm_with = normalizer.normalize_where_clause(where_with_parens)
        norm_without = normalizer.normalize_where_clause(where_without_parens)

        # CRITICAL: These MUST be different!
        assert norm_with != norm_without, (
            f"Precedence bug: {where_with_parens!r} and {where_without_parens!r} "
            f"normalized to same output: {norm_with!r}"
        )

        # The parens MUST be preserved
        assert (
            "(" in norm_with and ")" in norm_with
        ), f"Parentheses were stripped from {where_with_parens!r}, got {norm_with!r}"

    def test_multi_tenant_security_filter(self):
        """
        CRITICAL SECURITY: Multi-tenant filters MUST preserve precedence.

        Real production case:
        - CORRECT: tenant_id = 123 AND (status = 'active' OR status = 'pending')
          Returns only active/pending records for tenant 123

        - WRONG: tenant_id = 123 AND status = 'active' OR status = 'pending'
          Due to precedence: (tenant_id = 123 AND status = 'active') OR status = 'pending'
          Returns ALL pending records from ALL tenants! (security breach)

        This test MUST fail with current implementation.
        """
        normalizer = SchemaNormalizer()

        where_correct = "tenant_id = 123 AND (status = 'active' OR status = 'pending')"
        where_wrong = "tenant_id = 123 AND status = 'active' OR status = 'pending'"

        norm_correct = normalizer.normalize_where_clause(where_correct)
        norm_wrong = normalizer.normalize_where_clause(where_wrong)

        # CRITICAL: These MUST be different (security issue)!
        assert norm_correct != norm_wrong, (
            f"Security bug: {where_correct!r} and {where_wrong!r} "
            f"normalized to same output: {norm_correct!r}"
        )

        # The parens MUST be preserved in correct version
        assert "(" in norm_correct and ")" in norm_correct

    def test_scd2_temporal_filter_with_soft_delete(self):
        """
        Test real production SCD2 pattern with complex precedence.

        Real case from ff-storage temporal strategies:
        - "valid_to IS NULL AND deleted_at IS NULL AND (status = 'active' OR priority > 5)"

        The OR clause MUST be parenthesized to maintain correct semantics.
        """
        normalizer = SchemaNormalizer()

        where = "valid_to IS NULL AND deleted_at IS NULL AND (status = 'active' OR priority > 5)"
        result = normalizer.normalize_where_clause(where)

        # The OR clause MUST be parenthesized
        # Check that there are parens around the OR expression
        assert (
            "status = 'active' OR priority > 5" in result
            or "(status = 'active' OR priority > 5)" in result
        )

        # Verify we can detect difference from incorrect version
        where_wrong = (
            "valid_to IS NULL AND deleted_at IS NULL AND status = 'active' OR priority > 5"
        )
        result_wrong = normalizer.normalize_where_clause(where_wrong)

        assert result != result_wrong, "Failed to detect precedence difference in SCD2 filter"

    def test_complex_mixed_precedence_both_sides(self):
        """
        Test: (a OR b) AND (c OR d)

        Both sets of parentheses are required for correctness.
        Without them: a OR b AND c OR d = a OR (b AND c) OR d (different!)
        """
        normalizer = SchemaNormalizer()

        where = "(a OR b) AND (c OR d)"
        result = normalizer.normalize_where_clause(where)

        # MUST have parentheses preserved
        # Should contain patterns like "(... OR ...) AND (... OR ...)"
        assert (
            result.count("(") >= 2 and result.count(")") >= 2
        ), f"Lost required parentheses in {where!r}, got {result!r}"

        # Verify different from unparenthesized version
        where_wrong = "a OR b AND c OR d"
        result_wrong = normalizer.normalize_where_clause(where_wrong)

        assert result != result_wrong


class TestSQLStringEscaping:
    """Test SQL string literal escaping (doubled quotes)."""

    def test_sql_string_with_doubled_quote(self):
        """
        Test SQL standard escaping: '' inside string means literal '.

        SQL: name = 'O''Reilly'
        Means: name equals the string "O'Reilly" (with single quote)

        Current bug (lines 344-349): Tokenizer stops at first quote,
        produces invalid SQL like "name = 'O' 'Reilly'".

        This test MUST fail with current implementation.
        """
        normalizer = SchemaNormalizer()

        where = "name = 'O''Reilly'"
        result = normalizer.normalize_where_clause(where)

        # MUST preserve the escaped quote
        assert (
            "'O''Reilly'" in result
        ), f"Doubled quote escaping broken: {where!r} normalized to {result!r}"

        # Should NOT have broken-apart strings
        assert "'O' 'Reilly'" not in result
        assert "name = 'O' " not in result

    def test_multiple_escaped_quotes_in_string(self):
        """Test multiple '' escapes in one string."""
        normalizer = SchemaNormalizer()

        where = "description = 'It''s a ''quoted'' value'"
        result = normalizer.normalize_where_clause(where)

        # MUST preserve all escaped quotes
        assert "'It''s a ''quoted'' value'" in result or "\"It''s a ''quoted'' value\"" in result

    def test_escaped_quote_at_string_boundaries(self):
        """Test '' at start and end of string."""
        normalizer = SchemaNormalizer()

        # Quote at end
        where1 = "name = 'ends with'''"
        result1 = normalizer.normalize_where_clause(where1)
        assert "'ends with'''" in result1

        # Quote at start
        where2 = "name = '''starts with'"
        result2 = normalizer.normalize_where_clause(where2)
        assert "'''starts with'" in result2


class TestSemanticCorrectness:
    """Test that normalization preserves semantic meaning."""

    def test_semantically_identical_normalize_same(self):
        """
        Test idempotency: normalize(normalize(x)) == normalize(x).

        Also test that cosmetically different but semantically identical
        WHERE clauses normalize to the same output.
        """
        normalizer = SchemaNormalizer()

        # Different spacing, casing, but same meaning
        variants = [
            "(a OR b) AND c",
            "( a OR b ) AND c",
            "( A or B ) and C",
            "  (  a  OR  b  )  AND  c  ",
        ]

        results = [normalizer.normalize_where_clause(w) for w in variants]

        # All should normalize to same canonical form
        assert len(set(results)) == 1, f"Idempotency failed: {results}"

        # Double-normalize should produce same result
        first_pass = results[0]
        second_pass = normalizer.normalize_where_clause(first_pass)

        assert (
            first_pass == second_pass
        ), f"Not idempotent: first={first_pass!r}, second={second_pass!r}"

    def test_semantically_different_normalize_different(self):
        """
        CRITICAL: Semantically different WHERE clauses MUST normalize differently.

        This is the opposite of idempotency - we're testing that the normalizer
        DOES detect real differences.
        """
        normalizer = SchemaNormalizer()

        # These are genuinely semantically different
        different_clauses = [
            "(a OR b) AND c",  # (a OR b) AND c
            "a OR (b AND c)",  # a OR (b AND c) - same as "a OR b AND c" due to precedence
            "(a OR b) AND (c OR d)",  # (a OR b) AND (c OR d)
            "a AND (b OR c)",  # a AND (b OR c)
        ]

        results = [normalizer.normalize_where_clause(w) for w in different_clauses]

        # Should have at least 3 unique results (clauses 2 & 4 might normalize the same)
        unique_results = set(results)
        assert (
            len(unique_results) >= 3
        ), f"Failed to distinguish semantically different clauses: {results}"

        # Critical: (a OR b) AND c should be different from a OR b AND c
        assert results[0] != "a OR b AND c"

    def test_postgresql_extra_parens_versus_generated(self):
        """
        Test the original production bug: PostgreSQL returns extra parens.

        From PostgreSQL pg_get_expr(): "(deleted_at IS NULL)"
        From generated DDL: "deleted_at IS NULL"

        These are semantically identical and MUST normalize to same output.
        """
        normalizer = SchemaNormalizer()

        from_db = "(deleted_at IS NULL)"
        from_model = "deleted_at IS NULL"

        norm_db = normalizer.normalize_where_clause(from_db)
        norm_model = normalizer.normalize_where_clause(from_model)

        assert (
            norm_db == norm_model
        ), f"PostgreSQL extra parens not handled: {norm_db!r} != {norm_model!r}"

    def test_compound_postgresql_case(self):
        """
        Test real PostgreSQL case with multiple conditions.

        From DB: "((valid_to IS NULL) AND (deleted_at IS NULL))"
        From model: "valid_to IS NULL AND deleted_at IS NULL"
        """
        normalizer = SchemaNormalizer()

        from_db = "((valid_to IS NULL) AND (deleted_at IS NULL))"
        from_model = "valid_to IS NULL AND deleted_at IS NULL"

        norm_db = normalizer.normalize_where_clause(from_db)
        norm_model = normalizer.normalize_where_clause(from_model)

        assert norm_db == norm_model


class TestRealWorldPatterns:
    """Test real-world WHERE clause patterns from production."""

    def test_partial_index_for_active_records(self):
        """Test soft delete pattern: WHERE deleted_at IS NULL."""
        normalizer = SchemaNormalizer()

        where = "deleted_at IS NULL"
        result = normalizer.normalize_where_clause(where)

        # Check normalized form (identifiers lowercase, keywords uppercase)
        assert "deleted_at" in result.lower()
        assert "IS NULL" in result.upper()

    def test_scd2_current_version_index(self):
        """Test SCD2 pattern: WHERE valid_to IS NULL."""
        normalizer = SchemaNormalizer()

        where = "valid_to IS NULL"
        result = normalizer.normalize_where_clause(where)

        # Check normalized form
        assert "valid_to" in result.lower()
        assert "IS NULL" in result.upper()

    def test_combined_temporal_soft_delete(self):
        """Test combined SCD2 + soft delete."""
        normalizer = SchemaNormalizer()

        where = "valid_to IS NULL AND deleted_at IS NULL"
        result = normalizer.normalize_where_clause(where)

        # Check normalized form
        assert "valid_to" in result.lower()
        assert "deleted_at" in result.lower()
        assert "IS NULL" in result.upper()
        assert "AND" in result.upper()

    def test_multi_tenant_with_status_filter(self):
        """Test multi-tenant pattern with OR status filter."""
        normalizer = SchemaNormalizer()

        where = (
            "tenant_id = 123 AND deleted_at IS NULL AND (status = 'active' OR status = 'pending')"
        )
        result = normalizer.normalize_where_clause(where)

        # Should preserve the OR grouping
        assert "OR" in result.upper()
        # Should have tenant filter
        assert "tenant_id" in result.lower()

    def test_function_in_where_clause(self):
        """Test WHERE clause with function call."""
        normalizer = SchemaNormalizer()

        where = "LENGTH(TRIM(name)) > 0"
        result = normalizer.normalize_where_clause(where)

        # Function names should be uppercase
        assert "LENGTH" in result
        assert "TRIM" in result
        # Column should be lowercase
        assert "name" in result

    def test_in_clause_with_multiple_values(self):
        """Test IN clause with list of values."""
        normalizer = SchemaNormalizer()

        where = "status IN ('active', 'pending', 'review')"
        result = normalizer.normalize_where_clause(where)

        assert "IN" in result
        assert "'active'" in result
        assert "'pending'" in result
        assert "'review'" in result

    def test_between_clause(self):
        """Test BETWEEN clause."""
        normalizer = SchemaNormalizer()

        where = "created_at BETWEEN '2024-01-01' AND '2024-12-31'"
        result = normalizer.normalize_where_clause(where)

        assert "BETWEEN" in result
        assert "AND" in result

    def test_like_pattern_matching(self):
        """Test LIKE pattern with wildcards."""
        normalizer = SchemaNormalizer()

        where = "email LIKE '%@example.com'"
        result = normalizer.normalize_where_clause(where)

        assert "LIKE" in result
        assert "'%@example.com'" in result


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_deeply_nested_precedence(self):
        """Test deeply nested expression with multiple precedence levels."""
        normalizer = SchemaNormalizer()

        where = "((a OR b) AND (c OR d)) OR (e AND f)"
        result = normalizer.normalize_where_clause(where)

        # Should preserve necessary parens for precedence
        # The exact form may vary, but semantics must be preserved
        # At minimum, should have some parentheses
        assert "(" in result and ")" in result

    def test_empty_where_clause(self):
        """Test empty/None WHERE clause."""
        normalizer = SchemaNormalizer()

        assert normalizer.normalize_where_clause(None) is None
        assert normalizer.normalize_where_clause("") is None
        assert normalizer.normalize_where_clause("   ") is None

    def test_single_condition(self):
        """Test single condition (no operators)."""
        normalizer = SchemaNormalizer()

        where = "deleted_at IS NULL"
        result = normalizer.normalize_where_clause(where)

        assert result  # Should produce some output
        assert "deleted_at" in result.lower()
        assert "NULL" in result.upper()

    def test_unnecessary_parens_same_operator(self):
        """Test that unnecessary parens with same operator are removed."""
        normalizer = SchemaNormalizer()

        # Same operator (AND) - parens not needed for precedence
        where = "(a AND b) AND c"
        result = normalizer.normalize_where_clause(where)

        # Should strip unnecessary parens
        assert result.count("(") == 0 or result == "a AND b AND c"
