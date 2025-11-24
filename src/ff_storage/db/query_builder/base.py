"""
Abstract base class for SQL query builders.

Defines the interface that all database-specific query builders must implement.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple


class QueryBuilder(ABC):
    """
    Abstract base for database-specific SQL query builders.

    Query builders are responsible for:
    1. Generating dialect-specific SQL queries
    2. Handling identifier quoting (reserved keywords, special characters)
    3. Building parameter placeholder lists
    4. No connection handling (that's the DB layer's job)

    Subclasses must implement all abstract methods for their target database.
    """

    @abstractmethod
    def quote_identifier(self, identifier: str) -> str:
        """
        Quote an SQL identifier (table, column, schema name).

        Handles:
        - Reserved keywords (e.g., "limit", "order", "user")
        - Special characters
        - Schema-qualified names (e.g., "schema.table")

        Args:
            identifier: Unquoted identifier or schema.table

        Returns:
            Properly quoted identifier for this database dialect

        Examples:
            PostgreSQL: quote_identifier("user") → '"user"'
            PostgreSQL: quote_identifier("public.users") → '"public"."users"'
            MySQL: quote_identifier("order") → '`order`'
        """
        pass

    @abstractmethod
    def build_insert(self, table: str, data: Dict[str, Any]) -> Tuple[str, List[Any]]:
        """
        Build INSERT query with RETURNING clause (if supported).

        Args:
            table: Table name (may be schema-qualified like "schema.table")
            data: Dictionary of column_name → value

        Returns:
            Tuple of (query_string, parameter_values)

        Examples:
            PostgreSQL:
                build_insert("users", {"name": "John", "age": 30})
                → ('INSERT INTO "users" ("name", "age") VALUES ($1, $2) RETURNING *', ['John', 30])

            MySQL:
                build_insert("users", {"name": "John", "age": 30})
                → ('INSERT INTO `users` (`name`, `age`) VALUES (?, ?)', ['John', 30])
        """
        pass

    @abstractmethod
    def build_update(
        self, table: str, data: Dict[str, Any], where: Dict[str, Any]
    ) -> Tuple[str, List[Any]]:
        """
        Build UPDATE query with WHERE clause.

        Args:
            table: Table name (may be schema-qualified)
            data: Dictionary of column_name → value to update
            where: Dictionary of column_name → value for WHERE clause

        Returns:
            Tuple of (query_string, parameter_values)

        Examples:
            PostgreSQL:
                build_update("users", {"age": 31}, {"id": 123})
                → ('UPDATE "users" SET "age" = $2 WHERE "id" = $1 RETURNING *', [123, 31])

        Note:
            Parameter order: WHERE values come first, then SET values
            This matches the common pattern in temporal strategies
        """
        pass

    @abstractmethod
    def build_where_clause(
        self, filters: Dict[str, Any], base_param_count: int = 0, operator: str = "AND"
    ) -> Tuple[str, List[Any]]:
        """
        Build WHERE clause from filters dictionary.

        Handles:
        - NULL values: column_name IS NULL
        - Lists/tuples: column_name IN ($1, $2, $3)
        - Single values: column_name = $1
        - Proper identifier quoting

        Args:
            filters: Dictionary of column_name → value
            base_param_count: Number of parameters already in query (for $N numbering)
            operator: Join operator ("AND" or "OR")

        Returns:
            Tuple of (where_clause_string, parameter_values)

        Examples:
            PostgreSQL:
                build_where_clause({"name": "John", "age": None}, base_param_count=0)
                → ('"name" = $1 AND "age" IS NULL', ['John'])

                build_where_clause({"id": [1, 2, 3]}, base_param_count=0)
                → ('"id" IN ($1, $2, $3)', [1, 2, 3])
        """
        pass

    def build_select(
        self,
        table: str,
        columns: List[str] = None,
        where: Dict[str, Any] = None,
        limit: int = None,
        offset: int = None,
        order_by: List[str] = None,
    ) -> Tuple[str, List[Any]]:
        """
        Build SELECT query (default implementation).

        Subclasses can override for database-specific features.

        Args:
            table: Table name (may be schema-qualified)
            columns: List of column names (None = SELECT *)
            where: Dictionary for WHERE clause
            limit: Maximum rows to return
            offset: Number of rows to skip
            order_by: List of "column" or "column DESC"

        Returns:
            Tuple of (query_string, parameter_values)
        """
        # Build column list
        if columns:
            col_list = ", ".join(self.quote_identifier(col) for col in columns)
        else:
            col_list = "*"

        quoted_table = self.quote_identifier(table)
        query = f"SELECT {col_list} FROM {quoted_table}"
        values = []

        # Add WHERE clause
        if where:
            where_clause, where_values = self.build_where_clause(where)
            query += f" WHERE {where_clause}"
            values.extend(where_values)

        # Add ORDER BY
        if order_by:
            # Parse "column" or "column DESC"
            order_parts = []
            for order_spec in order_by:
                parts = order_spec.split()
                col = self.quote_identifier(parts[0])
                direction = f" {parts[1]}" if len(parts) > 1 else ""
                order_parts.append(f"{col}{direction}")
            query += f" ORDER BY {', '.join(order_parts)}"

        # Add LIMIT/OFFSET (subclasses may override for dialect differences)
        if limit is not None:
            query += f" LIMIT {limit}"
        if offset is not None:
            query += f" OFFSET {offset}"

        return query, values
