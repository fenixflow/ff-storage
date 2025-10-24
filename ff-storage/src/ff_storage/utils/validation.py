"""
SQL query validation and security utilities.

This module provides validation functions to prevent SQL injection
and ensure query safety.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ..exceptions import SQLInjectionAttempt, ValidationError


class SQLValidator:
    """
    SQL query validator to prevent injection attacks and dangerous operations.

    This validator uses multiple strategies:
    1. Pattern matching for dangerous SQL patterns
    2. Parameter validation to ensure proper escaping
    3. Query structure analysis
    """

    # Dangerous SQL patterns that might indicate injection attempts
    DANGEROUS_PATTERNS = [
        # Multiple statements
        (
            r";\s*(DROP|DELETE|INSERT|UPDATE|CREATE|ALTER|TRUNCATE)",
            "Multiple statements with DDL/DML",
        ),
        # Comments that might hide malicious code
        (r"--[^\n]*$", "SQL line comment"),
        (r"/\*.*?\*/", "SQL block comment"),
        # Common injection patterns
        (r"'\s*OR\s+'?[0-9]+'?\s*=\s*'?[0-9]+'?", "OR 1=1 pattern"),
        (r"'\s*OR\s+''='", "OR ''='' pattern"),
        (r'"\s*OR\s+"?[0-9]+"?\s*=\s*"?[0-9]+"?', "OR with double quotes"),
        # Dangerous functions
        (r"\b(EXEC|EXECUTE|xp_cmdshell|sp_executesql)\b", "Dangerous execute functions"),
        # Time-based blind SQL injection
        (r"\b(SLEEP|WAITFOR|BENCHMARK|pg_sleep)\b", "Time delay functions"),
        # Union-based injection
        (r"\bUNION\s+(ALL\s+)?SELECT\b", "UNION SELECT pattern"),
        # Stacked queries
        (r";\s*SELECT", "Stacked SELECT query"),
        # File operations
        (r"\b(LOAD_FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE)\b", "File operations"),
    ]

    # Allowed safe patterns (whitelist)
    SAFE_PATTERNS = [
        r"^SELECT\s+",
        r"^INSERT\s+INTO\s+",
        r"^UPDATE\s+",
        r"^DELETE\s+FROM\s+",
        r"^WITH\s+",  # CTE
        r"^MERGE\s+",
    ]

    # Reserved keywords that shouldn't appear in user input
    RESERVED_KEYWORDS = {
        "DROP",
        "CREATE",
        "ALTER",
        "TRUNCATE",
        "EXEC",
        "EXECUTE",
        "GRANT",
        "REVOKE",
        "SHUTDOWN",
        "KILL",
    }

    def __init__(
        self,
        strict_mode: bool = True,
        allow_comments: bool = False,
        custom_dangerous_patterns: Optional[List[Tuple[str, str]]] = None,
        custom_safe_patterns: Optional[List[str]] = None,
    ):
        """
        Initialize SQL validator.

        Args:
            strict_mode: If True, reject queries with any suspicious patterns
            allow_comments: If True, allow SQL comments (risky)
            custom_dangerous_patterns: Additional patterns to check
            custom_safe_patterns: Additional safe patterns to allow
        """
        self.strict_mode = strict_mode
        self.allow_comments = allow_comments
        self.logger = logging.getLogger(__name__)

        # Build pattern lists
        self.dangerous_patterns = list(self.DANGEROUS_PATTERNS)
        if custom_dangerous_patterns:
            self.dangerous_patterns.extend(custom_dangerous_patterns)

        self.safe_patterns = list(self.SAFE_PATTERNS)
        if custom_safe_patterns:
            self.safe_patterns.extend(custom_safe_patterns)

        # Compile patterns for efficiency
        self._compiled_dangerous = [
            (re.compile(pattern, re.IGNORECASE | re.MULTILINE | re.DOTALL), desc)
            for pattern, desc in self.dangerous_patterns
        ]
        self._compiled_safe = [re.compile(pattern, re.IGNORECASE) for pattern in self.safe_patterns]

    def validate_query(
        self, query: str, params: Optional[Any] = None, context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Validate SQL query for potential injection attempts.

        Args:
            query: SQL query string
            params: Query parameters (if using parameterized queries)
            context: Additional context for validation
                - trusted_source (bool): If True, skip pattern matching (for internally-generated SQL)
                - source (str): Description of where the query comes from (for logging)

        Returns:
            True if query is safe

        Raises:
            SQLInjectionAttempt: If dangerous pattern detected
            ValidationError: If query structure is invalid
        """
        if not query or not query.strip():
            raise ValidationError("Empty query", "Query cannot be empty")

        query = query.strip()
        context = context or {}

        # Skip validation for trusted sources (internally-generated SQL)
        if context.get("trusted_source", False):
            self.logger.debug(
                f"Skipping validation for trusted source: {context.get('source', 'unknown')}",
                extra={"query_preview": query[:100]},
            )
            return True

        # Check for dangerous patterns
        if not self.allow_comments:
            # Remove comment patterns from dangerous list if comments allowed
            for pattern, description in self._compiled_dangerous:
                if pattern.search(query):
                    self.logger.warning(
                        f"Dangerous SQL pattern detected: {description}",
                        extra={"query": query[:200]},
                    )
                    raise SQLInjectionAttempt(query, description)

        # In strict mode, ensure query matches safe patterns
        if self.strict_mode:
            if not any(pattern.match(query) for pattern in self._compiled_safe):
                raise ValidationError(
                    "Query doesn't match safe patterns", "Query must start with allowed keywords"
                )

        # NOTE: Parameter validation removed - parameterized queries are already safe by design.
        # Parameters are passed separately from SQL and never interpreted as code.
        # Checking for keywords in parameter values (filenames, content, etc.) creates
        # false positives without adding security value.

        # Additional structure validation
        self._validate_query_structure(query)

        return True

    def validate_identifier(self, identifier: str) -> bool:
        """
        Validate database identifier (table name, column name, etc.).

        Args:
            identifier: The identifier to validate

        Returns:
            True if identifier is safe

        Raises:
            ValidationError: If identifier is invalid
        """
        # Check for empty identifier
        if not identifier:
            raise ValidationError("Empty identifier", "Identifier cannot be empty")

        # Only allow alphanumeric, underscore, and dot (for schema.table)
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$", identifier):
            raise ValidationError(
                "Invalid identifier", f"Identifier '{identifier}' contains invalid characters"
            )

        # Check length (prevent buffer overflow attacks)
        if len(identifier) > 128:
            raise ValidationError(
                "Identifier too long", f"Identifier length {len(identifier)} exceeds maximum 128"
            )

        # Check for reserved keywords
        identifier_upper = identifier.upper()
        if identifier_upper in self.RESERVED_KEYWORDS:
            raise ValidationError("Reserved keyword", f"'{identifier}' is a reserved keyword")

        return True

    def sanitize_like_pattern(self, pattern: str) -> str:
        """
        Sanitize a LIKE pattern to prevent wildcard injection.

        Args:
            pattern: The LIKE pattern to sanitize

        Returns:
            Sanitized pattern with escaped wildcards
        """
        # Escape special LIKE characters
        pattern = pattern.replace("\\", "\\\\")  # Escape backslash first
        pattern = pattern.replace("%", "\\%")  # Escape percent
        pattern = pattern.replace("_", "\\_")  # Escape underscore
        pattern = pattern.replace("[", "\\[")  # Escape bracket (SQL Server)

        return pattern

    def validate_order_by(
        self, column: str, allowed_columns: Set[str], direction: str = "ASC"
    ) -> Tuple[str, str]:
        """
        Validate ORDER BY clause components.

        Args:
            column: Column name to order by
            allowed_columns: Set of allowed column names
            direction: Sort direction (ASC/DESC)

        Returns:
            Tuple of (validated_column, validated_direction)

        Raises:
            ValidationError: If column or direction is invalid
        """
        # Validate column name
        if column not in allowed_columns:
            raise ValidationError(
                "Invalid ORDER BY column", f"Column '{column}' not in allowed columns"
            )

        # Validate direction
        direction = direction.upper()
        if direction not in ("ASC", "DESC"):
            raise ValidationError(
                "Invalid sort direction", f"Direction must be ASC or DESC, got '{direction}'"
            )

        return column, direction

    def build_safe_where_clause(
        self, conditions: Dict[str, Any], allowed_columns: Set[str], operator: str = "AND"
    ) -> Tuple[str, List[Any]]:
        """
        Build a safe WHERE clause from conditions.

        Args:
            conditions: Dictionary of column:value conditions
            allowed_columns: Set of allowed column names
            operator: Logical operator (AND/OR)

        Returns:
            Tuple of (where_clause, parameters)

        Raises:
            ValidationError: If any column is not allowed
        """
        if not conditions:
            return "", []

        # Validate operator
        operator = operator.upper()
        if operator not in ("AND", "OR"):
            raise ValidationError(
                "Invalid logical operator", f"Operator must be AND or OR, got '{operator}'"
            )

        clauses = []
        params = []

        for column, value in conditions.items():
            # Validate column name
            if column not in allowed_columns:
                raise ValidationError(
                    "Invalid WHERE column", f"Column '{column}' not in allowed columns"
                )

            if value is None:
                clauses.append(f"{column} IS NULL")
            elif isinstance(value, (list, tuple)):
                # Handle IN clause
                placeholders = ", ".join(["%s"] * len(value))
                clauses.append(f"{column} IN ({placeholders})")
                params.extend(value)
            else:
                clauses.append(f"{column} = %s")
                params.append(value)

        where_clause = f" {operator} ".join(clauses)
        return where_clause, params

    def _validate_parameters(self, params: Any):
        """Validate query parameters for dangerous content."""
        if params is None:
            return

        # Convert to list for uniform handling
        param_list = params if isinstance(params, (list, tuple)) else [params]

        for param in param_list:
            if isinstance(param, str):
                # Check for SQL keywords in string parameters
                param_upper = param.upper()
                for keyword in self.RESERVED_KEYWORDS:
                    if keyword in param_upper:
                        self.logger.warning(
                            f"Reserved keyword '{keyword}' found in parameter",
                            extra={"parameter": param[:100]},
                        )
                        if self.strict_mode:
                            raise ValidationError(
                                "Reserved keyword in parameter",
                                f"Parameter contains reserved keyword '{keyword}'",
                            )

    def _validate_query_structure(self, query: str):
        """Perform structural validation of the query."""
        # Check for balanced parentheses
        open_parens = query.count("(")
        close_parens = query.count(")")
        if open_parens != close_parens:
            raise ValidationError(
                "Unbalanced parentheses", f"Query has {open_parens} '(' and {close_parens} ')'"
            )

        # Check for balanced quotes
        single_quotes = query.count("'")
        if single_quotes % 2 != 0:
            raise ValidationError("Unbalanced quotes", "Query has odd number of single quotes")

        double_quotes = query.count('"')
        if double_quotes % 2 != 0:
            raise ValidationError("Unbalanced quotes", "Query has odd number of double quotes")


# Global validator instance
_global_validator = SQLValidator()


def get_validator() -> SQLValidator:
    """Get the global SQL validator instance."""
    return _global_validator


def set_validator(validator: SQLValidator):
    """Set the global SQL validator instance."""
    global _global_validator
    _global_validator = validator


def validate_query(
    query: str, params: Optional[Any] = None, context: Optional[Dict[str, Any]] = None
) -> bool:
    """Validate SQL query using global validator."""
    return get_validator().validate_query(query, params, context)


def validate_identifier(identifier: str) -> bool:
    """Validate database identifier using global validator."""
    return get_validator().validate_identifier(identifier)


def sanitize_like_pattern(pattern: str) -> str:
    """Sanitize LIKE pattern using global validator."""
    return get_validator().sanitize_like_pattern(pattern)
