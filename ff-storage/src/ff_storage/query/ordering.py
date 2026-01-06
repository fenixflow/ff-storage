"""Ordering clauses for the query builder.

This module provides OrderByClause for defining sort order in queries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .constants import NULLS_POSITIONS, ORDER_DIRECTIONS
from .sql_utils import ColumnRef


@dataclass
class OrderByClause:
    """
    Represents an ORDER BY clause in a query.

    Examples:
        >>> clause = OrderByClause("created_at", "DESC")
        >>> clause.to_sql()
        't0."created_at" DESC'

        >>> clause = OrderByClause("name", "ASC", nulls="LAST")
        >>> clause.to_sql()
        't0."name" ASC NULLS LAST'

    Attributes:
        field: The field/column name to order by
        direction: Sort direction (ASC or DESC)
        nulls: Optional NULLS FIRST or NULLS LAST
        table_alias: Table alias for the column (default: "t0")
    """

    field: str
    direction: Literal["ASC", "DESC"] = "ASC"
    nulls: Literal["FIRST", "LAST"] | None = None
    table_alias: str = "t0"

    def to_sql(self) -> str:
        """
        Convert to SQL ORDER BY clause fragment.

        Returns:
            SQL string like 't0."field" DESC NULLS LAST'

        Raises:
            ValueError: If direction or nulls contains invalid values
        """
        # Validate direction to prevent SQL injection
        if self.direction not in ORDER_DIRECTIONS:
            raise ValueError(
                f"Invalid ORDER BY direction: {self.direction!r}. "
                f"Must be one of: {sorted(ORDER_DIRECTIONS)}"
            )

        sql = f"{ColumnRef.format(self.field, self.table_alias)} {self.direction}"

        # Validate nulls to prevent SQL injection
        if self.nulls:
            if self.nulls not in NULLS_POSITIONS:
                raise ValueError(
                    f"Invalid NULLS value: {self.nulls!r}. "
                    f"Must be one of: {sorted(NULLS_POSITIONS)}"
                )
            sql += f" NULLS {self.nulls}"

        return sql

    def with_alias(self, alias: str) -> "OrderByClause":
        """Return a copy of this clause with a different table alias."""
        return OrderByClause(
            field=self.field,
            direction=self.direction,
            nulls=self.nulls,
            table_alias=alias,
        )
