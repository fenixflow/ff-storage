"""Fluent query builder for ff-storage models.

This module provides the Query class for building database queries with a fluent API.
"""

from __future__ import annotations

import copy
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
    from .subquery import Subquery


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

    Immutable Design:
        Query methods return NEW Query instances rather than mutating self.
        This allows safe query branching without explicit copying:

        # Safe - each method returns a new independent query
        base = Query(Product).filter(Product.active == True)
        cheap = base.filter(Product.price < 100)  # New query with both filters
        expensive = base.filter(Product.price > 1000)  # Different new query

        # base still only has the .active filter

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
        # Row locking
        self._for_update: bool = False
        self._for_update_nowait: bool = False
        self._for_update_skip_locked: bool = False

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
        Create an independent deep copy of this query for safe branching.

        Uses deep copy for nested structures (filters, joins, order_by, etc.)
        to ensure complete independence between the original and copied queries.

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
        # Deep copy nested structures to ensure complete independence
        new_query._filters = copy.deepcopy(self._filters)
        new_query._joins = copy.deepcopy(self._joins)
        new_query._order_by = copy.deepcopy(self._order_by)
        new_query._group_by = copy.deepcopy(self._group_by)
        new_query._having = copy.deepcopy(self._having)
        new_query._select_fields = copy.deepcopy(self._select_fields)
        # Primitive values don't need deep copy
        new_query._limit = self._limit
        new_query._offset = self._offset
        # List of strings - shallow copy is fine
        new_query._eager_load = self._eager_load.copy()
        new_query._alias_counter = self._alias_counter
        # Row locking
        new_query._for_update = self._for_update
        new_query._for_update_nowait = self._for_update_nowait
        new_query._for_update_skip_locked = self._for_update_skip_locked
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
            New Query instance with filters added

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
        new_query = self.copy()
        new_query._filters.extend(expressions)
        return new_query

    def filter_by(self, **kwargs: Any) -> "Query[T]":
        """
        Add simple equality filters using keyword arguments.

        Args:
            **kwargs: Field=value pairs for equality filters

        Returns:
            New Query instance with filters added

        Example:
            query.filter_by(status="active", category="electronics")
        """
        new_query = self.copy()
        for field_name, value in kwargs.items():
            if value is None:
                new_query._filters.append(FilterExpression(field_name, "IS NULL", None))
            else:
                new_query._filters.append(FilterExpression(field_name, "=", value))
        return new_query

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
            New Query instance with join added

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

        new_query = self.copy()

        # Import here to avoid circular imports
        try:
            from ..relationships.descriptor import RelationshipProxy
            from ..relationships.registry import RelationshipRegistry

            if isinstance(target, RelationshipProxy):
                # Joining via relationship - resolve target model
                target_model = RelationshipRegistry.resolve_model(target.config.target_model)
                if not target_model:
                    raise ValueError(f"Cannot resolve model: {target.config.target_model}")

                alias = f"t{new_query._alias_counter}"
                new_query._alias_counter += 1

                new_query._joins.append(
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
                alias = f"t{new_query._alias_counter}"
                new_query._alias_counter += 1

                new_query._joins.append(
                    JoinConfig(
                        target_model=target,
                        join_type=normalized_join_type,
                        on_clause=on,
                        alias=alias,
                    )
                )
        except ImportError:
            # Relationships module not yet available
            alias = f"t{new_query._alias_counter}"
            new_query._alias_counter += 1

            new_query._joins.append(
                JoinConfig(
                    target_model=target,  # type: ignore
                    join_type=normalized_join_type,
                    on_clause=on,
                    alias=alias,
                )
            )

        return new_query

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
            New Query instance with join added
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
            New Query instance with join added
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
            New Query instance with ordering added

        Example:
            query.order_by(Product.field("created_at").desc())
            query.order_by(F.name.asc(), F.created_at.desc())
        """
        new_query = self.copy()
        new_query._order_by.extend(clauses)
        return new_query

    # -------------------------------------------------------------------------
    # Pagination
    # -------------------------------------------------------------------------

    def limit(self, n: int) -> "Query[T]":
        """
        Set the maximum number of results.

        Args:
            n: Maximum number of results

        Returns:
            New Query instance with limit set
        """
        new_query = self.copy()
        new_query._limit = n
        return new_query

    def offset(self, n: int) -> "Query[T]":
        """
        Set the number of results to skip.

        Args:
            n: Number of results to skip

        Returns:
            New Query instance with offset set
        """
        new_query = self.copy()
        new_query._offset = n
        return new_query

    # -------------------------------------------------------------------------
    # Eager Loading
    # -------------------------------------------------------------------------

    def load(self, relationship_names: List[str]) -> "Query[T]":
        """
        Eager load relationships to prevent N+1 queries.

        Supports nested loading with dot notation (e.g., "posts.comments").

        Args:
            relationship_names: Names of relationships to load

        Returns:
            New Query instance with eager loading configured

        Example:
            query.load(["posts", "comments"])
            query.load(["posts.comments"])  # Nested loading
        """
        new_query = self.copy()
        new_query._eager_load.extend(relationship_names)
        return new_query

    # -------------------------------------------------------------------------
    # Row Locking
    # -------------------------------------------------------------------------

    def for_update(
        self,
        *,
        nowait: bool = False,
        skip_locked: bool = False,
    ) -> "Query[T]":
        """
        Add SELECT ... FOR UPDATE to lock selected rows.

        Use this within a transaction to lock rows for update, preventing
        concurrent modifications until the transaction completes.

        Args:
            nowait: If True, fail immediately if rows are locked (NOWAIT)
            skip_locked: If True, skip locked rows instead of waiting (SKIP LOCKED)

        Returns:
            New Query instance with row locking configured

        Note:
            - nowait and skip_locked are mutually exclusive
            - This only works when executed within a transaction
            - Without a transaction, the lock is released immediately

        Example:
            # Basic locking - waits for locks
            async with Transaction(db_pool) as txn:
                product = await (
                    Query(Product)
                    .filter(Product.field("id") == product_id)
                    .for_update()
                    .first(db_pool, tenant_id, connection=txn.connection)
                )
                # product row is locked until transaction commits

            # NOWAIT - fail immediately if locked
            try:
                product = await (
                    Query(Product)
                    .for_update(nowait=True)
                    .first(db_pool, tenant_id, connection=txn.connection)
                )
            except Exception:
                # Handle "could not obtain lock" error
                pass

            # SKIP LOCKED - skip locked rows (useful for job queues)
            jobs = await (
                Query(Job)
                .filter(Job.field("status") == "pending")
                .for_update(skip_locked=True)
                .limit(10)
                .execute(db_pool, tenant_id, connection=txn.connection)
            )
        """
        if nowait and skip_locked:
            raise ValueError("Cannot use both nowait and skip_locked")

        new_query = self.copy()
        new_query._for_update = True
        new_query._for_update_nowait = nowait
        new_query._for_update_skip_locked = skip_locked
        return new_query

    # -------------------------------------------------------------------------
    # Subqueries
    # -------------------------------------------------------------------------

    def subquery(
        self,
        alias: str = "sq",
        select_column: str | None = None,
    ) -> "Subquery[T]":
        """
        Return this query as a subquery for use in IN clauses.

        Args:
            alias: Alias for the subquery (default: "sq")
            select_column: Column to select for the subquery. If None,
                          defaults to "id" for IN clause usage.

        Returns:
            Subquery instance that can be used with .in_() or .not_in()

        Example:
            # Find products in categories with active sales
            active_category_ids = (
                Query(Sale)
                .filter(Sale.field("completed") == True)
                .subquery(select_column="category_id")
            )

            products = await (
                Query(Product)
                .filter(Product.field("category_id").in_(active_category_ids))
                .execute(db_pool, tenant_id)
            )

            # Using F shorthand
            banned_users = Query(BannedUser).subquery()
            posts = await (
                Query(Post)
                .filter(F.author_id.not_in(banned_users))
                .execute(db_pool, tenant_id)
            )
        """
        from .subquery import Subquery

        return Subquery(self, alias=alias, select_column=select_column)

    # -------------------------------------------------------------------------
    # Aggregations
    # -------------------------------------------------------------------------

    def group_by(self, *fields: FieldProxy) -> "Query[T]":
        """
        Add GROUP BY clause.

        Args:
            fields: FieldProxy objects to group by

        Returns:
            New Query instance with grouping added

        Example:
            query.group_by(Product.field("category"))
        """
        new_query = self.copy()
        new_query._group_by.extend(fields)
        return new_query

    def having(self, *expressions: "FilterExpression | CompositeExpression") -> "Query[T]":
        """
        Add HAVING clause for filtering grouped results.

        Args:
            expressions: FilterExpression or CompositeExpression objects

        Returns:
            New Query instance with having clause added

        Example:
            query.having(func.count() > 5)
        """
        new_query = self.copy()
        new_query._having.extend(expressions)
        return new_query

    def select(self, *fields: "FieldProxy | AggregateExpression") -> "Query[T]":
        """
        Specify fields to select (for aggregation queries).

        Args:
            fields: Fields or aggregate expressions to select

        Returns:
            New Query instance with selection added

        Example:
            query.select(Product.field("category"), func.avg(Product.field("price")))
        """
        new_query = self.copy()
        new_query._select_fields.extend(fields)
        return new_query

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    async def _apply_eager_loading(
        self,
        results: List[T],
        db_pool: "PostgresPool",
        tenant_id: UUID | None,
        connection: Any = None,
    ) -> List[T]:
        """
        Apply eager loading to results if configured.

        This is an internal helper to avoid code duplication between
        execute() and first() methods.

        Args:
            results: Query results to load relationships for
            db_pool: Database connection pool
            tenant_id: Optional tenant ID for multi-tenant filtering
            connection: Optional database connection for transaction context

        Returns:
            Results with relationships populated
        """
        if not self._eager_load or not results:
            return results

        try:
            from ..relationships.loader import RelationshipLoader

            loader = RelationshipLoader(self.model_class)
            return await loader.load_relationships(
                results, self._eager_load, db_pool, tenant_id, connection=connection
            )
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
        # Validate relationships on first query (emits warnings if misconfigured)
        from ..relationships.registry import RelationshipRegistry

        RelationshipRegistry.ensure_validated()

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
            for_update=self._for_update,
            for_update_nowait=self._for_update_nowait,
            for_update_skip_locked=self._for_update_skip_locked,
        )

        # Apply eager loading if configured (forward connection for transaction context)
        return await self._apply_eager_loading(results, db_pool, tenant_id, connection=connection)

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

        # Apply eager loading if configured (forward connection for transaction context)
        results = await self._apply_eager_loading(
            results, db_pool, tenant_id, connection=connection
        )

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
