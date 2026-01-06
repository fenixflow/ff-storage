"""SQL generation utilities.

This module provides utilities for generating SQL fragments with proper
quoting and parameter tracking, eliminating duplication across the query
builder components.
"""

from __future__ import annotations

from typing import List, Tuple


class ColumnRef:
    """
    Generates properly quoted column references.

    This utility ensures consistent column quoting across all SQL generation
    code, preventing SQL injection and handling reserved words.

    Examples:
        >>> ColumnRef.format("price")
        't0."price"'

        >>> ColumnRef.format("name", "t1")
        't1."name"'

        >>> ColumnRef.format_qualified("public", "users", "id")
        '"public"."users"."id"'
    """

    @staticmethod
    def _escape_identifier(name: str) -> str:
        """
        Escape double quotes in an identifier for SQL quoting.

        In SQL, a double quote within a quoted identifier must be escaped
        by doubling it (e.g., 'foo"bar' becomes '"foo""bar"').

        Args:
            name: Raw identifier name

        Returns:
            Escaped identifier safe for quoting
        """
        return name.replace('"', '""')

    @staticmethod
    def format(field: str, table_alias: str = "t0") -> str:
        """
        Format a column reference with proper quoting.

        Args:
            field: The column/field name
            table_alias: Table alias prefix (default: "t0")

        Returns:
            Quoted column reference like 't0."field"'
        """
        escaped = ColumnRef._escape_identifier(field)
        return f'{table_alias}."{escaped}"'

    @staticmethod
    def format_qualified(schema: str, table: str, column: str) -> str:
        """
        Format a fully qualified column reference.

        Args:
            schema: Database schema name
            table: Table name
            column: Column name

        Returns:
            Fully qualified reference like '"schema"."table"."column"'
        """
        s = ColumnRef._escape_identifier(schema)
        t = ColumnRef._escape_identifier(table)
        c = ColumnRef._escape_identifier(column)
        return f'"{s}"."{t}"."{c}"'

    @staticmethod
    def format_table(schema: str, table: str) -> str:
        """
        Format a schema-qualified table reference.

        Args:
            schema: Database schema name
            table: Table name

        Returns:
            Qualified table reference like '"schema"."table"'
        """
        s = ColumnRef._escape_identifier(schema)
        t = ColumnRef._escape_identifier(table)
        return f'"{s}"."{t}"'

    @staticmethod
    def quote_identifier(name: str) -> str:
        """
        Quote a SQL identifier.

        Handles dotted identifiers (schema.table) by quoting each part.
        Escapes embedded double quotes by doubling them.

        Args:
            name: Identifier to quote

        Returns:
            Quoted identifier like '"name"' or '"schema"."table"'
        """
        if "." in name:
            parts = name.split(".")
            return ".".join(f'"{ColumnRef._escape_identifier(p)}"' for p in parts)
        return f'"{ColumnRef._escape_identifier(name)}"'


class ParameterTracker:
    """
    Tracks parameter indices for PostgreSQL parameterized queries.

    PostgreSQL uses $1, $2, ... style placeholders. This class helps
    track the current index and generate placeholders consistently.

    Examples:
        >>> tracker = ParameterTracker()
        >>> tracker.next()
        '$1'
        >>> tracker.next()
        '$2'
        >>> tracker.next_n(3)
        '$3, $4, $5'
        >>> tracker.current
        6
    """

    def __init__(self, start: int = 1):
        """
        Initialize the parameter tracker.

        Args:
            start: Starting parameter index (default: 1)
        """
        self._index = start
        self._params: List = []

    def next(self) -> str:
        """
        Get the next parameter placeholder.

        Returns:
            Placeholder string like '$N'
        """
        placeholder = f"${self._index}"
        self._index += 1
        return placeholder

    def next_n(self, count: int) -> str:
        """
        Get N consecutive placeholders as a comma-separated string.

        Args:
            count: Number of placeholders to generate

        Returns:
            Comma-separated placeholders like '$1, $2, $3'
        """
        if count <= 0:
            return ""
        placeholders = ", ".join(f"${self._index + i}" for i in range(count))
        self._index += count
        return placeholders

    def next_list(self, count: int) -> List[str]:
        """
        Get N consecutive placeholders as a list.

        Args:
            count: Number of placeholders to generate

        Returns:
            List of placeholder strings ['$1', '$2', '$3']
        """
        if count <= 0:
            return []
        placeholders = [f"${self._index + i}" for i in range(count)]
        self._index += count
        return placeholders

    @property
    def current(self) -> int:
        """
        Get the current (next available) parameter index.

        Returns:
            Current parameter index
        """
        return self._index

    def add_param(self, value) -> str:
        """
        Add a parameter value and return its placeholder.

        This is a convenience method that tracks both the placeholder
        and the parameter value.

        Args:
            value: Parameter value to add

        Returns:
            Placeholder string like '$N'
        """
        placeholder = self.next()
        self._params.append(value)
        return placeholder

    def add_params(self, values: List) -> str:
        """
        Add multiple parameter values and return placeholders.

        Args:
            values: List of parameter values

        Returns:
            Comma-separated placeholders
        """
        self._params.extend(values)
        return self.next_n(len(values))

    @property
    def params(self) -> List:
        """
        Get the accumulated parameter values.

        Returns:
            List of parameter values in order
        """
        return self._params

    def reset(self, start: int = 1) -> None:
        """
        Reset the tracker to a new starting index.

        Args:
            start: New starting index (default: 1)
        """
        self._index = start
        self._params = []


def build_in_clause(
    column: str,
    values: List,
    tracker: ParameterTracker,
    table_alias: str = "t0",
) -> Tuple[str, List]:
    """
    Build an IN clause with proper parameterization.

    Args:
        column: Column name
        values: List of values for IN clause
        tracker: Parameter tracker for placeholder indices
        table_alias: Table alias (default: "t0")

    Returns:
        Tuple of (sql_clause, param_values)

    Examples:
        >>> tracker = ParameterTracker()
        >>> sql, params = build_in_clause("status", ["a", "b"], tracker)
        >>> sql
        't0."status" IN ($1, $2)'
        >>> params
        ['a', 'b']
    """
    if not values:
        return "FALSE", []

    col_ref = ColumnRef.format(column, table_alias)
    placeholders = tracker.next_n(len(values))
    return f"{col_ref} IN ({placeholders})", list(values)


def build_not_in_clause(
    column: str,
    values: List,
    tracker: ParameterTracker,
    table_alias: str = "t0",
) -> Tuple[str, List]:
    """
    Build a NOT IN clause with proper parameterization.

    Args:
        column: Column name
        values: List of values for NOT IN clause
        tracker: Parameter tracker for placeholder indices
        table_alias: Table alias (default: "t0")

    Returns:
        Tuple of (sql_clause, param_values)
    """
    if not values:
        return "TRUE", []

    col_ref = ColumnRef.format(column, table_alias)
    placeholders = tracker.next_n(len(values))
    return f"{col_ref} NOT IN ({placeholders})", list(values)


def build_between_clause(
    column: str,
    low,
    high,
    tracker: ParameterTracker,
    table_alias: str = "t0",
) -> Tuple[str, List]:
    """
    Build a BETWEEN clause with proper parameterization.

    Args:
        column: Column name
        low: Lower bound value
        high: Upper bound value
        tracker: Parameter tracker for placeholder indices
        table_alias: Table alias (default: "t0")

    Returns:
        Tuple of (sql_clause, param_values)
    """
    col_ref = ColumnRef.format(column, table_alias)
    p1 = tracker.next()
    p2 = tracker.next()
    return f"{col_ref} BETWEEN {p1} AND {p2}", [low, high]
