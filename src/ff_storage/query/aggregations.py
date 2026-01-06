"""Aggregation expressions for the query builder.

This module provides classes for building SQL aggregate expressions like
COUNT, SUM, AVG, MIN, MAX with support for DISTINCT and aliasing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .sql_utils import ColumnRef

if TYPE_CHECKING:
    pass


@dataclass
class AggregateExpression:
    """
    Represents a SQL aggregate function call.

    Examples:
        >>> func.count()
        AggregateExpression("COUNT", "*", None)

        >>> func.avg(Product.field("price"))
        AggregateExpression("AVG", "price", None)

        >>> func.count(distinct=True).label("unique_count")
        AggregateExpression("COUNT", "*", "unique_count", distinct=True)

    Attributes:
        function_name: SQL function (COUNT, SUM, AVG, MIN, MAX)
        field: Field name or "*" for COUNT(*)
        alias: Optional AS alias
        distinct: Whether to use DISTINCT
    """

    function_name: str  # COUNT, SUM, AVG, MIN, MAX
    field: str | None  # None for COUNT(*)
    alias: str | None = None
    distinct: bool = False

    def to_sql(self, table_alias: str = "t0") -> str:
        """
        Convert to SQL expression.

        Args:
            table_alias: Table alias prefix for column

        Returns:
            SQL string like 'COUNT(DISTINCT t0."price") AS total'

        Example:
            >>> expr = AggregateExpression("AVG", "price", "avg_price")
            >>> expr.to_sql("t0")
            'AVG(t0."price") AS avg_price'
        """
        # Build the column reference
        if self.field is None or self.field == "*":
            col = "*"
        else:
            col = ColumnRef.format(self.field, table_alias)

        # Build DISTINCT if needed
        if self.distinct and col != "*":
            col = f"DISTINCT {col}"

        # Build function call
        sql = f"{self.function_name}({col})"

        # Add alias if specified - use quote_identifier to escape properly
        if self.alias:
            sql += f" AS {ColumnRef.quote_identifier(self.alias)}"

        return sql

    def label(self, name: str) -> "AggregateExpression":
        """
        Set an alias for this aggregate.

        Args:
            name: The alias name

        Returns:
            New AggregateExpression with alias set

        Example:
            >>> func.avg(Product.field("price")).label("average_price")
        """
        return AggregateExpression(
            function_name=self.function_name,
            field=self.field,
            alias=name,
            distinct=self.distinct,
        )


@dataclass
class GroupByClause:
    """
    Represents a GROUP BY clause field.

    Attributes:
        field: Field name to group by
        table_alias: Table alias (default: "t0")
    """

    field: str
    table_alias: str = "t0"

    def to_sql(self) -> str:
        """Convert to SQL fragment."""
        return ColumnRef.format(self.field, self.table_alias)
