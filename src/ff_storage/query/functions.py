"""SQL functions factory for aggregations.

This module provides the `func` singleton for creating aggregate expressions
in a fluent, readable way.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .aggregations import AggregateExpression

if TYPE_CHECKING:
    pass


class FunctionFactory:
    """
    Factory for creating SQL aggregate function expressions.

    This class provides methods for common SQL aggregate functions.
    Use the singleton `func` instance for convenient access.

    Example:
        from ff_storage.query import func, Query

        # Count all records
        total = await Query(Product).select(func.count()).scalar(db_pool)

        # Count distinct categories
        categories = await (
            Query(Product)
            .select(func.count(Product.field("category"), distinct=True))
            .scalar(db_pool)
        )

        # Group and aggregate
        stats = await (
            Query(Product)
            .group_by(Product.field("category"))
            .select(
                Product.field("category"),
                func.count().label("count"),
                func.avg(Product.field("price")).label("avg_price"),
                func.min(Product.field("price")).label("min_price"),
                func.max(Product.field("price")).label("max_price"),
            )
            .execute(db_pool)
        )
    """

    def count(self, field: "Any | None" = None, *, distinct: bool = False) -> AggregateExpression:
        """
        Create a COUNT aggregate.

        Args:
            field: Field to count (None or "*" for COUNT(*))
            distinct: Use COUNT(DISTINCT field)

        Returns:
            AggregateExpression for COUNT

        Example:
            func.count()  # COUNT(*)
            func.count(Product.field("id"))  # COUNT(t0."id")
            func.count(Product.field("category"), distinct=True)  # COUNT(DISTINCT t0."category")
        """
        field_name = self._get_field_name(field)
        return AggregateExpression("COUNT", field_name, distinct=distinct)

    def sum(self, field: Any) -> AggregateExpression:
        """
        Create a SUM aggregate.

        Args:
            field: Field to sum (FieldProxy or string)

        Returns:
            AggregateExpression for SUM

        Example:
            func.sum(Order.field("total"))
        """
        field_name = self._get_field_name(field)
        return AggregateExpression("SUM", field_name)

    def avg(self, field: Any) -> AggregateExpression:
        """
        Create an AVG aggregate.

        Args:
            field: Field to average (FieldProxy or string)

        Returns:
            AggregateExpression for AVG

        Example:
            func.avg(Product.field("price")).label("average_price")
        """
        field_name = self._get_field_name(field)
        return AggregateExpression("AVG", field_name)

    def min(self, field: Any) -> AggregateExpression:
        """
        Create a MIN aggregate.

        Args:
            field: Field to find minimum (FieldProxy or string)

        Returns:
            AggregateExpression for MIN

        Example:
            func.min(Product.field("price"))
        """
        field_name = self._get_field_name(field)
        return AggregateExpression("MIN", field_name)

    def max(self, field: Any) -> AggregateExpression:
        """
        Create a MAX aggregate.

        Args:
            field: Field to find maximum (FieldProxy or string)

        Returns:
            AggregateExpression for MAX

        Example:
            func.max(Order.field("created_at"))
        """
        field_name = self._get_field_name(field)
        return AggregateExpression("MAX", field_name)

    def _get_field_name(self, field: Any) -> str | None:
        """
        Extract field name from FieldProxy or string.

        Args:
            field: FieldProxy, string, or None

        Returns:
            Field name string or None for COUNT(*)
        """
        if field is None:
            return None
        # Check for FieldProxy first (before string comparison which would invoke __eq__)
        if hasattr(field, "field_name"):
            return field.field_name
        # Now safe to compare strings
        if field == "*":
            return None
        return str(field)


# Singleton instance for convenient access
func = FunctionFactory()
