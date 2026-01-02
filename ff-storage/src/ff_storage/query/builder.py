"""Fluent query builder for ff-storage models.

This module provides the Query class for building database queries with a fluent API.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, List, Type, TypeVar
from uuid import UUID

from .constants import JOIN_TYPES
from .expressions import CompositeExpression, FieldProxy, FilterExpression
from .ordering import OrderByClause

if TYPE_CHECKING:
    from ..db.pool.postgres import PostgresPool
    from ..pydantic_support.base import PydanticModel
    from ..relationships.descriptor import RelationshipProxy
    from .aggregations import AggregateExpression


T = TypeVar("T", bound="PydanticModel")


@dataclass
class JoinConfig:
    """Configuration for a JOIN clause."""

    target_model: Type["PydanticModel"]
    join_type: str = "INNER"  # INNER, LEFT, RIGHT
    on_clause: str | None = None  # Auto-generated if None
    alias: str = ""
    via_relationship: str | None = None  # Relationship name if joined via relationship


class Query(Generic[T]):
    """
    Fluent query builder for PydanticModel classes.

    Provides a type-safe, chainable API for building database queries with
    automatic temporal and multi-tenant awareness.

    IMPORTANT - Mutation Behavior:
        Query methods mutate and return self for chaining. Create a new
        Query() for each independent query chain:

        # CORRECT - separate Query instances
        active = Query(Product).filter(Product.active == True)
        inactive = Query(Product).filter(Product.active == False)

        # WRONG - second filter modifies the first query
        base = Query(Product)
        active = base.filter(Product.active == True)
        inactive = base.filter(Product.active == False)  # Has BOTH filters!

    Example:
        results = await (
            Query(Product)
            .filter(Product.field("price") > 100)
            .filter(Product.field("status") == "active")
            .order_by(Product.field("created_at").desc())
            .limit(10)
            .execute(db_pool, tenant_id=tenant)
        )

    Attributes:
        model_class: The PydanticModel class being queried
    """

    def __init__(self, model_class: Type[T]):
        """
        Initialize a Query for the given model class.

        Args:
            model_class: The PydanticModel class to query
        """
        self.model_class = model_class
        self._filters: List[FilterExpression | CompositeExpression] = []
        self._joins: List[JoinConfig] = []
        self._order_by: List[OrderByClause] = []
        self._group_by: List[FieldProxy] = []
        self._having: List[FilterExpression | CompositeExpression] = []
        self._select_fields: List[FieldProxy | "AggregateExpression"] = []
        self._limit: int | None = None
        self._offset: int | None = None
        self._eager_load: List[str] = []
        self._alias_counter = 1

    def __repr__(self) -> str:
        """
        Return a readable representation of the query for debugging.

        Example:
            >>> repr(Query(Product).filter(F.price > 100).limit(10))
            "Query(Product).filter(1 conditions).limit(10)"
        """
        parts = [f"Query({self.model_class.__name__})"]

        if self._filters:
            parts.append(f".filter({len(self._filters)} conditions)")
        if self._joins:
            parts.append(f".join({len(self._joins)} tables)")
        if self._order_by:
            parts.append(f".order_by({len(self._order_by)} fields)")
        if self._group_by:
            parts.append(f".group_by({len(self._group_by)} fields)")
        if self._having:
            parts.append(f".having({len(self._having)} conditions)")
        if self._select_fields:
            parts.append(f".select({len(self._select_fields)} fields)")
        if self._limit is not None:
            parts.append(f".limit({self._limit})")
        if self._offset is not None:
            parts.append(f".offset({self._offset})")
        if self._eager_load:
            parts.append(f".load({self._eager_load})")

        return "".join(parts)

    # -------------------------------------------------------------------------
    # Copying
    # -------------------------------------------------------------------------

    def copy(self) -> "Query[T]":
        """
        Create an independent copy of this query for safe branching.

        Since Query methods mutate and return self for chaining, creating
        branches from a base query requires making a copy first.

        Returns:
            A new Query instance with all the same configuration

        Example:
            # Safe branching with copy()
            base = Query(Product).filter(F.category == "electronics")
            expensive = base.copy().filter(F.price > 1000)
            cheap = base.copy().filter(F.price < 100)
            # base, expensive, and cheap are independent queries
        """
        new_query: Query[T] = Query(self.model_class)
        new_query._filters = self._filters.copy()
        new_query._joins = self._joins.copy()
        new_query._order_by = self._order_by.copy()
        new_query._group_by = self._group_by.copy()
        new_query._having = self._having.copy()
        new_query._select_fields = self._select_fields.copy()
        new_query._limit = self._limit
        new_query._offset = self._offset
        new_query._eager_load = self._eager_load.copy()
        new_query._alias_counter = self._alias_counter
        return new_query

    # -------------------------------------------------------------------------
    # Filtering
    # -------------------------------------------------------------------------

    def filter(self, *expressions: "FilterExpression | CompositeExpression") -> "Query[T]":
        """
        Add filter conditions to the query.

        Multiple calls to filter() are ANDed together. Use OR() to combine
        conditions with OR logic.

        Args:
            expressions: FilterExpression or CompositeExpression objects

        Returns:
            Self for chaining

        Example:
            # Simple filters (ANDed together)
            query.filter(Product.field("price") > 100)
            query.filter(F.status == "active", F.category == "electronics")

            # OR conditions
            from ff_storage.query import OR
            query.filter(OR(F.status == "active", F.status == "pending"))

            # Complex nested conditions
            from ff_storage.query import AND, OR
            query.filter(
                AND(
                    F.category == "electronics",
                    OR(F.price > 100, F.featured == True)
                )
            )
        """
        self._filters.extend(expressions)
        return self

    def filter_by(self, **kwargs: Any) -> "Query[T]":
        """
        Add simple equality filters using keyword arguments.

        Args:
            **kwargs: Field=value pairs for equality filters

        Returns:
            Self for chaining

        Example:
            query.filter_by(status="active", category="electronics")
        """
        for field_name, value in kwargs.items():
            if value is None:
                self._filters.append(FilterExpression(field_name, "IS NULL", None))
            else:
                self._filters.append(FilterExpression(field_name, "=", value))
        return self

    # -------------------------------------------------------------------------
    # Joins
    # -------------------------------------------------------------------------

    def join(
        self,
        target: "Type[PydanticModel] | RelationshipProxy",
        *,
        on: str | None = None,
        join_type: str = "INNER",
    ) -> "Query[T]":
        """
        Add a JOIN clause to the query.

        Args:
            target: Model class or relationship proxy to join
            on: Custom ON clause (auto-generated if not provided).
                SECURITY: Must be in format 'alias.column = alias.column'.
                Never pass user-controlled strings to this parameter.
            join_type: JOIN type (INNER, LEFT, RIGHT, FULL, CROSS)

        Returns:
            Self for chaining

        Raises:
            ValueError: If join_type is invalid or on clause has invalid format

        Example:
            # Join via relationship
            query.join(Author.posts)

            # Join with explicit model
            query.join(Post, on="t0.author_id = t1.id")
        """
        import re

        # Validate join_type to prevent SQL injection
        normalized_join_type = join_type.upper()
        if normalized_join_type not in JOIN_TYPES:
            raise ValueError(
                f"Invalid join type: {join_type!r}. Must be one of: {sorted(JOIN_TYPES)}"
            )

        # Validate on clause format to prevent SQL injection
        # Only allow simple column references: alias.column = alias.column
        if on is not None:
            # Pattern: identifier.identifier = identifier.identifier
            # Allows optional quotes around column names
            pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*\."?[a-zA-Z_][a-zA-Z0-9_]*"?\s*=\s*[a-zA-Z_][a-zA-Z0-9_]*\."?[a-zA-Z_][a-zA-Z0-9_]*"?$'
            if not re.match(pattern, on.strip()):
                raise ValueError(
                    f"Invalid ON clause format: {on!r}. "
                    "ON clause must be in format 'alias.column = alias.column'. "
                    "For complex joins, use relationships instead."
                )

        # Import here to avoid circular imports
        try:
            from ..relationships.descriptor import RelationshipProxy
            from ..relationships.registry import RelationshipRegistry

            if isinstance(target, RelationshipProxy):
                # Joining via relationship - resolve target model
                target_model = RelationshipRegistry.resolve_model(target.config.target_model)
                if not target_model:
                    raise ValueError(f"Cannot resolve model: {target.config.target_model}")

                alias = f"t{self._alias_counter}"
                self._alias_counter += 1

                self._joins.append(
                    JoinConfig(
                        target_model=target_model,
                        join_type=normalized_join_type,
                        on_clause=on,
                        alias=alias,
                        via_relationship=target.name,
                    )
                )
            else:
                # Direct model join
                alias = f"t{self._alias_counter}"
                self._alias_counter += 1

                self._joins.append(
                    JoinConfig(
                        target_model=target,
                        join_type=normalized_join_type,
                        on_clause=on,
                        alias=alias,
                    )
                )
        except ImportError:
            # Relationships module not yet available
            alias = f"t{self._alias_counter}"
            self._alias_counter += 1

            self._joins.append(
                JoinConfig(
                    target_model=target,  # type: ignore
                    join_type=normalized_join_type,
                    on_clause=on,
                    alias=alias,
                )
            )

        return self

    def left_join(
        self,
        target: "Type[PydanticModel] | RelationshipProxy",
        *,
        on: str | None = None,
    ) -> "Query[T]":
        """
        Add a LEFT JOIN clause.

        Args:
            target: Model class or relationship proxy to join
            on: Custom ON clause

        Returns:
            Self for chaining
        """
        return self.join(target, on=on, join_type="LEFT")

    def right_join(
        self,
        target: "Type[PydanticModel] | RelationshipProxy",
        *,
        on: str | None = None,
    ) -> "Query[T]":
        """
        Add a RIGHT JOIN clause.

        Args:
            target: Model class or relationship proxy to join
            on: Custom ON clause

        Returns:
            Self for chaining
        """
        return self.join(target, on=on, join_type="RIGHT")

    # -------------------------------------------------------------------------
    # Ordering
    # -------------------------------------------------------------------------

    def order_by(self, *clauses: OrderByClause) -> "Query[T]":
        """
        Add ORDER BY clauses to the query.

        Args:
            clauses: OrderByClause objects

        Returns:
            Self for chaining

        Example:
            query.order_by(Product.field("created_at").desc())
            query.order_by(F.name.asc(), F.created_at.desc())
        """
        self._order_by.extend(clauses)
        return self

    # -------------------------------------------------------------------------
    # Pagination
    # -------------------------------------------------------------------------

    def limit(self, n: int) -> "Query[T]":
        """
        Set the maximum number of results.

        Args:
            n: Maximum number of results

        Returns:
            Self for chaining
        """
        self._limit = n
        return self

    def offset(self, n: int) -> "Query[T]":
        """
        Set the number of results to skip.

        Args:
            n: Number of results to skip

        Returns:
            Self for chaining
        """
        self._offset = n
        return self

    # -------------------------------------------------------------------------
    # Eager Loading
    # -------------------------------------------------------------------------

    def load(self, relationship_names: List[str]) -> "Query[T]":
        """
        Eager load relationships to prevent N+1 queries.

        Args:
            relationship_names: Names of relationships to load

        Returns:
            Self for chaining

        Example:
            query.load(["posts", "comments"])
        """
        self._eager_load.extend(relationship_names)
        return self

    # -------------------------------------------------------------------------
    # Aggregations
    # -------------------------------------------------------------------------

    def group_by(self, *fields: FieldProxy) -> "Query[T]":
        """
        Add GROUP BY clause.

        Args:
            fields: FieldProxy objects to group by

        Returns:
            Self for chaining

        Example:
            query.group_by(Product.field("category"))
        """
        self._group_by.extend(fields)
        return self

    def having(self, *expressions: "FilterExpression | CompositeExpression") -> "Query[T]":
        """
        Add HAVING clause for filtering grouped results.

        Args:
            expressions: FilterExpression or CompositeExpression objects

        Returns:
            Self for chaining

        Example:
            query.having(func.count() > 5)
        """
        self._having.extend(expressions)
        return self

    def select(self, *fields: "FieldProxy | AggregateExpression") -> "Query[T]":
        """
        Specify fields to select (for aggregation queries).

        Args:
            fields: Fields or aggregate expressions to select

        Returns:
            Self for chaining

        Example:
            query.select(Product.field("category"), func.avg(Product.field("price")))
        """
        self._select_fields.extend(fields)
        return self

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    async def _apply_eager_loading(
        self,
        results: List[T],
        db_pool: "PostgresPool",
        tenant_id: UUID | None,
    ) -> List[T]:
        """
        Apply eager loading to results if configured.

        This is an internal helper to avoid code duplication between
        execute() and first() methods.

        Args:
            results: Query results to load relationships for
            db_pool: Database connection pool
            tenant_id: Optional tenant ID for multi-tenant filtering

        Returns:
            Results with relationships populated
        """
        if not self._eager_load or not results:
            return results

        try:
            from ..relationships.loader import RelationshipLoader

            loader = RelationshipLoader(self.model_class)
            return await loader.load_relationships(results, self._eager_load, db_pool, tenant_id)
        except ImportError:
            # Relationships module not available - warn the developer
            warnings.warn(
                f"Relationships module unavailable, cannot eager load: {self._eager_load}. "
                "Install the relationships module or remove .load() call.",
                RuntimeWarning,
                stacklevel=4,  # Point to the caller's call site
            )
            return results

    # -------------------------------------------------------------------------
    # Execution
    # -------------------------------------------------------------------------

    async def execute(
        self,
        db_pool: "PostgresPool",
        tenant_id: UUID | None = None,
        connection=None,
    ) -> List[T]:
        """
        Execute the query and return results.

        Args:
            db_pool: Database connection pool
            tenant_id: Optional tenant ID for multi-tenant filtering
            connection: Optional database connection for external transaction
                       management. When provided, the operation uses this
                       connection instead of acquiring a new one from the pool.

        Returns:
            List of model instances

        Example:
            results = await query.execute(db_pool, tenant_id=org_id)

            # Within a transaction
            async with Transaction(db_pool) as txn:
                results = await query.execute(db_pool, tenant_id=org_id, connection=txn.connection)
        """
        from .executor import QueryExecutor

        executor = QueryExecutor(self.model_class, db_pool)
        results = await executor.execute(
            filters=self._filters,
            joins=self._joins,
            order_by=self._order_by,
            group_by=self._group_by,
            having=self._having,
            select_fields=self._select_fields,
            limit=self._limit,
            offset=self._offset,
            tenant_id=tenant_id,
            connection=connection,
        )

        # Apply eager loading if configured
        return await self._apply_eager_loading(results, db_pool, tenant_id)

    async def count(
        self,
        db_pool: "PostgresPool",
        tenant_id: UUID | None = None,
        connection=None,
    ) -> int:
        """
        Execute a COUNT query.

        Args:
            db_pool: Database connection pool
            tenant_id: Optional tenant ID for multi-tenant filtering
            connection: Optional database connection for external transaction
                       management. When provided, the operation uses this
                       connection instead of acquiring a new one from the pool.

        Returns:
            Count of matching records
        """
        from .executor import QueryExecutor

        executor = QueryExecutor(self.model_class, db_pool)
        return await executor.count(
            filters=self._filters,
            joins=self._joins,
            tenant_id=tenant_id,
            connection=connection,
        )

    async def first(
        self,
        db_pool: "PostgresPool",
        tenant_id: UUID | None = None,
        connection=None,
    ) -> T | None:
        """
        Execute query and return first result or None.

        Note: This method does NOT mutate the query's limit.

        Args:
            db_pool: Database connection pool
            tenant_id: Optional tenant ID for multi-tenant filtering
            connection: Optional database connection for external transaction
                       management. When provided, the operation uses this
                       connection instead of acquiring a new one from the pool.

        Returns:
            First matching model instance or None
        """
        from .executor import QueryExecutor

        # Execute directly with limit=1 without mutating self._limit
        executor = QueryExecutor(self.model_class, db_pool)
        results = await executor.execute(
            filters=self._filters,
            joins=self._joins,
            order_by=self._order_by,
            group_by=self._group_by,
            having=self._having,
            select_fields=self._select_fields,
            limit=1,  # Use limit=1 directly, don't mutate self
            offset=self._offset,
            tenant_id=tenant_id,
            connection=connection,
        )

        # Apply eager loading if configured
        results = await self._apply_eager_loading(results, db_pool, tenant_id)

        return results[0] if results else None

    async def exists(
        self,
        db_pool: "PostgresPool",
        tenant_id: UUID | None = None,
        connection=None,
    ) -> bool:
        """
        Check if any matching records exist.

        Args:
            db_pool: Database connection pool
            tenant_id: Optional tenant ID for multi-tenant filtering
            connection: Optional database connection for external transaction
                       management. When provided, the operation uses this
                       connection instead of acquiring a new one from the pool.

        Returns:
            True if any records match
        """
        count = await self.count(db_pool, tenant_id, connection=connection)
        return count > 0

    async def scalar(
        self,
        db_pool: "PostgresPool",
        tenant_id: UUID | None = None,
        connection=None,
    ) -> Any:
        """
        Execute query and return a single scalar value.

        Useful for aggregate queries that return a single value.

        Args:
            db_pool: Database connection pool
            tenant_id: Optional tenant ID for multi-tenant filtering
            connection: Optional database connection for external transaction
                       management. When provided, the operation uses this
                       connection instead of acquiring a new one from the pool.

        Returns:
            The scalar value from the first column of the first row
        """
        from .executor import QueryExecutor

        executor = QueryExecutor(self.model_class, db_pool)
        return await executor.scalar(
            filters=self._filters,
            joins=self._joins,
            group_by=self._group_by,
            having=self._having,
            select_fields=self._select_fields,
            tenant_id=tenant_id,
            connection=connection,
        )
