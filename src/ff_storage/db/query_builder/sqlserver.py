"""
SQL Server query builder implementation.

Handles SQL Server-specific SQL generation:
- Square bracket quoting for identifiers
- Question mark parameters (?)
- OUTPUT clause instead of RETURNING
- SQL Server-specific data types
"""

from typing import Any, Dict, List, Optional, Tuple

from .base import QueryBuilder


class SQLServerQueryBuilder(QueryBuilder):
    """SQL Server-specific query builder."""

    def quote_identifier(self, identifier: str) -> str:
        """
        Quote identifier using SQL Server square brackets.

        Args:
            identifier: Column or table name

        Returns:
            Quoted identifier using square brackets
        """
        # Handle schema.table format
        if "." in identifier:
            parts = identifier.split(".", 1)
            return f"[{parts[0]}].[{parts[1]}]"
        return f"[{identifier}]"

    def build_insert(
        self, table: str, data: Dict[str, Any], returning_fields: Optional[List[str]] = None
    ) -> Tuple[str, List[Any]]:
        """
        Build INSERT query for SQL Server with OUTPUT clause.

        Args:
            table: Table name (can be schema.table)
            data: Dict of column -> value
            returning_fields: Fields to return (uses OUTPUT clause)

        Returns:
            Tuple of (query with $1 placeholders, list of values)
        """
        quoted_table = self.quote_identifier(table)
        columns = list(data.keys())
        quoted_columns = [self.quote_identifier(col) for col in columns]
        values = list(data.values())

        # Use $1, $2, $3 placeholders (adapter will convert to ? format)
        placeholders = ", ".join([f"${i + 1}" for i in range(len(columns))])

        # Build OUTPUT clause if returning fields requested
        output_clause = ""
        if returning_fields:
            if returning_fields == ["*"]:
                output_clause = "OUTPUT INSERTED.*"
            else:
                output_fields = [f"INSERTED.{self.quote_identifier(f)}" for f in returning_fields]
                output_clause = f"OUTPUT {', '.join(output_fields)}"

        query = f"""
            INSERT INTO {quoted_table}
            ({", ".join(quoted_columns)})
            {output_clause}
            VALUES ({placeholders})
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
        Build UPDATE query for SQL Server with OUTPUT clause.

        Args:
            table: Table name
            data: Dict of columns to update
            where: Dict of WHERE conditions
            returning_fields: Fields to return (uses OUTPUT clause)

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

        # Build OUTPUT clause if returning fields requested
        output_clause = ""
        if returning_fields:
            if returning_fields == ["*"]:
                output_clause = "OUTPUT INSERTED.*"
            else:
                output_fields = [f"INSERTED.{self.quote_identifier(f)}" for f in returning_fields]
                output_clause = f"OUTPUT {', '.join(output_fields)}"

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
            {output_clause}
            WHERE {" AND ".join(where_parts)}
        """.strip()

        return query, values

    def build_delete(
        self, table: str, where: Dict[str, Any], returning_fields: Optional[List[str]] = None
    ) -> Tuple[str, List[Any]]:
        """
        Build DELETE query for SQL Server with OUTPUT clause.

        Args:
            table: Table name
            where: Dict of WHERE conditions
            returning_fields: Fields to return (uses OUTPUT clause)

        Returns:
            Tuple of (query with $1 placeholders, list of values)
        """
        quoted_table = self.quote_identifier(table)
        values = []
        param_counter = 1

        # Build OUTPUT clause if returning fields requested
        output_clause = ""
        if returning_fields:
            if returning_fields == ["*"]:
                output_clause = "OUTPUT DELETED.*"
            else:
                output_fields = [f"DELETED.{self.quote_identifier(f)}" for f in returning_fields]
                output_clause = f"OUTPUT {', '.join(output_fields)}"

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
            {output_clause}
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
        Build SELECT query for SQL Server.

        SQL Server uses OFFSET/FETCH instead of LIMIT for pagination.

        Args:
            table: Table name
            columns: List of columns to select (None = *)
            where: Dict of WHERE conditions
            order_by: List of (column, direction) tuples
            limit: Number of rows to fetch
            offset: Number of rows to skip

        Returns:
            Tuple of (query with $1 placeholders, list of values)
        """
        quoted_table = self.quote_identifier(table)
        values = []
        param_counter = 1

        # SELECT clause
        if columns:
            quoted_columns = [self.quote_identifier(col) for col in columns]
            select_clause = ", ".join(quoted_columns)
        else:
            select_clause = "*"

        query_parts = [f"SELECT {select_clause}", f"FROM {quoted_table}"]

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

        # ORDER BY clause (required for OFFSET/FETCH)
        if order_by:
            order_parts = []
            for col, direction in order_by:
                quoted_col = self.quote_identifier(col)
                order_parts.append(f"{quoted_col} {direction.upper()}")
            query_parts.append(f"ORDER BY {', '.join(order_parts)}")
        elif limit is not None or offset is not None:
            # SQL Server requires ORDER BY for OFFSET/FETCH
            # Use a default order if none specified
            query_parts.append("ORDER BY (SELECT NULL)")

        # OFFSET/FETCH for pagination
        if offset is not None:
            query_parts.append(f"OFFSET {offset} ROWS")
        elif limit is not None:
            # OFFSET is required even if 0
            query_parts.append("OFFSET 0 ROWS")

        if limit is not None:
            query_parts.append(f"FETCH NEXT {limit} ROWS ONLY")

        query = " ".join(query_parts)
        return query, values

    def get_param_style(self) -> str:
        """SQL Server uses question mark parameters."""
        return "qmark"

    def build_upsert(
        self,
        table: str,
        data: Dict[str, Any],
        conflict_columns: List[str],
        update_columns: Optional[List[str]] = None,
        returning_fields: Optional[List[str]] = None,
    ) -> Tuple[str, List[Any]]:
        """
        Build MERGE statement for SQL Server (UPSERT equivalent).

        SQL Server uses MERGE instead of INSERT ... ON CONFLICT.

        Args:
            table: Target table name
            data: Data to insert/update
            conflict_columns: Columns to match on (merge condition)
            update_columns: Columns to update on match (None = all except conflict)
            returning_fields: Fields to return via OUTPUT

        Returns:
            Tuple of (query with $1 placeholders, list of values)
        """
        quoted_table = self.quote_identifier(table)
        values = []

        # Prepare columns
        all_columns = list(data.keys())
        if update_columns is None:
            update_columns = [col for col in all_columns if col not in conflict_columns]

        # Build source values with $1, $2, $3 placeholders
        source_placeholders = [f"${i + 1}" for i in range(len(all_columns))]
        for col in all_columns:
            values.append(data[col])

        # Build merge conditions
        merge_conditions = []
        for col in conflict_columns:
            quoted_col = self.quote_identifier(col)
            merge_conditions.append(f"target.{quoted_col} = source.{quoted_col}")

        # Build update SET clause
        update_set = []
        for col in update_columns:
            quoted_col = self.quote_identifier(col)
            update_set.append(f"target.{quoted_col} = source.{quoted_col}")

        # Build insert columns and values
        insert_columns = [self.quote_identifier(col) for col in all_columns]
        insert_values = [f"source.{self.quote_identifier(col)}" for col in all_columns]

        # Build OUTPUT clause if needed
        output_clause = ""
        if returning_fields:
            if returning_fields == ["*"]:
                output_clause = "OUTPUT INSERTED.*"
            else:
                output_fields = [f"INSERTED.{self.quote_identifier(f)}" for f in returning_fields]
                output_clause = f"OUTPUT {', '.join(output_fields)}"

        # Build MERGE statement
        query = f"""
            MERGE {quoted_table} AS target
            USING (SELECT {", ".join(f"{placeholder} AS {self.quote_identifier(col)}" for placeholder, col in zip(source_placeholders, all_columns))}) AS source
            ON {" AND ".join(merge_conditions)}
            WHEN MATCHED THEN
                UPDATE SET {", ".join(update_set)}
            WHEN NOT MATCHED THEN
                INSERT ({", ".join(insert_columns)})
                VALUES ({", ".join(insert_values)})
            {output_clause};
        """.strip()

        return query, values

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
