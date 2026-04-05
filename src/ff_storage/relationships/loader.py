"""Relationship loader for eager loading related objects.

This module provides RelationshipLoader which implements the "selectinload"
pattern - batch loading with IN clauses to prevent N+1 query problems.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Type, TypeVar
from uuid import UUID

from .registry import RelationshipRegistry

if TYPE_CHECKING:
    from ..db.pool.postgres import PostgresPool
    from ..pydantic_support.base import PydanticModel
    from .config import RelationshipConfig

T = TypeVar("T", bound="PydanticModel")


class RelationshipLoader:
    """
    Loads relationships for a set of model instances using batch queries.

    This loader uses the "selectinload" pattern to efficiently load related
    objects. Instead of N+1 queries, it executes:
    1. One query to fetch the main objects
    2. One query per relationship using IN clause

    Example:
        # Without eager loading: N+1 queries
        authors = await Query(Author).execute(db_pool, tenant_id)
        for author in authors:
            posts = await Query(Post).filter(...).execute(...)  # N queries!

        # With eager loading: 2 queries total
        authors = await (
            Query(Author)
            .load(["posts"])
            .execute(db_pool, tenant_id)
        )
        for author in authors:
            posts = author.posts  # Already loaded!

    Attributes:
        model_class: The main model class being loaded
        model_name: Name of the model class
    """

    def __init__(self, model_class: Type[T]):
        """
        Initialize the loader.

        Args:
            model_class: The model class whose relationships will be loaded
        """
        self.model_class = model_class
        self.model_name = model_class.__name__

    async def load_relationships(
        self,
        instances: List[T],
        relationship_names: List[str],
        db_pool: "PostgresPool",
        tenant_id: UUID | None = None,
        connection: Any = None,
    ) -> List[T]:
        """
        Load specified relationships for a list of instances.

        Supports nested relationships using dot notation (e.g., "posts.comments").
        For nested paths, loads the first level, then recursively loads the rest.

        Args:
            instances: List of model instances to load relationships for
            relationship_names: Names of relationships to load (supports dot notation)
            db_pool: Database connection pool
            tenant_id: Optional tenant ID for multi-tenant filtering
            connection: Optional database connection for transaction context

        Returns:
            The same instances with relationships populated

        Raises:
            ValueError: If a relationship name is not found

        Example:
            # Load posts for authors
            await loader.load_relationships(authors, ["posts"], db_pool, tenant_id)

            # Load posts and their comments (nested)
            await loader.load_relationships(authors, ["posts.comments"], db_pool, tenant_id)

            # Load multiple relationships including nested
            await loader.load_relationships(authors, ["posts.comments", "profile"], db_pool, tenant_id)
        """
        if not instances:
            return instances

        for rel_path in relationship_names:
            await self._load_nested_path(instances, rel_path, db_pool, tenant_id, connection)

        return instances

    async def _load_nested_path(
        self,
        instances: List[T],
        rel_path: str,
        db_pool: "PostgresPool",
        tenant_id: UUID | None,
        connection: Any = None,
    ) -> None:
        """
        Load a potentially nested relationship path.

        For simple paths (no dots), loads directly.
        For nested paths, loads the first level then recurses.

        Args:
            instances: List of model instances
            rel_path: Relationship path (e.g., "posts" or "posts.comments")
            db_pool: Database connection pool
            tenant_id: Tenant ID for filtering
            connection: Optional database connection for transaction context
        """
        if not instances or not rel_path:
            return

        # Split the path into first level and remaining
        parts = rel_path.split(".", 1)
        first_rel = parts[0]
        remaining_path = parts[1] if len(parts) > 1 else None

        # Load the first level relationship
        config = RelationshipRegistry.get_relationship(self.model_name, first_rel)
        if not config:
            raise ValueError(f"Unknown relationship: {self.model_name}.{first_rel}")

        await self._load_relationship(instances, first_rel, config, db_pool, tenant_id, connection)

        # If there's a remaining path, recurse into nested instances
        if remaining_path:
            # Collect all nested instances from the first-level relationship
            nested_instances: List[Any] = []
            for inst in instances:
                rel_value = getattr(inst, first_rel, None)
                if rel_value is not None:
                    if isinstance(rel_value, list):
                        nested_instances.extend(rel_value)
                    else:
                        nested_instances.append(rel_value)

            # Load remaining path on nested instances
            if nested_instances:
                # Get the model class of the nested instances
                nested_model_class = type(nested_instances[0])
                nested_loader = RelationshipLoader(nested_model_class)
                await nested_loader._load_nested_path(
                    nested_instances, remaining_path, db_pool, tenant_id, connection
                )

    async def _load_relationship(
        self,
        instances: List[T],
        rel_name: str,
        config: "RelationshipConfig",
        db_pool: "PostgresPool",
        tenant_id: UUID | None,
        connection: Any = None,
    ) -> None:
        """
        Load a single relationship for all instances.

        Handles three relationship types:
        - One-to-many: SELECT * FROM targets WHERE owner_id IN (...)
        - Many-to-one: SELECT * FROM targets WHERE id IN (...)
        - Many-to-many: Two-step JOIN through link table

        Args:
            instances: List of model instances
            rel_name: Name of the relationship to load
            config: RelationshipConfig for this relationship
            db_pool: Database connection pool
            tenant_id: Tenant ID for filtering
            connection: Optional database connection for transaction context
        """
        if config.is_many_to_many():
            await self._load_many_to_many(
                instances, rel_name, config, db_pool, tenant_id, connection
            )
        elif config.is_collection:
            await self._load_one_to_many(
                instances, rel_name, config, db_pool, tenant_id, connection
            )
        else:
            await self._load_many_to_one(
                instances, rel_name, config, db_pool, tenant_id, connection
            )

    async def _load_one_to_many(
        self,
        instances: List[T],
        rel_name: str,
        config: "RelationshipConfig",
        db_pool: "PostgresPool",
        tenant_id: UUID | None,
        connection: Any = None,
    ) -> None:
        """
        Load a one-to-many relationship.

        Example: Author.posts - load all Posts for given Authors

        Query: SELECT * FROM posts WHERE author_id IN ($1, $2, ...) AND ...

        Args:
            instances: List of model instances
            rel_name: Name of the relationship to load
            config: RelationshipConfig for this relationship
            db_pool: Database connection pool
            tenant_id: Tenant ID for filtering
            connection: Optional database connection for transaction context
        """
        # Resolve target model
        target_model = RelationshipRegistry.resolve_model(config.target_model)
        if not target_model:
            raise ValueError(f"Cannot resolve model: {config.target_model}")

        # Get IDs from instances
        instance_ids = [inst.id for inst in instances if inst.id]
        if not instance_ids:
            return

        # Get foreign key column on target
        fk_column = config.get_foreign_key_column()

        # Build and execute query
        related = await self._fetch_related(
            target_model=target_model,
            filter_column=fk_column,
            filter_values=instance_ids,
            db_pool=db_pool,
            tenant_id=tenant_id,
            connection=connection,
        )

        # Group by foreign key
        grouped: Dict[UUID, List] = {id_: [] for id_ in instance_ids}
        for item in related:
            fk_value = getattr(item, fk_column, None)
            if fk_value and fk_value in grouped:
                grouped[fk_value].append(item)

        # Assign to instances
        for inst in instances:
            self._set_relationship(inst, rel_name, grouped.get(inst.id, []))

    async def _load_many_to_one(
        self,
        instances: List[T],
        rel_name: str,
        config: "RelationshipConfig",
        db_pool: "PostgresPool",
        tenant_id: UUID | None,
        connection: Any = None,
    ) -> None:
        """
        Load a many-to-one relationship.

        Example: Post.author - load Authors for given Posts

        Query: SELECT * FROM authors WHERE id IN ($1, $2, ...) AND ...

        Args:
            instances: List of model instances
            rel_name: Name of the relationship to load
            config: RelationshipConfig for this relationship
            db_pool: Database connection pool
            tenant_id: Tenant ID for filtering
            connection: Optional database connection for transaction context
        """
        # Resolve target model
        target_model = RelationshipRegistry.resolve_model(config.target_model)
        if not target_model:
            raise ValueError(f"Cannot resolve model: {config.target_model}")

        # Get foreign key column on this model
        fk_column = config.get_foreign_key_column()

        # Get unique FK values
        fk_values = list(
            set(getattr(inst, fk_column) for inst in instances if getattr(inst, fk_column, None))
        )

        if not fk_values:
            # No foreign keys set, leave relationships as None
            return

        # Build and execute query
        related = await self._fetch_related(
            target_model=target_model,
            filter_column="id",
            filter_values=fk_values,
            db_pool=db_pool,
            tenant_id=tenant_id,
            connection=connection,
        )

        # Index by ID
        related_by_id = {item.id: item for item in related}

        # Assign to instances
        for inst in instances:
            fk_value = getattr(inst, fk_column, None)
            if fk_value:
                self._set_relationship(inst, rel_name, related_by_id.get(fk_value))
            else:
                self._set_relationship(inst, rel_name, None)

    async def _load_many_to_many(
        self,
        instances: List[T],
        rel_name: str,
        config: "RelationshipConfig",
        db_pool: "PostgresPool",
        tenant_id: UUID | None,
        connection: Any = None,
    ) -> None:
        """
        Load a many-to-many relationship.

        Example: Post.tags - load Tags for given Posts via PostTag junction

        Queries:
        1. SELECT * FROM post_tags WHERE post_id IN ($1, $2, ...)
        2. SELECT * FROM tags WHERE id IN ($3, $4, ...)

        Args:
            instances: List of model instances
            rel_name: Name of the relationship to load
            config: RelationshipConfig for this relationship
            db_pool: Database connection pool
            tenant_id: Tenant ID for filtering
            connection: Optional database connection for transaction context
        """
        # Resolve target and link models
        target_model = RelationshipRegistry.resolve_model(config.target_model)
        link_model = RelationshipRegistry.resolve_model(config.link_model)

        if not target_model:
            raise ValueError(f"Cannot resolve model: {config.target_model}")
        if not link_model:
            raise ValueError(f"Cannot resolve link model: {config.link_model}")

        link_config = config.get_link_table_config()
        if not link_config:
            return

        local_key = link_config["local_key"]
        remote_key = link_config["remote_key"]

        # Get IDs from instances
        instance_ids = [inst.id for inst in instances if inst.id]
        if not instance_ids:
            return

        # Step 1: Fetch link records
        link_records = await self._fetch_related(
            target_model=link_model,
            filter_column=local_key,
            filter_values=instance_ids,
            db_pool=db_pool,
            tenant_id=tenant_id,
            connection=connection,
        )

        if not link_records:
            # No links, set empty lists
            for inst in instances:
                self._set_relationship(inst, rel_name, [])
            return

        # Build mapping: local_id -> [remote_ids]
        local_to_remote: Dict[UUID, List[UUID]] = {id_: [] for id_ in instance_ids}
        remote_ids_needed = set()

        for link in link_records:
            local_id = getattr(link, local_key, None)
            remote_id = getattr(link, remote_key, None)
            if local_id and remote_id:
                local_to_remote[local_id].append(remote_id)
                remote_ids_needed.add(remote_id)

        if not remote_ids_needed:
            for inst in instances:
                self._set_relationship(inst, rel_name, [])
            return

        # Step 2: Fetch target records
        target_records = await self._fetch_related(
            target_model=target_model,
            filter_column="id",
            filter_values=list(remote_ids_needed),
            db_pool=db_pool,
            tenant_id=tenant_id,
            connection=connection,
        )

        # Index targets by ID
        targets_by_id = {item.id: item for item in target_records}

        # Assign to instances
        for inst in instances:
            remote_ids = local_to_remote.get(inst.id, [])
            related_items = [targets_by_id[rid] for rid in remote_ids if rid in targets_by_id]
            self._set_relationship(inst, rel_name, related_items)

    async def _fetch_related(
        self,
        target_model: Type,
        filter_column: str,
        filter_values: List[UUID],
        db_pool: "PostgresPool",
        tenant_id: UUID | None,
        connection: Any = None,
    ) -> List[Any]:
        """
        Fetch related records using an IN query.

        Builds a query with proper temporal and tenant filtering.

        Args:
            target_model: The model class to query
            filter_column: Column name to filter on
            filter_values: Values to filter by (IN clause)
            db_pool: Database connection pool
            tenant_id: Tenant ID for filtering
            connection: Optional database connection for transaction context
        """
        from ..query import Query
        from ..query.expressions import FieldProxy

        # Build filter expression
        filter_expr = FieldProxy(filter_column).in_(filter_values)

        # Execute query with connection for transaction context
        return (
            await Query(target_model)
            .filter(filter_expr)
            .execute(db_pool, tenant_id=tenant_id, connection=connection)
        )

    def _set_relationship(self, instance: T, rel_name: str, value: Any) -> None:
        """
        Set a relationship value on an instance.

        Uses the Relationship descriptor's __set__ method.
        """
        rel_descriptor = getattr(type(instance), rel_name, None)
        if rel_descriptor and hasattr(rel_descriptor, "__set__"):
            rel_descriptor.__set__(instance, value)
        else:
            # Fallback: set directly on instance __dict__
            instance.__dict__[rel_name] = value
