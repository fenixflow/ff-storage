"""Filter expressions for the query builder.

This module provides the foundation for building type-safe query filters:
- FilterExpression: Represents a filter condition (field operator value)
- FieldProxy: Enables fluent syntax like Model.field("price") > 100
- F: Shorthand factory for creating FieldProxy instances

Security Notes:
    - All user-provided values are parameterized (never interpolated into SQL)
    - LIKE patterns are escaped to prevent wildcard injection
    - Operators are validated against a whitelist to prevent SQL injection

Type Safety Note for FieldProxy:
    FieldProxy overrides __eq__ and __ne__ to return FilterExpression instead
    of bool. This is intentional for building query expressions but violates
    Python's type contract for these magic methods.

    The `# type: ignore[override]` comments suppress mypy warnings about this
    intentional deviation from the expected return type.

    IMPORTANT: DO NOT use FieldProxy in boolean contexts!

    Example of WRONG usage (always True because FilterExpression is truthy):
        if F.price == 100:  # WRONG! This is ALWAYS True
            do_something()

    Example of CORRECT usage (use in filter() method):
        Query(Product).filter(F.price == 100)  # CORRECT
        Query(Product).filter(F.name.contains("test"))  # CORRECT

    If you need to check a boolean field value, always use it within Query:
        # Check if there are products with price == 100
        exists = await Query(Product).filter(F.price == 100).exists(db_pool)

    The same applies to using FieldProxy in `and`, `or`, `not` expressions:
        # WRONG - Python short-circuits on truthiness, not SQL logic
        F.price > 100 and F.status == "active"

        # CORRECT - use AND() and OR() functions
        from ff_storage.query import AND, OR
        Query(Product).filter(AND(F.price > 100, F.status == "active"))
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List, Tuple
from uuid import UUID

from .constants import LIKE_ESCAPE_CHARS, VALID_OPERATORS
from .sql_utils import ColumnRef

if TYPE_CHECKING:
    from .ordering import OrderByClause
    from .subquery import Subquery


def _escape_like_pattern(value: str) -> str:
    """
    Escape special LIKE pattern characters in user input.

    This prevents wildcard injection attacks where user input like "%" or "_"
    could match unintended data.

    Args:
        value: The user-provided string to escape

    Returns:
        Escaped string safe for use in LIKE patterns

    Examples:
        >>> _escape_like_pattern("100%")
        '100\\%'
        >>> _escape_like_pattern("user_name")
        'user\\_name'
    """
    result = value
    # Escape backslash first to avoid double-escaping
    for char, escaped in LIKE_ESCAPE_CHARS.items():
        result = result.replace(char, escaped)
    return result


@dataclass
class FilterExpression:
    """
    Represents a filter condition in a query.

    Examples:
        FilterExpression("price", ">", 100)
        FilterExpression("name", "LIKE", "%test%")
        FilterExpression("status", "IN", ["active", "pending"])

    Attributes:
        field: The field/column name to filter on
        operator: SQL operator (=, !=, <, >, <=, >=, LIKE, ILIKE, IN, etc.)
        value: The value to compare against
        table_alias: Table alias for the column (default: "t0")
    """

    field: str
    operator: str
    value: Any
    table_alias: str = "t0"

    def to_sql(self, param_index: int = 1, tenant_id: UUID | None = None) -> Tuple[str, Any, int]:
        """
        Convert to SQL clause with parameter placeholder.

        Args:
            param_index: Starting parameter index for $N placeholders
            tenant_id: Optional tenant ID for subquery multi-tenant filtering.
                      CRITICAL: For IN_SUBQUERY expressions with multi-tenant models,
                      this must be provided to ensure proper data isolation.

        Returns:
            Tuple of (sql_clause, param_value_or_list, next_param_index)

        Raises:
            ValueError: If operator is not in the allowed whitelist

        Examples:
            >>> expr = FilterExpression("price", ">", 100)
            >>> expr.to_sql(1)
            ('t0."price" > $1', 100, 2)

            >>> expr = FilterExpression("status", "IN", ["a", "b"])
            >>> expr.to_sql(1)
            ('t0."status" IN ($1, $2)', ['a', 'b'], 3)
        """
        # Validate operator against whitelist to prevent SQL injection
        if self.operator not in VALID_OPERATORS:
            raise ValueError(
                f"Invalid operator: {self.operator!r}. Must be one of: {sorted(VALID_OPERATORS)}"
            )

        column = ColumnRef.format(self.field, self.table_alias)

        # NULL comparisons
        if self.operator == "IS NULL":
            return f"{column} IS NULL", None, param_index

        if self.operator == "IS NOT NULL":
            return f"{column} IS NOT NULL", None, param_index

        # IN clause
        if self.operator == "IN":
            if not self.value:
                return "FALSE", None, param_index  # Empty IN is always false
            placeholders = ", ".join(f"${param_index + i}" for i in range(len(self.value)))
            return (
                f"{column} IN ({placeholders})",
                list(self.value),
                param_index + len(self.value),
            )

        # NOT IN clause
        if self.operator == "NOT IN":
            if not self.value:
                return "TRUE", None, param_index  # Empty NOT IN is always true
            placeholders = ", ".join(f"${param_index + i}" for i in range(len(self.value)))
            return (
                f"{column} NOT IN ({placeholders})",
                list(self.value),
                param_index + len(self.value),
            )

        # IN_SUBQUERY clause
        if self.operator == "IN_SUBQUERY":
            from .subquery import Subquery

            if not isinstance(self.value, Subquery):
                raise ValueError("IN_SUBQUERY operator requires a Subquery value")
            # Pass tenant_id to subquery for multi-tenant data isolation
            subquery_sql, subquery_params, param_index = self.value.to_sql(
                param_index, tenant_id=tenant_id
            )
            return (
                f"{column} IN ({subquery_sql})",
                subquery_params,
                param_index,
            )

        # NOT IN_SUBQUERY clause
        if self.operator == "NOT IN_SUBQUERY":
            from .subquery import Subquery

            if not isinstance(self.value, Subquery):
                raise ValueError("NOT IN_SUBQUERY operator requires a Subquery value")
            # Pass tenant_id to subquery for multi-tenant data isolation
            subquery_sql, subquery_params, param_index = self.value.to_sql(
                param_index, tenant_id=tenant_id
            )
            return (
                f"{column} NOT IN ({subquery_sql})",
                subquery_params,
                param_index,
            )

        # BETWEEN clause
        if self.operator == "BETWEEN":
            low, high = self.value
            return (
                f"{column} BETWEEN ${param_index} AND ${param_index + 1}",
                [low, high],
                param_index + 2,
            )

        # Standard operators: =, !=, <, >, <=, >=, LIKE, ILIKE
        return f"{column} {self.operator} ${param_index}", self.value, param_index + 1

    def with_alias(self, alias: str) -> "FilterExpression":
        """Return a copy of this expression with a different table alias."""
        return FilterExpression(
            field=self.field,
            operator=self.operator,
            value=self.value,
            table_alias=alias,
        )


@dataclass
class CompositeExpression:
    """
    Combines FilterExpressions with AND/OR logic.

    This class enables complex filter expressions like:
    - (A OR B) AND C
    - A AND (B OR C) AND D
    - Nested combinations

    Examples:
        >>> expr = OR(F.status == "active", F.status == "pending")
        >>> sql, params, idx = expr.to_sql(1)
        >>> sql
        '(t0."status" = $1 OR t0."status" = $2)'

        >>> complex = AND(
        ...     F.category == "electronics",
        ...     OR(F.price > 100, F.featured == True)
        ... )

    Attributes:
        expressions: Tuple of FilterExpression or CompositeExpression objects
        operator: Logical operator ("AND" or "OR")
    """

    expressions: tuple
    operator: str = "AND"

    def __post_init__(self) -> None:
        """Validate the operator."""
        if self.operator not in ("AND", "OR"):
            raise ValueError(
                f"Invalid composite operator: {self.operator!r}. Must be 'AND' or 'OR'."
            )
        if len(self.expressions) < 2:
            raise ValueError("CompositeExpression requires at least 2 expressions.")

    def to_sql(
        self, param_index: int = 1, tenant_id: UUID | None = None
    ) -> Tuple[str, List[Any], int]:
        """
        Generate SQL with proper parentheses for precedence.

        Args:
            param_index: Starting parameter index for $N placeholders
            tenant_id: Optional tenant ID for subquery multi-tenant filtering

        Returns:
            Tuple of (sql_clause, param_values, next_param_index)

        Examples:
            >>> expr = OR(F.status == "a", F.status == "b")
            >>> sql, params, idx = expr.to_sql(1)
            >>> sql
            '(t0."status" = $1 OR t0."status" = $2)'
            >>> params
            ['a', 'b']
        """
        parts: List[str] = []
        params: List[Any] = []

        for expr in self.expressions:
            sql, value, param_index = expr.to_sql(param_index, tenant_id=tenant_id)
            parts.append(sql)
            if value is not None:
                if isinstance(value, (list, tuple)):
                    params.extend(value)
                else:
                    params.append(value)

        joined = f" {self.operator} ".join(parts)
        return f"({joined})", params, param_index

    def with_alias(self, alias: str) -> "CompositeExpression":
        """Return a copy with all expressions using a different table alias."""
        new_expressions = tuple(expr.with_alias(alias) for expr in self.expressions)
        return CompositeExpression(new_expressions, self.operator)


def AND(*expressions: "FilterExpression | CompositeExpression") -> CompositeExpression:
    """
    Combine expressions with AND logic.

    Args:
        *expressions: Two or more FilterExpression or CompositeExpression objects

    Returns:
        CompositeExpression with AND operator

    Example:
        >>> expr = AND(F.price > 100, F.status == "active")
        >>> sql, params, _ = expr.to_sql(1)
        >>> sql
        '(t0."price" > $1 AND t0."status" = $2)'
    """
    return CompositeExpression(expressions, "AND")


def OR(*expressions: "FilterExpression | CompositeExpression") -> CompositeExpression:
    """
    Combine expressions with OR logic.

    Args:
        *expressions: Two or more FilterExpression or CompositeExpression objects

    Returns:
        CompositeExpression with OR operator

    Example:
        >>> expr = OR(F.status == "active", F.status == "pending")
        >>> sql, params, _ = expr.to_sql(1)
        >>> sql
        '(t0."status" = $1 OR t0."status" = $2)'
    """
    return CompositeExpression(expressions, "OR")


class FieldProxy:
    """
    Proxy for a model field that enables expression building.

    This class allows building filter expressions using Python operators:

    Examples:
        >>> proxy = FieldProxy("price")
        >>> expr = proxy > 100
        >>> expr.operator
        '>'
        >>> expr.value
        100

        >>> expr = FieldProxy("name").contains("test")
        >>> expr.operator
        'LIKE'
        >>> expr.value
        '%test%'

    Attributes:
        field_name: The name of the field this proxy represents
        model_class: Optional reference to the model class
    """

    def __init__(self, field_name: str, model_class: type | None = None):
        """
        Initialize a FieldProxy.

        Args:
            field_name: The name of the field
            model_class: Optional model class reference for introspection
        """
        self.field_name = field_name
        self.model_class = model_class

    def __repr__(self) -> str:
        if self.model_class:
            return f"<FieldProxy {self.model_class.__name__}.{self.field_name}>"
        return f"<FieldProxy {self.field_name}>"

    def __bool__(self) -> bool:
        """
        Prevent accidental use in boolean context.

        FieldProxy objects should only be used in Query.filter() expressions,
        not in Python boolean contexts like `if` statements.

        Raises:
            TypeError: Always, with guidance on correct usage.
        """
        raise TypeError(
            f"Cannot use FieldProxy '{self.field_name}' in boolean context. "
            "FieldProxy is for building query expressions, not boolean checks.\n"
            "Wrong: if F.active:  # Always True!\n"
            "Right: Query(Model).filter(F.active == True).exists(db_pool)"
        )

    # -------------------------------------------------------------------------
    # Comparison operators
    # -------------------------------------------------------------------------

    def __eq__(self, other: Any) -> FilterExpression:  # type: ignore[override]
        """Equality comparison. None becomes IS NULL."""
        if other is None:
            return FilterExpression(self.field_name, "IS NULL", None)
        return FilterExpression(self.field_name, "=", other)

    def __ne__(self, other: Any) -> FilterExpression:  # type: ignore[override]
        """Inequality comparison. None becomes IS NOT NULL."""
        if other is None:
            return FilterExpression(self.field_name, "IS NOT NULL", None)
        return FilterExpression(self.field_name, "!=", other)

    def __lt__(self, other: Any) -> FilterExpression:
        """Less than comparison."""
        return FilterExpression(self.field_name, "<", other)

    def __le__(self, other: Any) -> FilterExpression:
        """Less than or equal comparison."""
        return FilterExpression(self.field_name, "<=", other)

    def __gt__(self, other: Any) -> FilterExpression:
        """Greater than comparison."""
        return FilterExpression(self.field_name, ">", other)

    def __ge__(self, other: Any) -> FilterExpression:
        """Greater than or equal comparison."""
        return FilterExpression(self.field_name, ">=", other)

    # -------------------------------------------------------------------------
    # String operations
    # -------------------------------------------------------------------------

    def contains(self, value: str) -> FilterExpression:
        """
        Case-sensitive contains (LIKE %value%).

        Special LIKE characters (%, _, \\) in value are escaped automatically.

        Args:
            value: The substring to search for

        Returns:
            FilterExpression with LIKE operator
        """
        escaped = _escape_like_pattern(value)
        return FilterExpression(self.field_name, "LIKE", f"%{escaped}%")

    def icontains(self, value: str) -> FilterExpression:
        """
        Case-insensitive contains (ILIKE %value%).

        Special LIKE characters (%, _, \\) in value are escaped automatically.

        Args:
            value: The substring to search for

        Returns:
            FilterExpression with ILIKE operator
        """
        escaped = _escape_like_pattern(value)
        return FilterExpression(self.field_name, "ILIKE", f"%{escaped}%")

    def startswith(self, value: str) -> FilterExpression:
        """
        Starts with (LIKE value%).

        Special LIKE characters (%, _, \\) in value are escaped automatically.

        Args:
            value: The prefix to match

        Returns:
            FilterExpression with LIKE operator
        """
        escaped = _escape_like_pattern(value)
        return FilterExpression(self.field_name, "LIKE", f"{escaped}%")

    def endswith(self, value: str) -> FilterExpression:
        """
        Ends with (LIKE %value).

        Special LIKE characters (%, _, \\) in value are escaped automatically.

        Args:
            value: The suffix to match

        Returns:
            FilterExpression with LIKE operator
        """
        escaped = _escape_like_pattern(value)
        return FilterExpression(self.field_name, "LIKE", f"%{escaped}")

    def like(self, pattern: str) -> FilterExpression:
        """
        Case-sensitive pattern match (LIKE).

        Args:
            pattern: The LIKE pattern (use % for wildcards)

        Returns:
            FilterExpression with LIKE operator
        """
        return FilterExpression(self.field_name, "LIKE", pattern)

    def ilike(self, pattern: str) -> FilterExpression:
        """
        Case-insensitive pattern match (ILIKE).

        Args:
            pattern: The ILIKE pattern (use % for wildcards)

        Returns:
            FilterExpression with ILIKE operator
        """
        return FilterExpression(self.field_name, "ILIKE", pattern)

    # -------------------------------------------------------------------------
    # Collection operations
    # -------------------------------------------------------------------------

    def in_(self, values: "List[Any] | Subquery") -> FilterExpression:
        """
        IN clause with list of values or subquery.

        Args:
            values: List of values to match against, or a Subquery

        Returns:
            FilterExpression with IN or IN_SUBQUERY operator

        Example:
            # With list of values
            query.filter(F.status.in_(["active", "pending"]))

            # With subquery
            active_ids = Query(User).filter(F.active == True).subquery()
            query.filter(F.user_id.in_(active_ids))
        """
        from .subquery import Subquery

        if isinstance(values, Subquery):
            return FilterExpression(self.field_name, "IN_SUBQUERY", values)
        return FilterExpression(self.field_name, "IN", list(values))

    def not_in(self, values: "List[Any] | Subquery") -> FilterExpression:
        """
        NOT IN clause with list of values or subquery.

        Args:
            values: List of values to exclude, or a Subquery

        Returns:
            FilterExpression with NOT IN or NOT IN_SUBQUERY operator

        Example:
            # With list of values
            query.filter(F.status.not_in(["deleted", "archived"]))

            # With subquery
            banned_ids = Query(BannedUser).subquery()
            query.filter(F.user_id.not_in(banned_ids))
        """
        from .subquery import Subquery

        if isinstance(values, Subquery):
            return FilterExpression(self.field_name, "NOT IN_SUBQUERY", values)
        return FilterExpression(self.field_name, "NOT IN", list(values))

    def between(self, low: Any, high: Any) -> FilterExpression:
        """
        BETWEEN clause.

        Args:
            low: Lower bound (inclusive)
            high: Upper bound (inclusive)

        Returns:
            FilterExpression with BETWEEN operator
        """
        return FilterExpression(self.field_name, "BETWEEN", (low, high))

    # -------------------------------------------------------------------------
    # Null checks
    # -------------------------------------------------------------------------

    def is_null(self) -> FilterExpression:
        """IS NULL check."""
        return FilterExpression(self.field_name, "IS NULL", None)

    def is_not_null(self) -> FilterExpression:
        """IS NOT NULL check."""
        return FilterExpression(self.field_name, "IS NOT NULL", None)

    # -------------------------------------------------------------------------
    # Ordering
    # -------------------------------------------------------------------------

    def asc(self, nulls: str | None = None) -> "OrderByClause":
        """
        Ascending order.

        Args:
            nulls: Optional NULLS FIRST or NULLS LAST

        Returns:
            OrderByClause for ascending order
        """
        from .ordering import OrderByClause

        return OrderByClause(self.field_name, "ASC", nulls=nulls)

    def desc(self, nulls: str | None = None) -> "OrderByClause":
        """
        Descending order.

        Args:
            nulls: Optional NULLS FIRST or NULLS LAST

        Returns:
            OrderByClause for descending order
        """
        from .ordering import OrderByClause

        return OrderByClause(self.field_name, "DESC", nulls=nulls)


class _FieldFactory:
    """
    Factory for creating FieldProxy instances.

    This provides a convenient shorthand for creating field proxies:

    Examples:
        >>> F.price > 100  # Same as FieldProxy("price") > 100
        >>> F["field_name"].contains("test")
    """

    def __getattr__(self, field_name: str) -> FieldProxy:
        """Create a FieldProxy for the given field name."""
        if field_name.startswith("_"):
            raise AttributeError(field_name)
        return FieldProxy(field_name)

    def __getitem__(self, field_name: str) -> FieldProxy:
        """Create a FieldProxy using bracket notation."""
        return FieldProxy(field_name)


# Singleton instance for convenient access
F = _FieldFactory()
