"""
MySQL query builder implementation.

Handles MySQL-specific SQL generation:
- Backtick quoting for identifiers
- Named parameters (%(name)s format)
- LAST_INSERT_ID() instead of RETURNING
- MySQL-specific data types
"""

from typing import Any, Dict, List, Optional, Tuple

from .base import QueryBuilder


class MySQLQueryBuilder(QueryBuilder):
    """MySQL-specific query builder."""

    def quote_identifier(self, identifier: str) -> str:
        """
        Quote identifier using MySQL backticks.

        Args:
            identifier: Column or table name

        Returns:
            Quoted identifier using backticks
        """
        # Handle schema.table format
        if "." in identifier:
            parts = identifier.split(".", 1)
            return f"`{parts[0]}`.`{parts[1]}`"
        return f"`{identifier}`"

    def build_insert(
        self, table: str, data: Dict[str, Any], returning_fields: Optional[List[str]] = None
    ) -> Tuple[str, List[Any]]:
        """
        Build INSERT query for MySQL.

        MySQL doesn't support RETURNING clause, so we ignore returning_fields.
        Use LAST_INSERT_ID() after insert to get the ID.

        Args:
            table: Table name (can be schema.table)
            data: Dict of column -> value
            returning_fields: Ignored for MySQL

        Returns:
            Tuple of (query with $1 placeholders, list of values)
        """
        quoted_table = self.quote_identifier(table)
        columns = list(data.keys())
        quoted_columns = [self.quote_identifier(col) for col in columns]
        values = [data[col] for col in columns]

        # Use $1, $2, $3 placeholders (adapter will convert to %(p1)s format)
        params = [f"${i + 1}" for i in range(len(columns))]

        query = f"""
            INSERT INTO {quoted_table}
            ({", ".join(quoted_columns)})
            VALUES ({", ".join(params)})
        """.strip()

        return query, values

    def build_update(
        self,
        table: str,
        data: Dict[str, Any],
        where: Dict[str, Any],
        returning_fields: Optional[List[str]] = None,
    ) -> Tuple[str, List[Any]]:
        """
        Build UPDATE query for MySQL.

        Args:
            table: Table name
            data: Dict of columns to update
            where: Dict of WHERE conditions
            returning_fields: Ignored for MySQL

        Returns:
            Tuple of (query with $1 placeholders, list of values)
        """
        quoted_table = self.quote_identifier(table)
        values = []
        param_counter = 1

        # Build SET clause
        set_parts = []
        for col, value in data.items():
            quoted_col = self.quote_identifier(col)
            set_parts.append(f"{quoted_col} = ${param_counter}")
            values.append(value)
            param_counter += 1

        # Build WHERE clause
        where_parts = []
        for col, value in where.items():
            quoted_col = self.quote_identifier(col)
            if value is None:
                where_parts.append(f"{quoted_col} IS NULL")
            else:
                where_parts.append(f"{quoted_col} = ${param_counter}")
                values.append(value)
                param_counter += 1

        query = f"""
            UPDATE {quoted_table}
            SET {", ".join(set_parts)}
            WHERE {" AND ".join(where_parts)}
        """.strip()

        return query, values

    def build_delete(
        self, table: str, where: Dict[str, Any], returning_fields: Optional[List[str]] = None
    ) -> Tuple[str, List[Any]]:
        """
        Build DELETE query for MySQL.

        Args:
            table: Table name
            where: Dict of WHERE conditions
            returning_fields: Ignored for MySQL

        Returns:
            Tuple of (query with $1 placeholders, list of values)
        """
        quoted_table = self.quote_identifier(table)
        values = []
        param_counter = 1

        # Build WHERE clause
        where_parts = []
        for col, value in where.items():
            quoted_col = self.quote_identifier(col)
            if value is None:
                where_parts.append(f"{quoted_col} IS NULL")
            else:
                where_parts.append(f"{quoted_col} = ${param_counter}")
                values.append(value)
                param_counter += 1

        query = f"""
            DELETE FROM {quoted_table}
            WHERE {" AND ".join(where_parts)}
        """.strip()

        return query, values

    def build_select(
        self,
        table: str,
        columns: List[str] = None,
        where: Optional[Dict[str, Any]] = None,
        order_by: Optional[List[Tuple[str, str]]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Tuple[str, List[Any]]:
        """
        Build SELECT query for MySQL.

        Args:
            table: Table name
            columns: List of columns to select (None = *)
            where: Dict of WHERE conditions
            order_by: List of (column, direction) tuples
            limit: LIMIT value
            offset: OFFSET value

        Returns:
            Tuple of (query with $1 placeholders, list of values)
        """
        quoted_table = self.quote_identifier(table)

        # SELECT clause
        if columns:
            quoted_columns = [self.quote_identifier(col) for col in columns]
            select_clause = ", ".join(quoted_columns)
        else:
            select_clause = "*"

        query_parts = [f"SELECT {select_clause}", f"FROM {quoted_table}"]
        values = []
        param_counter = 1

        # WHERE clause
        if where:
            where_parts = []
            for col, value in where.items():
                quoted_col = self.quote_identifier(col)
                if value is None:
                    where_parts.append(f"{quoted_col} IS NULL")
                elif isinstance(value, list):
                    # IN clause
                    placeholders = []
                    for v in value:
                        placeholders.append(f"${param_counter}")
                        values.append(v)
                        param_counter += 1
                    where_parts.append(f"{quoted_col} IN ({', '.join(placeholders)})")
                else:
                    where_parts.append(f"{quoted_col} = ${param_counter}")
                    values.append(value)
                    param_counter += 1

            if where_parts:
                query_parts.append(f"WHERE {' AND '.join(where_parts)}")

        # ORDER BY clause
        if order_by:
            order_parts = []
            for col, direction in order_by:
                quoted_col = self.quote_identifier(col)
                order_parts.append(f"{quoted_col} {direction.upper()}")
            query_parts.append(f"ORDER BY {', '.join(order_parts)}")

        # LIMIT/OFFSET
        if limit is not None:
            query_parts.append(f"LIMIT {limit}")
        if offset is not None:
            query_parts.append(f"OFFSET {offset}")

        query = " ".join(query_parts)
        return query, values

    def get_param_style(self) -> str:
        """MySQL uses named parameters."""
        return "named"

    def build_where_clause(
        self, filters: Dict[str, Any], base_param_count: int = 0, operator: str = "AND"
    ) -> Tuple[str, List[Any]]:
        """
        Build WHERE clause from filters.

        Args:
            filters: Dict of column -> value filters
            base_param_count: Starting parameter count (1-indexed for $1, $2, etc.)
            operator: AND or OR

        Returns:
            Tuple of (where_clause with $N placeholders, list of values)
        """
        if not filters:
            return "", []

        where_parts = []
        values = []
        param_counter = base_param_count + 1

        for col, value in filters.items():
            quoted_col = self.quote_identifier(col)
            if value is None:
                where_parts.append(f"{quoted_col} IS NULL")
            elif isinstance(value, list):
                # IN clause
                placeholders = []
                for v in value:
                    placeholders.append(f"${param_counter}")
                    values.append(v)
                    param_counter += 1
                where_parts.append(f"{quoted_col} IN ({', '.join(placeholders)})")
            else:
                where_parts.append(f"{quoted_col} = ${param_counter}")
                values.append(value)
                param_counter += 1

        where_clause = f" {operator} ".join(where_parts)
        return where_clause, values
