"""
PostgreSQL-specific query builder implementation.

Handles PostgreSQL syntax including:
- Double-quote identifier quoting
- $1, $2, $3 parameter placeholders
- RETURNING clauses
- Reserved keywords
"""

from typing import Any, Dict, List, Tuple

from ...utils.validation import validate_identifier
from .base import QueryBuilder


class PostgresQueryBuilder(QueryBuilder):
    """
    PostgreSQL query builder with automatic identifier quoting.

    Features:
    - Always quotes identifiers (safe against reserved keywords)
    - Handles schema-qualified names (e.g., "schema"."table")
    - PostgreSQL $N parameter placeholders
    - RETURNING * for INSERT/UPDATE
    - NULL and IN clause support
    """

    # PostgreSQL reserved keywords that MUST be quoted
    # Full list: https://www.postgresql.org/docs/current/sql-keywords-appendix.html
    # We quote ALL identifiers for simplicity and safety
    RESERVED_KEYWORDS = {
        "all",
        "analyse",
        "analyze",
        "and",
        "any",
        "array",
        "as",
        "asc",
        "asymmetric",
        "authorization",
        "between",
        "binary",
        "both",
        "case",
        "cast",
        "check",
        "collate",
        "column",
        "constraint",
        "create",
        "cross",
        "current_date",
        "current_role",
        "current_time",
        "current_timestamp",
        "current_user",
        "default",
        "deferrable",
        "desc",
        "distinct",
        "do",
        "else",
        "end",
        "except",
        "false",
        "for",
        "foreign",
        "freeze",
        "from",
        "full",
        "grant",
        "group",
        "having",
        "ilike",
        "in",
        "initially",
        "inner",
        "intersect",
        "into",
        "is",
        "isnull",
        "join",
        "lateral",
        "leading",
        "left",
        "like",
        "limit",
        "localtime",
        "localtimestamp",
        "natural",
        "not",
        "notnull",
        "null",
        "offset",
        "on",
        "only",
        "or",
        "order",
        "outer",
        "overlaps",
        "placing",
        "primary",
        "references",
        "right",
        "select",
        "session_user",
        "similar",
        "some",
        "symmetric",
        "table",
        "tablesample",
        "then",
        "to",
        "trailing",
        "true",
        "union",
        "unique",
        "user",
        "using",
        "variadic",
        "verbose",
        "when",
        "where",
        "window",
        "with",
    }

    def quote_identifier(self, identifier: str) -> str:
        """
        Quote SQL identifier using PostgreSQL double-quote syntax.

        Always quotes identifiers for safety against reserved keywords.

        Args:
            identifier: Column/table/schema name (may be schema.table)

        Returns:
            Quoted identifier (e.g., '"limit"' or '"schema"."table"')

        Examples:
            >>> qb = PostgresQueryBuilder()
            >>> qb.quote_identifier("user")
            '"user"'
            >>> qb.quote_identifier("public.users")
            '"public"."users"'
        """
        if "." in identifier:
            # Schema-qualified name: quote each part separately
            parts = identifier.split(".")
            return ".".join(f'"{part}"' for part in parts)
        return f'"{identifier}"'

    def build_insert(self, table: str, data: Dict[str, Any]) -> Tuple[str, List[Any]]:
        """
        Build PostgreSQL INSERT query with RETURNING *.

        Args:
            table: Table name (may be schema-qualified)
            data: Column → value dictionary

        Returns:
            (query, values) tuple

        Examples:
            >>> qb = PostgresQueryBuilder()
            >>> query, values = qb.build_insert("users", {"name": "John", "age": 30})
            >>> query
            'INSERT INTO "users" ("name", "age") VALUES ($1, $2) RETURNING *'
            >>> values
            ['John', 30]
        """
        if not data:
            raise ValueError("Cannot build INSERT with empty data")

        quoted_table = self.quote_identifier(table)
        columns = list(data.keys())
        values = list(data.values())

        # Quote all column names
        quoted_columns = ", ".join(self.quote_identifier(col) for col in columns)

        # Build PostgreSQL parameter placeholders: $1, $2, $3, ...
        placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))

        query = f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders}) RETURNING *"

        return query, values

    def build_update(
        self, table: str, data: Dict[str, Any], where: Dict[str, Any]
    ) -> Tuple[str, List[Any]]:
        """
        Build PostgreSQL UPDATE query with WHERE clause and RETURNING *.

        Parameter order: WHERE values first, then SET values.
        This matches the common pattern in temporal strategies.

        Args:
            table: Table name (may be schema-qualified)
            data: Column → value dictionary for SET clause
            where: Column → value dictionary for WHERE clause

        Returns:
            (query, values) tuple

        Examples:
            >>> qb = PostgresQueryBuilder()
            >>> query, values = qb.build_update("users", {"age": 31}, {"id": 123})
            >>> query
            'UPDATE "users" SET "age" = $2 WHERE "id" = $1 RETURNING *'
            >>> values
            [123, 31]
        """
        if not data:
            raise ValueError("Cannot build UPDATE with empty data")
        if not where:
            raise ValueError("Cannot build UPDATE without WHERE clause (unsafe)")

        quoted_table = self.quote_identifier(table)

        # Build WHERE clause (parameters start at $1)
        where_clause, where_values = self.build_where_clause(where, base_param_count=0)

        # Build SET clause (parameters continue after WHERE)
        set_parts = []
        set_values = []
        base_param = len(where_values)

        for key, value in data.items():
            set_values.append(value)
            quoted_key = self.quote_identifier(key)
            param_num = base_param + len(set_values)
            set_parts.append(f"{quoted_key} = ${param_num}")

        set_clause = ", ".join(set_parts)

        query = f"UPDATE {quoted_table} SET {set_clause} WHERE {where_clause} RETURNING *"

        # Combine parameter values: WHERE first, then SET
        all_values = where_values + set_values

        return query, all_values

    def build_where_clause(
        self, filters: Dict[str, Any], base_param_count: int = 0, operator: str = "AND"
    ) -> Tuple[str, List[Any]]:
        """
        Build WHERE clause with NULL and IN support.

        Validates all identifiers to prevent SQL injection.

        Args:
            filters: Column → value dictionary
            base_param_count: Starting parameter number (for $N)
            operator: "AND" or "OR"

        Returns:
            (where_clause, values) tuple

        Examples:
            >>> qb = PostgresQueryBuilder()
            >>> clause, values = qb.build_where_clause({"name": "John", "age": None})
            >>> clause
            '"name" = $1 AND "age" IS NULL'
            >>> values
            ['John']

            >>> clause, values = qb.build_where_clause({"id": [1, 2, 3]})
            >>> clause
            '"id" IN ($1, $2, $3)'
            >>> values
            [1, 2, 3]
        """
        if not filters:
            raise ValueError("Cannot build WHERE clause with empty filters")

        clauses = []
        values = []

        for key, value in filters.items():
            # SECURITY: Validate identifier to prevent SQL injection
            validate_identifier(key)

            # Quote identifier to handle reserved keywords
            quoted_key = self.quote_identifier(key)

            if value is None:
                # Handle NULL: column IS NULL
                clauses.append(f"{quoted_key} IS NULL")

            elif isinstance(value, (list, tuple)):
                # Handle IN clause: column IN ($1, $2, $3)
                if not value:
                    raise ValueError(f"Cannot build IN clause with empty list for {key}")

                placeholders = ", ".join(
                    f"${base_param_count + len(values) + i + 1}" for i in range(len(value))
                )
                clauses.append(f"{quoted_key} IN ({placeholders})")
                values.extend(value)

            else:
                # Handle equality: column = $N
                param_num = base_param_count + len(values) + 1
                clauses.append(f"{quoted_key} = ${param_num}")
                values.append(value)

        where_clause = f" {operator} ".join(clauses)

        return where_clause, values

    def build_column_list(self, columns: List[str], quoted: bool = True) -> str:
        """
        Build comma-separated column list.

        Args:
            columns: List of column names
            quoted: Whether to quote identifiers (default True)

        Returns:
            Comma-separated column list

        Examples:
            >>> qb = PostgresQueryBuilder()
            >>> qb.build_column_list(["id", "name", "limit"])
            '"id", "name", "limit"'
        """
        if not columns:
            raise ValueError("Cannot build column list with empty columns")

        if quoted:
            return ", ".join(self.quote_identifier(col) for col in columns)
        else:
            return ", ".join(columns)
