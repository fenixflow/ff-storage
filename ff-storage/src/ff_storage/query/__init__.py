"""Query builder for ff-storage models.

This module provides a fluent, type-safe query API for building database queries
with automatic temporal and multi-tenant awareness.

Security Model
--------------

This query builder is designed with SQL injection prevention as a core principle.
All user-provided values are parameterized and never interpolated into SQL strings.

**Safe for User Input:**
    - Filter values (e.g., `Query(Product).filter(F.name == user_input)`)
    - LIMIT and OFFSET values (validated as non-negative integers)
    - Field values in expressions

**NOT Safe for User Input (Developer-Controlled Only):**
    - Field names (use `F.field_name`, not `F[user_input]`)
    - Table/model names
    - JOIN on_clause strings (validated format, but use relationships instead)
    - ORDER BY field names

**Automatic Safety Guarantees:**
    - Temporal filtering: SCD2 tables automatically filter `valid_to IS NULL`
    - Soft delete filtering: Automatically filters `deleted_at IS NULL`
    - Multi-tenant isolation: Queries include `tenant_id` filtering when provided
    - JOIN safety: Joined tables include temporal and tenant filters automatically

**Validation:**
    - JOIN types are restricted to: INNER, LEFT, RIGHT, FULL, CROSS
    - ORDER BY directions are restricted to: ASC, DESC
    - NULLS handling is restricted to: FIRST, LAST
    - ON clauses must match format: `alias.column = alias.column`

Example usage:
    from ff_storage.query import Query, F

    # Simple filtering
    results = await (
        Query(Product)
        .filter(Product.field("price") > 100)
        .filter(Product.field("status") == "active")
        .order_by(Product.field("created_at").desc())
        .limit(10)
        .execute(db_pool, tenant_id=tenant)
    )

    # Using F shorthand
    results = await (
        Query(Product)
        .filter(F.price > 100, F.status == "active")
        .execute(db_pool, tenant_id=tenant)
    )

    # Aggregations
    stats = await (
        Query(Product)
        .group_by(Product.field("category"))
        .select(Product.field("category"), func.avg(Product.field("price")))
        .execute(db_pool, tenant_id=tenant)
    )
"""

from .aggregations import AggregateExpression, GroupByClause
from .builder import Query
from .expressions import AND, OR, CompositeExpression, F, FieldProxy, FilterExpression
from .functions import func
from .ordering import OrderByClause
from .sql_utils import ColumnRef, ParameterTracker
from .subquery import Subquery

__all__ = [
    # Expressions
    "FilterExpression",
    "FieldProxy",
    "F",
    # Composite Expressions
    "CompositeExpression",
    "AND",
    "OR",
    # Ordering
    "OrderByClause",
    # Builder
    "Query",
    # Subqueries
    "Subquery",
    # Aggregations
    "AggregateExpression",
    "GroupByClause",
    "func",
    # SQL Utilities
    "ColumnRef",
    "ParameterTracker",
]
