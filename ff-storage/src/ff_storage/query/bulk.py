"""Bulk operations for efficient batch database operations.

This module provides functions for inserting and updating many records
efficiently, minimizing database round-trips.

Example:
    from ff_storage.query.bulk import bulk_insert, bulk_update

    # Insert many records efficiently
    products = [Product(name=f"Product {i}", price=i*10) for i in range(1000)]
    count = await bulk_insert(Product, products, db_pool, tenant_id)

    # Update many records efficiently
    updates = [
        {"id": uuid1, "price": 100},
        {"id": uuid2, "price": 200},
    ]
    count = await bulk_update(Product, updates, db_pool, tenant_id)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Type, TypeVar
from uuid import UUID, uuid4

from .sql_utils import ColumnRef

if TYPE_CHECKING:
    from ..db.pool.postgres import PostgresPool
    from ..pydantic_support.base import PydanticModel

T = TypeVar("T", bound="PydanticModel")


async def bulk_insert(
    model_class: Type[T],
    records: List[T],
    db_pool: "PostgresPool",
    tenant_id: UUID | None = None,
    batch_size: int = 1000,
    connection: Any = None,
) -> int:
    """
    Insert multiple records efficiently using multi-row INSERT.

    Uses batched INSERT with multiple VALUES rows to minimize round-trips.
    Automatically handles temporal fields (created_at, updated_at) and
    ensures proper ID generation.

    Args:
        model_class: The PydanticModel class for the records
        records: List of model instances to insert
        db_pool: Database connection pool
        tenant_id: Tenant ID for multi-tenant models
        batch_size: Maximum records per INSERT statement (default: 1000)
        connection: Optional database connection for transaction context

    Returns:
        Number of records inserted

    Raises:
        ValueError: If records list is empty or contains wrong model type

    Example:
        products = [
            Product(name="Widget", price=10),
            Product(name="Gadget", price=20),
        ]
        count = await bulk_insert(Product, products, db_pool, tenant_id)
        print(f"Inserted {count} products")
    """
    if not records:
        return 0

    # Validate all records are the correct model type
    for record in records:
        if not isinstance(record, model_class):
            raise ValueError(
                f"All records must be instances of {model_class.__name__}, "
                f"got {type(record).__name__}"
            )

    # Get model metadata
    table_name = model_class.__table_name__
    schema = getattr(model_class, "__schema__", "public")
    multi_tenant = getattr(model_class, "__multi_tenant__", True)
    temporal_strategy = getattr(model_class, "__temporal_strategy__", "none")

    # Get columns from the first record's fields (excluding relationship fields)
    first_record = records[0]
    columns: List[str] = []
    for field_name in first_record.model_fields:
        # Skip relationship fields (they don't exist in the database)
        if hasattr(model_class, "_relationships") and field_name in model_class._relationships:
            continue
        columns.append(field_name)

    # Add temporal columns if using SCD2
    if temporal_strategy == "scd2":
        if "valid_from" not in columns:
            columns.append("valid_from")
        if "valid_to" not in columns:
            columns.append("valid_to")

    full_table = f'"{schema}"."{table_name}"'
    quoted_columns = ", ".join(ColumnRef.quote_identifier(c) for c in columns)

    total_inserted = 0
    now = datetime.now(timezone.utc)

    async def execute_with_conn(conn: Any) -> int:
        nonlocal total_inserted
        for batch_start in range(0, len(records), batch_size):
            batch = records[batch_start : batch_start + batch_size]

            # Build VALUES clause
            values_parts: List[str] = []
            params: List[Any] = []
            param_idx = 1

            for record in batch:
                placeholders: List[str] = []
                for col in columns:
                    value = _get_record_value(
                        record, col, tenant_id, multi_tenant, temporal_strategy, now
                    )
                    placeholders.append(f"${param_idx}")
                    params.append(value)
                    param_idx += 1
                values_parts.append(f"({', '.join(placeholders)})")

            sql = f"INSERT INTO {full_table} ({quoted_columns}) VALUES {', '.join(values_parts)}"

            await conn.execute(sql, *params)
            total_inserted += len(batch)

        return total_inserted

    if connection:
        return await execute_with_conn(connection)
    else:
        async with db_pool.acquire() as conn:
            return await execute_with_conn(conn)


async def bulk_update(
    model_class: Type[T],
    updates: List[Dict[str, Any]],
    db_pool: "PostgresPool",
    tenant_id: UUID | None = None,
    connection: Any = None,
) -> int:
    """
    Update multiple records efficiently using UPDATE ... FROM VALUES.

    Uses PostgreSQL's UPDATE ... FROM (VALUES ...) pattern to update
    many records in a single query. Each update dict must contain an "id" key.

    Args:
        model_class: The PydanticModel class for the records
        updates: List of dicts, each with "id" and fields to update
        db_pool: Database connection pool
        tenant_id: Tenant ID for multi-tenant filtering
        connection: Optional database connection for transaction context

    Returns:
        Number of records updated

    Raises:
        ValueError: If updates list is empty or dicts missing "id"

    Example:
        updates = [
            {"id": product1_id, "price": 100, "status": "sale"},
            {"id": product2_id, "price": 200},
        ]
        count = await bulk_update(Product, updates, db_pool, tenant_id)
        print(f"Updated {count} products")

    Note:
        For SCD2 temporal models, this updates only current records
        (valid_to IS NULL). Consider using the repository for proper
        temporal versioning.
    """
    if not updates:
        return 0

    # Validate all updates have id
    for i, update in enumerate(updates):
        if "id" not in update:
            raise ValueError(f"Update at index {i} missing required 'id' key")

    # Get model metadata
    table_name = model_class.__table_name__
    schema = getattr(model_class, "__schema__", "public")
    multi_tenant = getattr(model_class, "__multi_tenant__", True)
    temporal_strategy = getattr(model_class, "__temporal_strategy__", "none")
    soft_delete = getattr(model_class, "__soft_delete__", True)

    # Collect all unique columns being updated (excluding id)
    all_columns: set = set()
    for update in updates:
        all_columns.update(k for k in update.keys() if k != "id")

    if not all_columns:
        return 0  # Nothing to update

    # Always update updated_at if the model has it
    all_columns.add("updated_at")
    column_list = sorted(all_columns)  # Consistent ordering

    full_table = f'"{schema}"."{table_name}"'
    now = datetime.now(timezone.utc)

    # Build the UPDATE ... FROM (VALUES ...) query
    # Format: UPDATE table SET col1 = v.col1, ... FROM (VALUES (...), ...) AS v(id, col1, ...)
    # WHERE table.id = v.id

    # Build VALUES clause
    values_parts: List[str] = []
    params: List[Any] = []
    param_idx = 1

    for update in updates:
        row_values: List[str] = []

        # Add id first
        row_values.append(f"${param_idx}::uuid")
        params.append(update["id"])
        param_idx += 1

        # Add each column
        for col in column_list:
            if col == "updated_at":
                value = now
            else:
                value = update.get(col)

            row_values.append(f"${param_idx}")
            params.append(value)
            param_idx += 1

        values_parts.append(f"({', '.join(row_values)})")

    # Build column list for VALUES alias
    values_columns = ["id"] + column_list
    values_alias = ", ".join(ColumnRef.quote_identifier(c) for c in values_columns)

    # Build SET clause
    set_parts = [
        f"{ColumnRef.quote_identifier(col)} = v.{ColumnRef.quote_identifier(col)}"
        for col in column_list
    ]
    set_clause = ", ".join(set_parts)

    # Build WHERE clause
    where_parts = [f"{full_table}.id = v.id"]

    if temporal_strategy == "scd2":
        where_parts.append(f"{full_table}.valid_to IS NULL")

    if soft_delete:
        where_parts.append(f"{full_table}.deleted_at IS NULL")

    if multi_tenant and tenant_id:
        where_parts.append(f"{full_table}.tenant_id = ${param_idx}")
        params.append(tenant_id)
        param_idx += 1

    where_clause = " AND ".join(where_parts)

    sql = (
        f"UPDATE {full_table} "
        f"SET {set_clause} "
        f"FROM (VALUES {', '.join(values_parts)}) AS v({values_alias}) "
        f"WHERE {where_clause}"
    )

    if connection:
        result = await connection.execute(sql, *params)
    else:
        async with db_pool.acquire() as conn:
            result = await conn.execute(sql, *params)

    # Parse result to get count (format: "UPDATE N")
    if isinstance(result, str) and result.startswith("UPDATE"):
        return int(result.split()[-1])
    return 0


async def bulk_delete(
    model_class: Type[T],
    ids: List[UUID],
    db_pool: "PostgresPool",
    tenant_id: UUID | None = None,
    connection: Any = None,
    hard_delete: bool = False,
) -> int:
    """
    Delete multiple records efficiently.

    By default, performs soft delete (sets deleted_at). Use hard_delete=True
    for permanent deletion.

    Args:
        model_class: The PydanticModel class for the records
        ids: List of record IDs to delete
        db_pool: Database connection pool
        tenant_id: Tenant ID for multi-tenant filtering
        connection: Optional database connection for transaction context
        hard_delete: If True, permanently delete. If False, soft delete.

    Returns:
        Number of records deleted

    Example:
        # Soft delete
        count = await bulk_delete(Product, product_ids, db_pool, tenant_id)

        # Hard delete (permanent)
        count = await bulk_delete(Product, product_ids, db_pool, tenant_id, hard_delete=True)
    """
    if not ids:
        return 0

    # Get model metadata
    table_name = model_class.__table_name__
    schema = getattr(model_class, "__schema__", "public")
    multi_tenant = getattr(model_class, "__multi_tenant__", True)
    soft_delete_enabled = getattr(model_class, "__soft_delete__", True)
    temporal_strategy = getattr(model_class, "__temporal_strategy__", "none")

    full_table = f'"{schema}"."{table_name}"'
    now = datetime.now(timezone.utc)

    params: List[Any] = list(ids)
    param_idx = len(ids) + 1

    # Build WHERE clause
    placeholders = ", ".join(f"${i + 1}" for i in range(len(ids)))
    where_parts = [f"id IN ({placeholders})"]

    if temporal_strategy == "scd2":
        where_parts.append("valid_to IS NULL")

    if soft_delete_enabled and not hard_delete:
        where_parts.append("deleted_at IS NULL")

    if multi_tenant and tenant_id:
        where_parts.append(f"tenant_id = ${param_idx}")
        params.append(tenant_id)
        param_idx += 1

    where_clause = " AND ".join(where_parts)

    if hard_delete or not soft_delete_enabled:
        sql = f"DELETE FROM {full_table} WHERE {where_clause}"
    else:
        # Soft delete: set deleted_at
        sql = f"UPDATE {full_table} SET deleted_at = ${param_idx} WHERE {where_clause}"
        params.append(now)

    if connection:
        result = await connection.execute(sql, *params)
    else:
        async with db_pool.acquire() as conn:
            result = await conn.execute(sql, *params)

    # Parse result to get count
    if isinstance(result, str):
        if result.startswith("UPDATE") or result.startswith("DELETE"):
            return int(result.split()[-1])
    return 0


def _get_record_value(
    record: Any,
    column: str,
    tenant_id: UUID | None,
    multi_tenant: bool,
    temporal_strategy: str,
    now: datetime,
) -> Any:
    """
    Get the value for a column from a record, with automatic defaults.

    Handles:
    - Auto-generating UUIDs for id if not set
    - Setting tenant_id for multi-tenant models
    - Setting timestamps (created_at, updated_at)
    - Setting temporal fields (valid_from, valid_to) for SCD2
    """
    # Handle special columns
    if column == "id":
        value = getattr(record, "id", None)
        return value if value else uuid4()

    if column == "tenant_id" and multi_tenant:
        value = getattr(record, "tenant_id", None)
        return value if value else tenant_id

    if column == "created_at":
        value = getattr(record, "created_at", None)
        return value if value else now

    if column == "updated_at":
        return now  # Always update to current time

    if column == "valid_from" and temporal_strategy == "scd2":
        value = getattr(record, "valid_from", None)
        return value if value else now

    if column == "valid_to" and temporal_strategy == "scd2":
        return None  # New records are always current

    if column == "deleted_at":
        return getattr(record, "deleted_at", None)

    # Regular column
    return getattr(record, column, None)
