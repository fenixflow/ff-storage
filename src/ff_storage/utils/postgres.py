"""
PostgreSQL-specific query building utilities.

This module provides centralized utilities for building safe PostgreSQL queries
with properly quoted identifiers to handle SQL reserved keywords.

All temporal strategies and schema sync operations should use these utilities
to ensure consistent, production-grade SQL generation.
"""

from typing import Any, Dict, List, Tuple


def quote_identifier(identifier: str) -> str:
    """
    Quote a SQL identifier (table, column, index name) for PostgreSQL.

    This ensures SQL reserved keywords and special characters work correctly
    by wrapping identifiers in double quotes.

    Args:
        identifier: SQL identifier (can be schema.table or simple name)

    Returns:
        Quoted identifier

    Examples:
        >>> quote_identifier("limit")
        '"limit"'

        >>> quote_identifier("order")
        '"order"'

        >>> quote_identifier("public.users")
        '"public"."users"'

        >>> quote_identifier("my_table")
        '"my_table"'

    Implementation Note:
        This is the single source of truth for identifier quoting in ff-storage.
        All SQL query building (DDL and DML) should use this function.
    """
    if "." in identifier:
        # Handle schema.table format
        parts = identifier.split(".")
        return ".".join(f'"{part}"' for part in parts)

    # Simple identifier
    return f'"{identifier}"'


def build_column_list(columns: List[str], quoted: bool = True) -> str:
    """
    Build comma-separated column list for SQL queries.

    Args:
        columns: List of column names
        quoted: If True, quote each column name (default: True)

    Returns:
        Comma-separated column list

    Examples:
        >>> build_column_list(["id", "limit", "order"])
        '"id", "limit", "order"'

        >>> build_column_list(["name", "price"], quoted=False)
        'name, price'
    """
    if quoted:
        return ", ".join(quote_identifier(col) for col in columns)
    return ", ".join(columns)


def build_insert_query(table_name: str, columns: List[str]) -> str:
    """
    Build INSERT query with properly quoted identifiers.

    Generates a PostgreSQL INSERT query with:
    - Quoted table name (handles schema.table)
    - Quoted column names (handles reserved keywords)
    - Parameterized placeholders ($1, $2, ...)
    - RETURNING * clause

    Args:
        table_name: Fully-qualified table name (e.g., "public.products")
        columns: List of column names

    Returns:
        Complete INSERT query string

    Example:
        >>> build_insert_query("public.products", ["id", "limit", "order", "price"])
        'INSERT INTO "public"."products" ("id", "limit", "order", "price") VALUES ($1, $2, $3, $4) RETURNING *'

    Note:
        This replaces the pattern:
            INSERT INTO {table_name} ({", ".join(columns)})
        Which fails for reserved keywords like 'limit', 'order', 'user', etc.
    """
    quoted_table = quote_identifier(table_name)
    quoted_columns = build_column_list(columns, quoted=True)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))

    return f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders}) RETURNING *"


def build_update_set_clause(data: Dict[str, Any], base_param_count: int) -> Tuple[str, List[Any]]:
    """
    Build UPDATE SET clause with quoted column names.

    Generates a SET clause for UPDATE queries with:
    - Quoted column names (handles reserved keywords)
    - Parameterized placeholders starting from base_param_count + 1

    Args:
        data: Dictionary of column_name -> value
        base_param_count: Number of parameters already in the query (for $N numbering)

    Returns:
        Tuple of (set_clause, values_list)

    Example:
        >>> build_update_set_clause({"limit": 100, "order": "A", "updated_at": "2025-01-01"}, 2)
        ('"limit" = $3, "order" = $4, "updated_at" = $5', [100, 'A', '2025-01-01'])

    Usage:
        set_clause, set_values = build_update_set_clause(data, len(where_values))
        query = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}"
        await conn.fetchrow(query, *where_values, *set_values)

    Note:
        This replaces the pattern:
            set_parts.append(f"{key} = ${param_num}")
        Which fails for reserved keywords like 'limit', 'order', 'user', etc.
    """
    set_parts = []
    set_values = []

    for key, value in data.items():
        set_values.append(value)
        quoted_key = quote_identifier(key)
        param_num = base_param_count + len(set_values)
        set_parts.append(f"{quoted_key} = ${param_num}")

    set_clause = ", ".join(set_parts)
    return set_clause, set_values


def build_where_clause(
    filters: Dict[str, Any], base_param_count: int = 0, operator: str = "AND"
) -> Tuple[str, List[Any]]:
    """
    Build WHERE clause with quoted column names.

    Generates a WHERE clause with:
    - Quoted column names (handles reserved keywords)
    - Proper NULL handling (IS NULL / IS NOT NULL)
    - IN clause support for list/tuple values
    - Parameterized placeholders

    Args:
        filters: Dictionary of column_name -> value
        base_param_count: Number of parameters already in the query (for $N numbering)
        operator: Logical operator between conditions ("AND" or "OR")

    Returns:
        Tuple of (where_clause, values_list)

    Example:
        >>> build_where_clause({"limit": 100, "select": True}, 0, "AND")
        ('"limit" = $1 AND "select" = $2', [100, True])

        >>> build_where_clause({"status": None}, 0)
        ('"status" IS NULL', [])

        >>> build_where_clause({"id": [1, 2, 3]}, 0)
        ('"id" IN ($1, $2, $3)', [1, 2, 3])

    Note:
        This replaces the pattern:
            where_clauses.append(f"{key} = ${param_num}")
        Which fails for reserved keywords like 'limit', 'order', 'user', etc.
    """
    where_clauses = []
    where_values = []

    for key, value in filters.items():
        quoted_key = quote_identifier(key)

        if value is None:
            # Handle NULL values
            where_clauses.append(f"{quoted_key} IS NULL")
        elif isinstance(value, (list, tuple)):
            # Handle IN clause
            placeholders = []
            for item in value:
                where_values.append(item)
                param_num = base_param_count + len(where_values)
                placeholders.append(f"${param_num}")
            where_clauses.append(f"{quoted_key} IN ({', '.join(placeholders)})")
        else:
            # Handle equality
            where_values.append(value)
            param_num = base_param_count + len(where_values)
            where_clauses.append(f"{quoted_key} = ${param_num}")

    where_clause = f" {operator} ".join(where_clauses)
    return where_clause, where_values
