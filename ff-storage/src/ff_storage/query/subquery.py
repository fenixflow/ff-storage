"""Subquery support for the query builder.

This module provides the Subquery class which allows using Query results
as subqueries in other queries, particularly in IN clauses.

Example:
    # Find products in categories that have sales
    active_category_ids = (
        Query(Sale)
        .filter(Sale.field("completed") == True)
        .select(Sale.field("category_id"))
        .subquery("active_cats")
    )

    products = await (
        Query(Product)
        .filter(Product.field("category_id").in_(active_category_ids))
        .execute(db_pool, tenant_id)
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, List, Tuple, TypeVar
from uuid import UUID

if TYPE_CHECKING:
    from ..pydantic_support.base import PydanticModel
    from .builder import Query

T = TypeVar("T", bound="PydanticModel")


class Subquery(Generic[T]):
    """
    Wraps a Query to be used as a subquery in another query.

    A Subquery generates SQL that can be embedded in IN clauses or other
    contexts that accept a subquery.

    Attributes:
        query: The Query instance to use as a subquery
        alias: Optional alias for the subquery
        select_column: The column to select (for IN clause subqueries)

    Example:
        # Subquery returning IDs for use in IN clause
        subq = Query(Author).filter(F.active == True).subquery("active_authors")
        posts = Query(Post).filter(F.author_id.in_(subq)).execute(db_pool)

        # With explicit column selection
        subq = (
            Query(Sale)
            .filter(F.completed == True)
            .select(F.product_id)
            .subquery("sold_products")
        )
        products = Query(Product).filter(F.id.in_(subq)).execute(db_pool)
    """

    def __init__(
        self,
        query: "Query[T]",
        alias: str = "sq",
        select_column: str | None = None,
    ):
        """
        Initialize a Subquery.

        Args:
            query: The Query instance to wrap
            alias: Alias for the subquery (default: "sq")
            select_column: Column to select. If None, uses "id" by default
                          for IN clause subqueries.
        """
        self.query = query
        self.alias = alias
        self.select_column = select_column or "id"

    def __repr__(self) -> str:
        return f"<Subquery {self.alias} from {self.query.model_class.__name__}>"

    def to_sql(
        self, param_index: int = 1, tenant_id: UUID | None = None
    ) -> Tuple[str, List[Any], int]:
        """
        Generate SQL for this subquery.

        Args:
            param_index: Starting parameter index for $N placeholders
            tenant_id: Optional tenant ID for multi-tenant filtering. CRITICAL:
                      For multi-tenant models, this MUST be provided to ensure
                      proper data isolation. Without it, the subquery may return
                      IDs from all tenants.

        Returns:
            Tuple of (sql_string, params_list, next_param_index)
        """
        from .sql_utils import ColumnRef

        # Build the inner query SQL
        sql_parts: List[str] = []
        params: List[Any] = []

        # Get model metadata
        model_class = self.query.model_class
        table_name = model_class.__table_name__
        schema = getattr(model_class, "__schema__", "public")
        temporal_strategy = getattr(model_class, "__temporal_strategy__", "none")
        soft_delete = getattr(model_class, "__soft_delete__", True)
        multi_tenant = getattr(model_class, "__multi_tenant__", True)

        full_table = f'"{schema}"."{table_name}"'

        # SELECT clause - just the column we need for IN clause
        col = ColumnRef.format(self.select_column, "t0")
        sql_parts.append(f"SELECT {col} FROM {full_table} t0")

        # WHERE clause
        where_parts: List[str] = []

        # Temporal filtering
        if temporal_strategy == "scd2":
            where_parts.append("t0.valid_to IS NULL")

        # Soft delete filtering
        if soft_delete:
            where_parts.append("t0.deleted_at IS NULL")

        # Multi-tenant filtering - CRITICAL for data isolation
        # Subqueries must filter by tenant_id to prevent cross-tenant data leaks
        if multi_tenant and tenant_id is not None:
            where_parts.append(f't0."tenant_id" = ${param_index}')
            params.append(tenant_id)
            param_index += 1

        # User filters from the query
        for expr in self.query._filters:
            # Pass tenant_id for nested subqueries
            expr_sql, expr_value, param_index = expr.to_sql(param_index, tenant_id=tenant_id)
            where_parts.append(expr_sql)
            if expr_value is not None:
                if isinstance(expr_value, (list, tuple)):
                    params.extend(expr_value)
                else:
                    params.append(expr_value)

        if where_parts:
            sql_parts.append(" WHERE " + " AND ".join(where_parts))

        # LIMIT clause (useful for EXISTS subqueries)
        # Validate LIMIT to prevent injection (defense-in-depth)
        if self.query._limit is not None:
            limit = self.query._limit
            if not isinstance(limit, int) or limit < 0:
                raise ValueError(f"LIMIT must be a non-negative integer, got {limit!r}")
            sql_parts.append(f" LIMIT {limit}")

        sql = "".join(sql_parts)
        return sql, params, param_index
