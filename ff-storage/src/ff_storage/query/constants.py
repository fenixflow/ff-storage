"""Centralized constants for query building.

This module provides a single source of truth for SQL-related constants
used across the query builder. Centralizing these prevents duplication
and ensures consistent validation across all modules.

Security Notes:
    - All constants use frozenset for immutability
    - Validation against these constants prevents SQL injection via invalid values
    - These are the ONLY acceptable values for their respective SQL clauses
"""

# SQL JOIN types - validated in builder.py and executor.py
JOIN_TYPES = frozenset({"INNER", "LEFT", "RIGHT", "FULL", "CROSS"})

# ORDER BY directions - validated in ordering.py and base query builder
ORDER_DIRECTIONS = frozenset({"ASC", "DESC"})

# NULLS positioning for ORDER BY - validated in ordering.py
NULLS_POSITIONS = frozenset({"FIRST", "LAST"})

# Valid filter operators - validated in expressions.py
# These are the ONLY operators that can be used in FilterExpression.to_sql()
VALID_OPERATORS = frozenset(
    {
        # Comparison operators
        "=",
        "!=",
        "<>",  # Alternative to !=
        "<",
        ">",
        "<=",
        ">=",
        # Pattern matching
        "LIKE",
        "ILIKE",
        "NOT LIKE",
        "NOT ILIKE",
        # Set membership
        "IN",
        "NOT IN",
        # Subquery membership
        "IN_SUBQUERY",
        "NOT IN_SUBQUERY",
        # NULL checks
        "IS NULL",
        "IS NOT NULL",
        # Range
        "BETWEEN",
    }
)

# Characters that need escaping in LIKE patterns
# These have special meaning in SQL LIKE clauses
LIKE_ESCAPE_CHARS = {
    "%": r"\%",  # Matches any sequence of characters
    "_": r"\_",  # Matches any single character
    "\\": r"\\",  # Escape character itself
}
