"""
Schema normalization framework for cross-database comparison.

This module provides a centralized, DRY approach to normalizing schema elements
before comparison. This eliminates false positives in schema drift detection
caused by cosmetic differences in formatting (case, whitespace, parentheses, etc.).

Architecture:
    - SchemaNormalizer: Provider-agnostic base class for all normalization
    - PostgresNormalizer: PostgreSQL-specific normalization (float types, booleans)
    - MySQLNormalizer: MySQL-specific normalization (future)
    - SQLServerNormalizer: SQL Server-specific normalization (future)

The normalization process follows the Canonical Form pattern:
    1. Provider-specific introspector returns raw DB values
    2. Normalizer converts to canonical (comparison-ready) form
    3. SchemaDiffer compares normalized values

This ensures consistent comparison across all providers and eliminates the
scattered normalization code that caused bugs in v3.2.x.
"""

import re
from dataclasses import replace
from typing import Optional

from .models import ColumnDefinition, ColumnType, IndexDefinition


class SchemaNormalizer:
    """
    Provider-agnostic schema normalization for comparison.

    This base class provides generic normalization that works across all
    database providers. Provider-specific subclasses override methods
    to handle provider-specific quirks (e.g., PostgreSQL float type aliases).

    All normalization is case-insensitive and whitespace-normalized to
    ensure consistent comparison.
    """

    # =========================================================================
    # Column Normalization
    # =========================================================================

    def normalize_column(self, col: ColumnDefinition) -> ColumnDefinition:
        """
        Normalize all column properties for comparison.

        Creates a new ColumnDefinition with normalized values while preserving
        the original column name (needed for SQL generation).

        Args:
            col: Original column definition

        Returns:
            New ColumnDefinition with normalized properties
        """
        return replace(
            col,
            default=self.normalize_default_value(col.default, col.column_type),
            native_type=self.normalize_native_type(col.native_type),
            references=self.normalize_references(col.references),
        )

    def normalize_default_value(
        self, default: Optional[str], col_type: ColumnType
    ) -> Optional[str]:
        """
        Normalize default values for consistent comparison.

        Normalization rules:
            - Boolean values: 'true'/'t'/'1' → 'TRUE', 'false'/'f'/'0' → 'FALSE'
            - NULL values: 'NULL'/'null'/'' → None
            - Whitespace: Strip leading/trailing, preserve internal
            - Case: Preserve for non-boolean values

        Args:
            default: Original default value string (or None)
            col_type: Column type (for boolean-specific normalization)

        Returns:
            Normalized default value or None
        """
        if default is None:
            return None

        # Strip whitespace
        default = default.strip()

        # Empty string → None
        if not default:
            return None

        # 'NULL' string → None (case-insensitive)
        if default.upper() == "NULL":
            return None

        # Boolean-specific normalization
        if col_type == ColumnType.BOOLEAN:
            default_lower = default.lower()

            # True variants
            if default_lower in ("true", "t", "1", "yes", "y"):
                return "TRUE"

            # False variants
            if default_lower in ("false", "f", "0", "no", "n"):
                return "FALSE"

        # For non-boolean types, return trimmed value
        return default

    def normalize_native_type(self, native_type: Optional[str]) -> Optional[str]:
        """
        Normalize native (provider-specific) type names.

        Normalization rules:
            - Case: Convert to uppercase
            - Whitespace: Collapse multiple spaces to single space
            - Parameters: Normalize whitespace inside parentheses
            - Strip leading/trailing whitespace

        Examples:
            'varchar' → 'VARCHAR'
            'DOUBLE  PRECISION' → 'DOUBLE PRECISION'
            'DECIMAL( 10 , 2 )' → 'DECIMAL(10,2)'

        Args:
            native_type: Original type name (e.g., 'varchar', 'DECIMAL(10,2)')

        Returns:
            Normalized type name or None
        """
        if native_type is None:
            return None

        # Strip leading/trailing whitespace
        native_type = native_type.strip()

        if not native_type:
            return None

        # Convert to uppercase
        native_type = native_type.upper()

        # Collapse multiple spaces to single space
        native_type = re.sub(r"\s+", " ", native_type)

        # Normalize whitespace in parameters: 'DECIMAL( 10 , 2 )' → 'DECIMAL(10,2)'
        native_type = re.sub(r"\s*\(\s*", "(", native_type)  # '( ' → '('
        native_type = re.sub(r"\s*\)\s*", ")", native_type)  # ' )' → ')'
        native_type = re.sub(r"\s*,\s*", ",", native_type)  # ' , ' → ','

        return native_type

    def normalize_identifier(self, identifier: Optional[str]) -> Optional[str]:
        """
        Normalize SQL identifiers (table, column, index names).

        Normalization rules:
            - Case: Convert to lowercase (standard SQL behavior)
            - Quotes: Strip double quotes

        Args:
            identifier: Original identifier (e.g., 'MyTable', '"my_table"')

        Returns:
            Normalized identifier or None
        """
        if identifier is None:
            return None

        # Strip quotes
        identifier = identifier.strip('"')

        # Convert to lowercase
        return identifier.lower()

    def normalize_references(self, references: Optional[str]) -> Optional[str]:
        """
        Normalize foreign key references.

        Normalization rules:
            - Case: Convert to lowercase
            - Preserve structure: 'schema.table(column)'

        Args:
            references: Original reference (e.g., 'Users(id)', 'public.Users(id)')

        Returns:
            Normalized reference or None
        """
        if references is None:
            return None

        # Convert to lowercase
        return references.lower()

    # =========================================================================
    # Index Normalization
    # =========================================================================

    def normalize_index(self, idx: IndexDefinition) -> IndexDefinition:
        """
        Normalize all index properties for comparison.

        Creates a new IndexDefinition with normalized values while preserving
        column order (order matters for SQL indexes).

        Args:
            idx: Original index definition

        Returns:
            New IndexDefinition with normalized properties
        """
        return replace(
            idx,
            index_type=self.normalize_index_type(idx.index_type),
            where_clause=self.normalize_where_clause(idx.where_clause),
            # NOTE: columns NOT normalized - order matters in SQL!
        )

    def normalize_index_type(self, index_type: Optional[str]) -> Optional[str]:
        """
        Normalize index type for comparison.

        Normalization rules:
            - Case: Convert to uppercase

        Args:
            index_type: Original index type (e.g., 'btree', 'hash')

        Returns:
            Normalized index type or None
        """
        if index_type is None:
            return None

        return index_type.upper()

    def normalize_where_clause(self, where: Optional[str]) -> Optional[str]:
        """
        Normalize WHERE clause using SQL AST parsing.

        This is the most complex normalization because WHERE clauses can
        have cosmetic differences while being semantically identical:

        Examples (all equivalent):
            - 'deleted_at IS NULL'
            - '(deleted_at IS NULL)'
            - '((deleted_at IS NULL))'

        Examples (NOT equivalent - precedence matters):
            - '(a OR b) AND c' ≠ 'a OR b AND c'
            - Due to operator precedence: AND binds tighter than OR

        Normalization rules:
            1. Parse into AST (Abstract Syntax Tree)
            2. Strip unnecessary outer parentheses
            3. Preserve parentheses needed for logical precedence
            4. Normalize keywords to uppercase (AND, OR, IS, NULL)
            5. Normalize identifiers to lowercase
            6. Normalize whitespace
            7. Rebuild minimal form

        Args:
            where: Original WHERE clause (or None)

        Returns:
            Normalized WHERE clause or None
        """
        if where is None:
            return None

        where = where.strip()

        if not where:
            # Return None for empty strings to maintain consistency:
            # - SQL partial index: WHERE deleted_at IS NULL (where_clause = "deleted_at IS NULL")
            # - SQL full index: no WHERE clause (where_clause = None)
            # - Empty string treated as "no WHERE clause" to avoid None != "" false positives
            # in IndexDefinition comparison (base.py:340)
            return None

        # Parse WHERE clause using recursive descent parser
        ast = self._parse_where_clause(where)

        # Rebuild normalized form from AST
        return self._rebuild_where_clause(ast)

    # =========================================================================
    # WHERE Clause Parser (Recursive Descent)
    # =========================================================================

    def _parse_where_clause(self, where: str) -> "WhereClauseAST":
        """
        Parse WHERE clause into Abstract Syntax Tree.

        Uses recursive descent parser to handle:
            - Binary operators (AND, OR)
            - Parenthesized expressions
            - Atomic conditions (column IS NULL, status = 'active', etc.)

        Args:
            where: WHERE clause string

        Returns:
            WhereClauseAST representing the parsed structure
        """
        # Tokenize
        tokens = self._tokenize_where_clause(where)

        # Parse
        ast, _ = self._parse_or_expression(tokens, 0)

        return ast

    def _tokenize_where_clause(self, where: str) -> list[str]:
        """
        Tokenize WHERE clause into list of tokens.

        Tokens include:
            - Parentheses: '(', ')'
            - Keywords: AND, OR, IS, NULL, NOT, BETWEEN, IN, LIKE
            - Operators: =, >, <, >=, <=, <>
            - Identifiers: column_name, table.column
            - Literals: 'string', 123, TRUE, FALSE
            - Function calls: LOWER(email), current_tenant_id()

        Function calls are treated as atomic tokens to preserve their structure.

        Args:
            where: WHERE clause string

        Returns:
            List of tokens
        """
        tokens = []
        i = 0

        while i < len(where):
            # Skip whitespace
            if where[i].isspace():
                i += 1
                continue

            # String literals (single quotes) - handle SQL escaping ('')
            if where[i] == "'":
                j = i + 1
                while j < len(where):
                    if where[j] == "'":
                        # Check if this is an escaped quote ('')
                        if j + 1 < len(where) and where[j + 1] == "'":
                            # Doubled quote - skip both and continue
                            j += 2
                            continue
                        else:
                            # End of string
                            break
                    j += 1
                tokens.append(where[i : j + 1])
                i = j + 1
                continue

            # String literals (double quotes) - handle SQL escaping ("")
            if where[i] == '"':
                j = i + 1
                while j < len(where):
                    if where[j] == '"':
                        # Check if this is an escaped quote ("")
                        if j + 1 < len(where) and where[j + 1] == '"':
                            # Doubled quote - skip both and continue
                            j += 2
                            continue
                        else:
                            # End of string
                            break
                    j += 1
                tokens.append(where[i : j + 1])
                i = j + 1
                continue

            # Two-character operators
            if i + 1 < len(where) and where[i : i + 2] in (">=", "<=", "<>", "!="):
                tokens.append(where[i : i + 2])
                i += 2
                continue

            # Single-character operators and parentheses
            if where[i] in "()=<>,":
                tokens.append(where[i])
                i += 1
                continue

            # Identifiers, keywords, numbers, or function calls
            j = i
            paren_depth = 0
            while j < len(where):
                if where[j] == "(":
                    paren_depth += 1
                    j += 1
                elif where[j] == ")":
                    if paren_depth > 0:
                        paren_depth -= 1  # FIX: decrement, not increment!
                        j += 1
                        # If we've closed all parens, end the function call
                        if paren_depth == 0:
                            break
                    else:
                        # This closing paren is not part of our token
                        break
                elif where[j].isspace():
                    if paren_depth > 0:
                        # Inside function call, continue
                        j += 1
                    else:
                        # Outside function call, end token
                        break
                elif where[j] in "=<>,":
                    # Operator ends token (unless inside function)
                    if paren_depth > 0:
                        j += 1
                    else:
                        break
                else:
                    j += 1

            if j > i:
                token = where[i:j].strip()
                if token:
                    tokens.append(token)
                i = j
            else:
                i += 1

        return tokens

    def _parse_or_expression(self, tokens: list[str], pos: int) -> tuple["WhereClauseAST", int]:
        """
        Parse OR expression (lowest precedence).

        Grammar:
            or_expr := and_expr (OR and_expr)*

        Args:
            tokens: List of tokens
            pos: Current position in token list

        Returns:
            Tuple of (AST node, new position)
        """
        left, pos = self._parse_and_expression(tokens, pos)

        while pos < len(tokens) and tokens[pos].upper() == "OR":
            pos += 1  # Consume 'OR'
            right, pos = self._parse_and_expression(tokens, pos)
            left = BinaryOp(left=left, operator="OR", right=right)

        return left, pos

    def _parse_and_expression(self, tokens: list[str], pos: int) -> tuple["WhereClauseAST", int]:
        """
        Parse AND expression (higher precedence than OR).

        Grammar:
            and_expr := primary (AND primary)*

        Args:
            tokens: List of tokens
            pos: Current position in token list

        Returns:
            Tuple of (AST node, new position)
        """
        left, pos = self._parse_primary(tokens, pos)

        while pos < len(tokens) and tokens[pos].upper() == "AND":
            pos += 1  # Consume 'AND'
            right, pos = self._parse_primary(tokens, pos)
            left = BinaryOp(left=left, operator="AND", right=right)

        return left, pos

    def _parse_primary(self, tokens: list[str], pos: int) -> tuple["WhereClauseAST", int]:
        """
        Parse primary expression (parenthesized or atomic condition).

        Grammar:
            primary := '(' or_expr ')' | condition

        Args:
            tokens: List of tokens
            pos: Current position in token list

        Returns:
            Tuple of (AST node, new position)
        """
        if pos >= len(tokens):
            raise ValueError("Unexpected end of WHERE clause")

        # Parenthesized expression
        if tokens[pos] == "(":
            pos += 1  # Consume '('
            expr, pos = self._parse_or_expression(tokens, pos)

            if pos >= len(tokens) or tokens[pos] != ")":
                raise ValueError(f"Expected ')' at position {pos}")

            pos += 1  # Consume ')'
            return Parenthesized(inner=expr), pos

        # Atomic condition - consume until we hit an operator or closing paren
        return self._parse_condition(tokens, pos)

    def _parse_condition(self, tokens: list[str], pos: int) -> tuple["WhereClauseAST", int]:
        """
        Parse atomic condition (everything that's not AND/OR/parens).

        Examples:
            - 'deleted_at IS NULL'
            - 'status = \'active\''
            - 'age > 18'
            - 'email LIKE \'%@example.com\''
            - 'status IN (\'active\', \'pending\')'  # Contains internal parens
            - 'NOT (deleted_at IS NULL OR disabled)'  # Contains internal parens and operators

        Args:
            tokens: List of tokens
            pos: Current position in token list

        Returns:
            Tuple of (Condition node, new position)
        """
        condition_tokens = []
        paren_depth = 0  # Track parenthesis nesting within the atomic condition

        while pos < len(tokens):
            token = tokens[pos]

            # Track parenthesis depth (same pattern as tokenizer at lines 398-427)
            if token == "(":
                paren_depth += 1
                condition_tokens.append(token)
                pos += 1
            elif token == ")":
                if paren_depth > 0:
                    # This closing paren is part of the atomic condition (e.g., IN clause)
                    paren_depth -= 1
                    condition_tokens.append(token)
                    pos += 1
                else:
                    # This closing paren ends a parenthesized group at higher level
                    break
            # Stop at binary operators only when not inside parens
            elif token.upper() in ("AND", "OR") and paren_depth == 0:
                break
            else:
                condition_tokens.append(token)
                pos += 1

        # Rebuild condition string
        condition_str = " ".join(condition_tokens)

        return Condition(expression=condition_str), pos

    def _rebuild_where_clause(self, ast: "WhereClauseAST", parent_op: Optional[str] = None) -> str:
        """
        Rebuild normalized WHERE clause from AST.

        Normalization during rebuild:
            1. Strip unnecessary parentheses
            2. Normalize keywords to uppercase
            3. Normalize identifiers to lowercase
            4. Normalize whitespace

        Args:
            ast: WHERE clause AST
            parent_op: Parent operator context (AND/OR) for precedence checking

        Returns:
            Normalized WHERE clause string
        """
        if isinstance(ast, Condition):
            return self._normalize_condition(ast.expression)

        elif isinstance(ast, Parenthesized):
            # Unwrap and rebuild inner expression
            inner_rebuilt = self._rebuild_where_clause(ast.inner, parent_op)

            # Check if parentheses are needed for precedence
            # Get the operator of the inner expression
            inner_op = self._get_top_level_operator(ast.inner)

            # If inner operator has lower precedence than parent, preserve parens
            if parent_op and inner_op and self._has_lower_precedence(inner_op, parent_op):
                return f"({inner_rebuilt})"

            # Otherwise, strip unnecessary parens
            return inner_rebuilt

        elif isinstance(ast, BinaryOp):
            left_str = self._rebuild_where_clause(ast.left, ast.operator)
            right_str = self._rebuild_where_clause(ast.right, ast.operator)

            # Add parentheses to left if it's a lower-precedence operator
            if self._needs_left_parens(ast.left, ast.operator):
                left_str = f"({left_str})"

            # Add parentheses to right if it's a lower-precedence operator
            if self._needs_right_parens(ast.right, ast.operator):
                right_str = f"({right_str})"

            return f"{left_str} {ast.operator} {right_str}"

        else:
            raise ValueError(f"Unknown AST node type: {type(ast)}")

    def _normalize_condition(self, condition: str) -> str:
        """
        Normalize atomic condition.

        Normalization rules:
            - Keywords to uppercase (IS, NULL, NOT, LIKE, IN, BETWEEN)
            - Function names to uppercase (LOWER, UPPER, LENGTH, TRIM, etc.)
            - Identifiers to lowercase (column_name)
            - Whitespace normalized
            - Function calls preserve their structure

        Args:
            condition: Condition string (may contain function calls)

        Returns:
            Normalized condition
        """
        # SQL keywords that should be uppercase
        KEYWORDS = {
            "IS",
            "NULL",
            "NOT",
            "AND",
            "OR",
            "LIKE",
            "IN",
            "BETWEEN",
            "TRUE",
            "FALSE",
        }

        # Common SQL functions (keep uppercase)
        FUNCTIONS = {
            "LOWER",
            "UPPER",
            "LENGTH",
            "TRIM",
            "SUBSTRING",
            "CONCAT",
            "COALESCE",
            "CURRENT_TIMESTAMP",
            "NOW",
            "CURRENT_DATE",
            "CURRENT_TIME",
            # User-defined functions should preserve case
            # For now, we'll normalize all functions to uppercase for consistency
        }

        # If this is a function call, preserve it as-is but normalize internal parts
        if "(" in condition and condition.strip().endswith(")"):
            # Check if it starts with a function name
            match = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", condition)
            if match:
                func_name = match.group(1).upper()
                # This is a function call - preserve structure, just normalize case
                return re.sub(
                    r"([a-zA-Z_][a-zA-Z0-9_]*)",
                    lambda m: m.group(1).upper()
                    if m.group(1).upper() in FUNCTIONS | KEYWORDS
                    else m.group(1).lower(),
                    condition,
                )

        # For non-function conditions, split and normalize tokens
        tokens = condition.split()

        normalized_tokens = []
        for token in tokens:
            token_upper = token.upper()

            # Check if token is a function call
            if "(" in token:
                # Function call - keep function name uppercase
                match = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", token)
                if match:
                    func_name = match.group(1).upper()
                    token = token.replace(match.group(1), func_name, 1)
                normalized_tokens.append(token)
            # Normalize SQL keywords to uppercase
            elif token_upper in KEYWORDS:
                normalized_tokens.append(token_upper)
            # Preserve string literals and numbers
            elif token.startswith("'") or token.startswith('"') or token.isdigit():
                normalized_tokens.append(token)
            # Preserve operators
            elif token in ("=", ">", "<", ">=", "<=", "<>", "!=", ",", "(", ")"):
                normalized_tokens.append(token)
            # Check if it's a known function name
            elif token_upper in FUNCTIONS:
                normalized_tokens.append(token_upper)
            # Normalize identifiers to lowercase
            else:
                normalized_tokens.append(token.lower())

        return " ".join(normalized_tokens)

    def _needs_left_parens(self, left: "WhereClauseAST", parent_op: str) -> bool:
        """
        Check if left operand needs parentheses.

        Args:
            left: Left AST node
            parent_op: Parent operator (AND/OR)

        Returns:
            True if left needs parentheses
        """
        # OR has lower precedence than AND
        if isinstance(left, BinaryOp) and left.operator == "OR" and parent_op == "AND":
            return True

        return False

    def _needs_right_parens(self, right: "WhereClauseAST", parent_op: str) -> bool:
        """
        Check if right operand needs parentheses.

        Args:
            right: Right AST node
            parent_op: Parent operator (AND/OR)

        Returns:
            True if right needs parentheses
        """
        # OR has lower precedence than AND
        if isinstance(right, BinaryOp) and right.operator == "OR" and parent_op == "AND":
            return True

        return False

    def _get_top_level_operator(self, ast: "WhereClauseAST") -> Optional[str]:
        """
        Get the top-level operator of an AST node.

        This is used to determine precedence for Parenthesized expressions.
        - For BinaryOp: returns the operator (AND/OR)
        - For Parenthesized: recursively gets inner operator
        - For Condition: returns None (atomic expression)

        Args:
            ast: AST node

        Returns:
            Operator string (AND/OR) or None
        """
        if isinstance(ast, BinaryOp):
            return ast.operator
        elif isinstance(ast, Parenthesized):
            return self._get_top_level_operator(ast.inner)
        else:
            return None

    def _has_lower_precedence(self, op1: str, op2: str) -> bool:
        """
        Check if op1 has lower precedence than op2.

        Precedence rules (lower number = lower precedence):
        1. OR
        2. AND

        Args:
            op1: First operator (AND/OR)
            op2: Second operator (AND/OR)

        Returns:
            True if op1 has lower precedence than op2
        """
        precedence = {"OR": 1, "AND": 2}

        prec1 = precedence.get(op1, 0)
        prec2 = precedence.get(op2, 0)

        return prec1 < prec2


# =============================================================================
# Provider-Specific Normalizers
# =============================================================================


class PostgresNormalizer(SchemaNormalizer):
    """
    PostgreSQL-specific schema normalization.

    Handles PostgreSQL-specific quirks:
        - Float type aliases: float8 → DOUBLE PRECISION, float4 → REAL
        - Integer aliases: int4 → INTEGER, int8 → BIGINT
        - Timestamp aliases: TIMESTAMPTZ → TIMESTAMP WITH TIME ZONE
        - Boolean defaults: 't' → TRUE, 'f' → FALSE
        - Type parameters: Strip VARCHAR(n), NUMERIC(p,s) parameters for comparison
        - Sequence defaults: nextval(...) handling
    """

    def normalize_native_type(self, native_type: Optional[str]) -> Optional[str]:
        """
        Normalize PostgreSQL native types with provider-specific aliases.

        PostgreSQL uses internal type names that differ from SQL standards:
            - float8 → DOUBLE PRECISION
            - float4 → REAL
            - int4 → INTEGER
            - int8 → BIGINT
            - bool → BOOLEAN
            - varchar → CHARACTER VARYING
            - timestamptz → TIMESTAMP WITH TIME ZONE

        Additionally, PostgreSQL's information_schema returns types WITHOUT
        parameters (e.g., VARCHAR not VARCHAR(255), NUMERIC not NUMERIC(15,2)),
        so we strip parameters for consistent comparison.

        Args:
            native_type: PostgreSQL native type (e.g., 'float8', 'VARCHAR(255)')

        Returns:
            Normalized type name (without parameters)
        """
        # First apply base normalization (case, whitespace)
        normalized = super().normalize_native_type(native_type)

        if normalized is None:
            return None

        # Step 1: Strip type parameters for comparison
        # PostgreSQL information_schema returns: VARCHAR (not VARCHAR(255))
        # Pydantic generates: VARCHAR(255)
        # We need to normalize both to: VARCHAR
        base_type = self._strip_type_parameters(normalized)

        # Step 2: Apply PostgreSQL-specific type aliases
        type_aliases = {
            "FLOAT8": "DOUBLE PRECISION",
            "DOUBLE": "DOUBLE PRECISION",
            "FLOAT4": "REAL",
            "INT4": "INTEGER",
            "INT8": "BIGINT",
            "BOOL": "BOOLEAN",
            # Timestamp aliases
            "TIMESTAMPTZ": "TIMESTAMP WITH TIME ZONE",
            "TIMESTAMP WITH TIME ZONE": "TIMESTAMP WITH TIME ZONE",
            # Array types (PostgreSQL uses _type internally, but displays as type[])
            "TEXT[]": "TEXT[]",
            "_TEXT": "TEXT[]",
        }

        return type_aliases.get(base_type, base_type)

    def _strip_type_parameters(self, type_str: str) -> str:
        """
        Strip type parameters from SQL type string.

        Examples:
            'VARCHAR(255)' → 'VARCHAR'
            'NUMERIC(15,2)' → 'NUMERIC'
            'TIMESTAMP WITH TIME ZONE' → 'TIMESTAMP WITH TIME ZONE' (no params)
            'TEXT[]' → 'TEXT[]' (array suffix preserved)

        Args:
            type_str: Type string with optional parameters

        Returns:
            Base type without parameters
        """
        # Find the first opening parenthesis
        paren_idx = type_str.find("(")

        if paren_idx == -1:
            # No parameters
            return type_str

        # Return everything before the opening parenthesis
        return type_str[:paren_idx]


class MySQLNormalizer(SchemaNormalizer):
    """
    MySQL-specific schema normalization.

    Currently inherits all normalization from SchemaNormalizer base class.

    **Status**: Basic stub implementation
    **Coverage**: WHERE clause normalization, column/index comparison work via base class

    **Future MySQL-Specific Normalization** (not yet implemented):
        - Type aliases: INT → INTEGER, TINYINT(1) → BOOLEAN
        - TIMESTAMP vs DATETIME normalization
        - VARCHAR collation normalization (utf8mb4_unicode_ci)
        - ENUM/SET type handling
        - AUTO_INCREMENT attribute normalization
        - Index type aliases: BTREE vs default

    **Current Behavior**:
        All schema comparison uses base SchemaNormalizer, which handles:
        ✅ WHERE clause precedence preservation
        ✅ SQL string escaping
        ✅ Case normalization (identifiers lowercase, keywords uppercase)
        ✅ Column type, nullable, default comparison
        ✅ Index columns, unique, type, where_clause comparison

    **Recommendation**: For production MySQL use, implement normalize_native_type()
    override with MySQL type alias mapping.
    """

    pass


class SQLServerNormalizer(SchemaNormalizer):
    """
    SQL Server-specific schema normalization.

    Currently inherits all normalization from SchemaNormalizer base class.

    **Status**: Basic stub implementation
    **Coverage**: WHERE clause normalization, column/index comparison work via base class

    **Future SQL Server-Specific Normalization** (not yet implemented):
        - Type aliases: INT → INTEGER, BIT → BOOLEAN
        - NVARCHAR vs VARCHAR normalization
        - DATETIME2 vs DATETIME normalization
        - IDENTITY attribute normalization
        - Collation normalization (SQL_Latin1_General_CP1_CI_AS)
        - Index type: CLUSTERED vs NONCLUSTERED normalization
        - Schema-qualified names: dbo.table normalization

    **Current Behavior**:
        All schema comparison uses base SchemaNormalizer, which handles:
        ✅ WHERE clause precedence preservation
        ✅ SQL string escaping
        ✅ Case normalization (identifiers lowercase, keywords uppercase)
        ✅ Column type, nullable, default comparison
        ✅ Index columns, unique, type, where_clause comparison

    **Recommendation**: For production SQL Server use, implement normalize_native_type()
    override with SQL Server type alias mapping.
    """

    pass


# =============================================================================
# WHERE Clause AST Nodes
# =============================================================================


class WhereClauseAST:
    """Base class for WHERE clause Abstract Syntax Tree nodes."""

    pass


class Condition(WhereClauseAST):
    """
    Atomic condition (leaf node).

    Examples:
        - 'deleted_at IS NULL'
        - 'status = \'active\''
        - 'age > 18'
    """

    def __init__(self, expression: str):
        self.expression = expression

    def __repr__(self):
        return f"Condition({self.expression!r})"


class Parenthesized(WhereClauseAST):
    """
    Parenthesized expression.

    Tracks whether parens are semantically necessary or just cosmetic.
    """

    def __init__(self, inner: WhereClauseAST):
        self.inner = inner

    def __repr__(self):
        return f"Parenthesized({self.inner!r})"


class BinaryOp(WhereClauseAST):
    """
    Binary operation (AND/OR).

    Preserves operator precedence:
        - AND has higher precedence than OR
        - Example: 'a OR b AND c' = 'a OR (b AND c)'
    """

    def __init__(self, left: WhereClauseAST, operator: str, right: WhereClauseAST):
        self.left = left
        self.operator = operator.upper()
        self.right = right

    def __repr__(self):
        return f"BinaryOp({self.left!r} {self.operator} {self.right!r})"
