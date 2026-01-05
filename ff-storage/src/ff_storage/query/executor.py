"""Query executor with temporal and multi-tenant awareness.

This module executes queries built by the Query class, handling:
- SCD2 temporal filtering (valid_to IS NULL for current versions)
- Soft delete filtering (deleted_at IS NULL)
- Multi-tenant isolation (tenant_id = ?)
- JOIN temporal safety (filters applied to joined tables)

SECURITY NOTE:
--------------
This executor bypasses the standard validate_query() check used by
PostgresPool methods. This is intentional and safe because:

1. All SQL identifiers use ColumnRef.quote_identifier() which properly
   escapes and quotes table/column names to prevent SQL injection.

2. All values are passed as parameterized arguments (*params), never
   interpolated directly into SQL strings.

3. JOIN types are validated against a whitelist in JoinConfig.

4. No user input is directly incorporated into SQL strings - all filters
   and expressions are constructed programmatically.

If you modify this module to accept raw user SQL or unvalidated identifiers,
you MUST add validate_query() calls with appropriate context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Type, TypeVar
from uuid import UUID

from .expressions import CompositeExpression, FieldProxy, FilterExpression
from .ordering import OrderByClause
from .sql_utils import ColumnRef

if TYPE_CHECKING:
    from ..db.pool.postgres import PostgresPool
    from ..pydantic_support.base import PydanticModel
    from .aggregations import AggregateExpression
    from .builder import JoinConfig


T = TypeVar("T", bound="PydanticModel")


class QueryExecutor:
    """
    Executes queries with temporal and multi-tenant awareness.

    This class handles all SQL generation and execution, ensuring that:
    - SCD2 tables filter by valid_to IS NULL (current versions only)
    - Soft-deleted records are excluded by default
    - Multi-tenant queries filter by tenant_id
    - JOINs include temporal and tenant safety filters

    Attributes:
        model_class: The PydanticModel class being queried
        db_pool: Database connection pool
    """

    def __init__(self, model_class: Type[T], db_pool: "PostgresPool"):
        """
        Initialize the executor.

        Args:
            model_class: The PydanticModel class to query
            db_pool: Database connection pool for executing queries
        """
        self.model_class = model_class
        self.db_pool = db_pool

        # Extract model metadata
        self.table_name = self._get_table_name()
        self.schema = getattr(model_class, "__schema__", "public")
        self.temporal_strategy = getattr(model_class, "__temporal_strategy__", "none")
        self.soft_delete = getattr(model_class, "__soft_delete__", True)
        self.multi_tenant = getattr(model_class, "__multi_tenant__", True)
        self.tenant_field = getattr(model_class, "__tenant_field__", "tenant_id")

    def _get_table_name(self) -> str:
        """Get the table name from the model class."""
        if hasattr(self.model_class, "__table_name__") and self.model_class.__table_name__:
            return self.model_class.__table_name__
        # Default: lowercase class name + 's'
        return self.model_class.__name__.lower() + "s"

    def _quote_identifier(self, name: str) -> str:
        """Quote a SQL identifier to prevent injection and handle reserved words."""
        return ColumnRef.quote_identifier(name)

    async def execute(
        self,
        filters: List[FilterExpression | CompositeExpression],
        joins: List["JoinConfig"],
        order_by: List[OrderByClause],
        group_by: List[FieldProxy],
        having: List[FilterExpression | CompositeExpression],
        select_fields: List["FieldProxy | AggregateExpression"],
        limit: int | None,
        offset: int | None,
        tenant_id: UUID | None,
        connection=None,
        for_update: bool = False,
        for_update_nowait: bool = False,
        for_update_skip_locked: bool = False,
    ) -> List[T]:
        """
        Execute the query and return model instances.

        Args:
            filters: List of filter expressions
            joins: List of join configurations
            order_by: List of order by clauses
            group_by: List of fields to group by
            having: List of having expressions
            select_fields: Fields to select (for aggregations)
            limit: Maximum results
            offset: Results to skip
            tenant_id: Tenant ID for multi-tenant filtering
            connection: Optional database connection for external transaction
                       management. When provided, the operation uses this
                       connection instead of acquiring a new one from the pool.
            for_update: Whether to add FOR UPDATE clause
            for_update_nowait: Whether to add NOWAIT to FOR UPDATE
            for_update_skip_locked: Whether to add SKIP LOCKED to FOR UPDATE

        Returns:
            List of model instances
        """
        sql, params = self._build_select_query(
            filters=filters,
            joins=joins,
            order_by=order_by,
            group_by=group_by,
            having=having,
            select_fields=select_fields,
            limit=limit,
            offset=offset,
            tenant_id=tenant_id,
            for_update=for_update,
            for_update_nowait=for_update_nowait,
            for_update_skip_locked=for_update_skip_locked,
        )

        if connection is not None:
            rows = await connection.fetch(sql, *params)
        else:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(sql, *params)

        # Convert rows to model instances
        return [self._row_to_model(dict(row)) for row in rows]

    async def count(
        self,
        filters: List[FilterExpression | CompositeExpression],
        joins: List["JoinConfig"],
        tenant_id: UUID | None,
        connection=None,
    ) -> int:
        """
        Execute a COUNT query.

        Args:
            filters: List of filter expressions
            joins: List of join configurations
            tenant_id: Tenant ID for multi-tenant filtering
            connection: Optional database connection for external transaction
                       management. When provided, the operation uses this
                       connection instead of acquiring a new one from the pool.

        Returns:
            Count of matching records
        """
        sql, params = self._build_count_query(filters, joins, tenant_id)

        if connection is not None:
            row = await connection.fetchrow(sql, *params)
        else:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(sql, *params)

        return row["count"] if row else 0

    async def scalar(
        self,
        filters: List[FilterExpression | CompositeExpression],
        joins: List["JoinConfig"],
        group_by: List[FieldProxy],
        having: List[FilterExpression | CompositeExpression],
        select_fields: List["FieldProxy | AggregateExpression"],
        tenant_id: UUID | None,
        connection=None,
    ) -> Any:
        """
        Execute query and return a single scalar value.

        Args:
            filters: List of filter expressions
            joins: List of join configurations
            group_by: List of fields to group by
            having: List of having expressions
            select_fields: Fields to select
            tenant_id: Tenant ID for multi-tenant filtering
            connection: Optional database connection for external transaction
                       management. When provided, the operation uses this
                       connection instead of acquiring a new one from the pool.

        Returns:
            The first column of the first row
        """
        sql, params = self._build_select_query(
            filters=filters,
            joins=joins,
            order_by=[],
            group_by=group_by,
            having=having,
            select_fields=select_fields,
            limit=1,
            offset=None,
            tenant_id=tenant_id,
        )

        if connection is not None:
            row = await connection.fetchrow(sql, *params)
        else:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(sql, *params)

        if not row:
            return None

        # Return first column value
        return row[0] if row else None

    def _build_select_query(
        self,
        filters: List[FilterExpression | CompositeExpression],
        joins: List["JoinConfig"],
        order_by: List[OrderByClause],
        group_by: List[FieldProxy],
        having: List[FilterExpression | CompositeExpression],
        select_fields: List["FieldProxy | AggregateExpression"],
        limit: int | None,
        offset: int | None,
        tenant_id: UUID | None,
        for_update: bool = False,
        for_update_nowait: bool = False,
        for_update_skip_locked: bool = False,
    ) -> tuple[str, List[Any]]:
        """Build the SELECT query with all components."""
        params: List[Any] = []
        param_index = 1

        # Determine SELECT clause
        if select_fields:
            select_parts = []
            for field in select_fields:
                if isinstance(field, FieldProxy):
                    select_parts.append(ColumnRef.format(field.field_name, "t0"))
                else:
                    # AggregateExpression
                    select_parts.append(field.to_sql("t0"))
            select_clause = ", ".join(select_parts)
        else:
            select_clause = "t0.*"

        # FROM clause
        full_table = (
            f"{self._quote_identifier(self.schema)}.{self._quote_identifier(self.table_name)}"
        )
        sql = f"SELECT {select_clause} FROM {full_table} t0"

        # JOIN clauses
        for join in joins:
            join_sql, join_params, param_index = self._build_join(join, param_index, tenant_id)
            sql += join_sql
            params.extend(join_params)

        # WHERE clause
        where_parts, where_params, param_index = self._build_where_clause(
            filters, param_index, tenant_id
        )
        params.extend(where_params)

        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)

        # GROUP BY clause
        if group_by:
            group_parts = [ColumnRef.format(f.field_name, "t0") for f in group_by]
            sql += " GROUP BY " + ", ".join(group_parts)

        # HAVING clause
        if having:
            having_parts = []
            for expr in having:
                # Pass tenant_id for subquery multi-tenant filtering
                expr_sql, expr_value, param_index = expr.to_sql(param_index, tenant_id=tenant_id)
                having_parts.append(expr_sql)
                if expr_value is not None:
                    if isinstance(expr_value, (list, tuple)):
                        params.extend(expr_value)
                    else:
                        params.append(expr_value)
            sql += " HAVING " + " AND ".join(having_parts)

        # ORDER BY clause
        if order_by:
            order_parts = [clause.to_sql() for clause in order_by]
            sql += " ORDER BY " + ", ".join(order_parts)

        # LIMIT and OFFSET - validate before interpolation to prevent injection
        if limit is not None:
            if not isinstance(limit, int) or limit < 0:
                raise ValueError(f"limit must be a non-negative integer, got {limit!r}")
            sql += f" LIMIT {limit}"
        if offset is not None:
            if not isinstance(offset, int) or offset < 0:
                raise ValueError(f"offset must be a non-negative integer, got {offset!r}")
            sql += f" OFFSET {offset}"

        # FOR UPDATE clause - for row locking within transactions
        if for_update:
            sql += " FOR UPDATE"
            if for_update_nowait:
                sql += " NOWAIT"
            elif for_update_skip_locked:
                sql += " SKIP LOCKED"

        return sql, params

    def _build_count_query(
        self,
        filters: List[FilterExpression | CompositeExpression],
        joins: List["JoinConfig"],
        tenant_id: UUID | None,
    ) -> tuple[str, List[Any]]:
        """Build a COUNT query."""
        params: List[Any] = []
        param_index = 1

        full_table = (
            f"{self._quote_identifier(self.schema)}.{self._quote_identifier(self.table_name)}"
        )
        sql = f"SELECT COUNT(*) as count FROM {full_table} t0"

        # JOIN clauses
        for join in joins:
            join_sql, join_params, param_index = self._build_join(join, param_index, tenant_id)
            sql += join_sql
            params.extend(join_params)

        # WHERE clause
        where_parts, where_params, param_index = self._build_where_clause(
            filters, param_index, tenant_id
        )
        params.extend(where_params)

        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)

        return sql, params

    def _build_where_clause(
        self,
        filters: List[FilterExpression | CompositeExpression],
        param_index: int,
        tenant_id: UUID | None,
    ) -> tuple[List[str], List[Any], int]:
        """
        Build WHERE clause with temporal and tenant filters.

        Returns:
            Tuple of (where_parts, params, next_param_index)
        """
        where_parts: List[str] = []
        params: List[Any] = []

        # SCD2 temporal filtering: only current versions
        if self.temporal_strategy == "scd2":
            where_parts.append(f"{ColumnRef.format('valid_to', 't0')} IS NULL")

        # Soft delete filtering
        if self.soft_delete:
            where_parts.append(f"{ColumnRef.format('deleted_at', 't0')} IS NULL")

        # Multi-tenant filtering
        if self.multi_tenant:
            if tenant_id is None:
                # Import here to avoid circular imports
                from ..temporal.exceptions import TenantNotConfigured

                raise TenantNotConfigured(
                    self.model_class.__name__,
                    message=(
                        f"Multi-tenant model '{self.model_class.__name__}' requires tenant_id parameter. "
                        "Pass tenant_id to Query.execute() for tenant-scoped queries, "
                        "or set __multi_tenant__ = False on the model."
                    ),
                )
            where_parts.append(f"{ColumnRef.format(self.tenant_field, 't0')} = ${param_index}")
            params.append(tenant_id)
            param_index += 1

        # User-provided filters
        for expr in filters:
            # Pass tenant_id for subquery multi-tenant filtering
            expr_sql, expr_value, param_index = expr.to_sql(param_index, tenant_id=tenant_id)
            where_parts.append(expr_sql)
            if expr_value is not None:
                if isinstance(expr_value, (list, tuple)):
                    params.extend(expr_value)
                else:
                    params.append(expr_value)

        return where_parts, params, param_index

    # Valid join types (defense-in-depth validation)
    _VALID_JOIN_TYPES = {"INNER", "LEFT", "RIGHT", "FULL", "CROSS"}

    def _build_join(
        self,
        join: "JoinConfig",
        param_index: int,
        tenant_id: UUID | None,
    ) -> tuple[str, List[Any], int]:
        """
        Build a JOIN clause with temporal and tenant safety.

        CRITICAL: For SCD2 joined tables, the ON clause must include:
        - {alias}.valid_to IS NULL (current version only)
        - {alias}.deleted_at IS NULL (not soft-deleted)
        - {alias}.tenant_id = t0.tenant_id (tenant isolation)

        Args:
            join: Join configuration
            param_index: Current parameter index
            tenant_id: Tenant ID for filtering

        Returns:
            Tuple of (join_sql, params, next_param_index)

        Raises:
            ValueError: If join_type is invalid
        """
        # Defense-in-depth: validate join_type even though builder.py should have validated
        if join.join_type not in self._VALID_JOIN_TYPES:
            raise ValueError(
                f"Invalid join type: {join.join_type!r}. "
                f"Must be one of: {sorted(self._VALID_JOIN_TYPES)}"
            )

        params: List[Any] = []
        target = join.target_model
        alias = join.alias

        # Get target table metadata
        target_table = self._get_model_table_name(target)
        target_schema = getattr(target, "__schema__", "public")
        target_temporal = getattr(target, "__temporal_strategy__", "none")
        target_soft_delete = getattr(target, "__soft_delete__", True)
        target_multi_tenant = getattr(target, "__multi_tenant__", True)
        target_tenant_field = getattr(target, "__tenant_field__", "tenant_id")

        full_target = (
            f"{self._quote_identifier(target_schema)}.{self._quote_identifier(target_table)}"
        )

        # Build ON clause parts
        on_parts: List[str] = []

        # User-provided ON clause or auto-generate from relationship
        if join.on_clause:
            on_parts.append(join.on_clause)
        elif join.via_relationship:
            # Auto-generate from relationship configuration
            try:
                from ..relationships.registry import RelationshipRegistry

                config = RelationshipRegistry.get_relationship(
                    self.model_class.__name__, join.via_relationship
                )
                if config:
                    if config.is_collection:
                        # One-to-many: target.fk = t0.id
                        fk_col = config.get_foreign_key_column()
                        on_parts.append(
                            f"{ColumnRef.format(fk_col, alias)} = {ColumnRef.format('id', 't0')}"
                        )
                    else:
                        # Many-to-one: t0.fk = target.id
                        fk_col = config.get_foreign_key_column()
                        on_parts.append(
                            f"{ColumnRef.format(fk_col, 't0')} = {ColumnRef.format('id', alias)}"
                        )
            except ImportError:
                # Relationships module not available
                pass

        # CRITICAL: Temporal safety for joined table
        if target_temporal == "scd2":
            on_parts.append(f"{ColumnRef.format('valid_to', alias)} IS NULL")

        # CRITICAL: Soft delete safety for joined table
        if target_soft_delete:
            on_parts.append(f"{ColumnRef.format('deleted_at', alias)} IS NULL")

        # CRITICAL: Multi-tenant safety - joined table must be in same tenant
        if target_multi_tenant and self.multi_tenant and tenant_id:
            on_parts.append(
                f"{ColumnRef.format(target_tenant_field, alias)} = {ColumnRef.format(self.tenant_field, 't0')}"
            )

        on_clause = " AND ".join(on_parts) if on_parts else "TRUE"

        sql = f" {join.join_type} JOIN {full_target} {alias} ON {on_clause}"

        return sql, params, param_index

    def _get_model_table_name(self, model_class: type) -> str:
        """Get table name from a model class."""
        if hasattr(model_class, "__table_name__") and model_class.__table_name__:
            return model_class.__table_name__
        return model_class.__name__.lower() + "s"

    def _row_to_model(self, row_dict: Dict[str, Any]) -> T:
        """Convert a database row to a model instance."""
        if hasattr(self.model_class, "model_validate"):
            # Pydantic v2
            return self.model_class.model_validate(row_dict)
        elif hasattr(self.model_class, "from_orm"):
            # Pydantic v1
            return self.model_class.from_orm(row_dict)
        else:
            # Dataclass or other
            return self.model_class(**row_dict)
