"""Relationship cascade manager for mock data generation.

This module provides the RelationshipCascadeManager which handles creating
related models when cascade=True is passed to MockFactory.create().

Example:
    >>> from ff_storage.mock import MockFactory
    >>>
    >>> factory = MockFactory(seed=42)
    >>> # Creates Author AND automatically creates related Posts
    >>> author = factory.create(Author, cascade=True)
    >>> len(author.posts)  # Posts were created
    3
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import uuid4

if TYPE_CHECKING:
    from pydantic import BaseModel

    from .generators import ValueGeneratorRegistry

T = TypeVar("T", bound="BaseModel")


class RelationshipCascadeManager:
    """Manages cascading mock data creation through relationships.

    When creating mock data with cascade=True, this manager:
    1. Discovers relationships on the model via RelationshipRegistry
    2. For one-to-many: Creates child instances referencing the parent
    3. For many-to-one: Creates parent instance and populates FK
    4. Tracks visited models to prevent infinite loops

    Example:
        >>> cascade_manager = RelationshipCascadeManager(factory)
        >>>
        >>> # Create author with cascaded posts
        >>> author, related = cascade_manager.create_with_cascade(Author)
        >>> len(related["posts"])  # Posts created referencing author
        3
    """

    DEFAULT_COLLECTION_SIZE = 3
    MAX_COLLECTION_SIZE = 10

    def __init__(
        self,
        registry: ValueGeneratorRegistry,
        max_depth: int = 3,
        collection_size: int | tuple[int, int] = 3,
    ):
        """Initialize the cascade manager.

        Args:
            registry: The ValueGeneratorRegistry to use for value generation
            max_depth: Maximum cascade depth to prevent infinite recursion
            collection_size: Number of items to create for one-to-many relationships.
                           Can be an int or tuple (min, max) for random range.
        """
        self._registry = registry
        self._max_depth = max_depth
        self._collection_size = collection_size
        self._visited: set[tuple[str, str]] = set()  # (model_name, id)

    def create_with_cascade(
        self,
        model_class: type[T],
        overrides: dict[str, Any] | None = None,
        depth: int = 0,
        parent_context: dict[str, Any] | None = None,
    ) -> tuple[T, dict[str, list[Any]]]:
        """Create a model instance with cascading relationships.

        Args:
            model_class: The Pydantic model class to instantiate
            overrides: Field values to override
            depth: Current cascade depth
            parent_context: Context from parent creation (FK values, etc.)

        Returns:
            Tuple of (created_instance, related_instances_dict)
            where related_instances_dict maps relationship_name -> list of instances
        """
        from .factory import MockFactory

        overrides = overrides or {}
        parent_context = parent_context or {}
        related_instances: dict[str, list[Any]] = {}

        # Check depth limit
        if depth >= self._max_depth:
            factory = MockFactory(registry=self._registry)
            instance = factory.create(model_class, overrides=overrides, cascade=False)
            return instance, related_instances

        # Create the main instance first (without cascade)
        factory = MockFactory(registry=self._registry)

        # Merge parent context into overrides (FK fields from parent)
        merged_overrides = {**parent_context, **overrides}
        instance = factory.create(model_class, overrides=merged_overrides, cascade=False)

        # Track this instance to prevent cycles
        model_name = model_class.__name__
        instance_id = str(getattr(instance, "id", uuid4()))
        visit_key = (model_name, instance_id)

        if visit_key in self._visited:
            return instance, related_instances

        self._visited.add(visit_key)

        try:
            # Get relationships for this model
            relationships = self._get_relationships(model_class)

            for rel_name, rel_config in relationships.items():
                # Skip if already provided in overrides
                if rel_name in overrides:
                    continue

                related = self._cascade_relationship(
                    instance=instance,
                    rel_name=rel_name,
                    rel_config=rel_config,
                    depth=depth,
                )

                if related:
                    related_instances[rel_name] = related

        finally:
            # Clean up visited set (allow this model to be created again in another context)
            self._visited.discard(visit_key)

        return instance, related_instances

    def _cascade_relationship(
        self,
        instance: Any,
        rel_name: str,
        rel_config: Any,
        depth: int,
    ) -> list[Any]:
        """Cascade creation for a single relationship.

        Args:
            instance: The parent instance
            rel_name: Name of the relationship
            rel_config: RelationshipConfig for the relationship
            depth: Current cascade depth

        Returns:
            List of created related instances
        """
        related_instances = []

        try:
            from ..relationships.registry import RelationshipRegistry
            from ..relationships.types import RelationType

            # Get the target model class
            target_model_name = rel_config.target_model
            target_model = RelationshipRegistry.resolve_model(target_model_name)

            if not target_model:
                return related_instances

            relationship_type = rel_config.relationship_type

            if relationship_type == RelationType.ONE_TO_MANY:
                # Create child instances referencing this parent
                related_instances = self._cascade_one_to_many(
                    parent=instance,
                    target_model=target_model,
                    rel_config=rel_config,
                    depth=depth,
                )

            elif relationship_type == RelationType.MANY_TO_ONE:
                # For many-to-one, the FK is on this model
                # Parent should already exist (or we create it)
                # This is handled by populating the FK field during instance creation
                pass

            elif relationship_type == RelationType.MANY_TO_MANY:
                # For M2M, create instances and link table entries
                related_instances = self._cascade_many_to_many(
                    parent=instance,
                    target_model=target_model,
                    rel_config=rel_config,
                    depth=depth,
                )

        except ImportError:
            pass
        except Exception:
            pass

        return related_instances

    def _cascade_one_to_many(
        self,
        parent: Any,
        target_model: type,
        rel_config: Any,
        depth: int,
    ) -> list[Any]:
        """Create child instances for a one-to-many relationship.

        Args:
            parent: The parent instance
            target_model: The child model class
            rel_config: RelationshipConfig
            depth: Current cascade depth

        Returns:
            List of created child instances
        """
        children = []

        # Determine FK field on child model
        fk_field = rel_config.foreign_key
        if not fk_field:
            # Auto-detect: look for field ending in _id matching parent table
            parent_table = (
                parent.__class__.table_name() if hasattr(parent.__class__, "table_name") else None
            )
            if parent_table:
                # Try common patterns: author_id, parent_id, {table}_id
                fk_candidates = [
                    f"{parent_table[:-1]}_id"
                    if parent_table.endswith("s")
                    else f"{parent_table}_id",
                    f"{parent.__class__.__name__.lower()}_id",
                ]

                for candidate in fk_candidates:
                    if candidate in target_model.model_fields:
                        fk_field = candidate
                        break

        if not fk_field:
            return children

        # Determine how many children to create
        count = self._get_collection_count()

        # Create children referencing parent
        parent_id = getattr(parent, "id", None)
        if parent_id is None:
            return children

        for _ in range(count):
            child, _ = self.create_with_cascade(
                model_class=target_model,
                overrides={fk_field: parent_id},
                depth=depth + 1,
            )
            children.append(child)

        return children

    def _cascade_many_to_many(
        self,
        parent: Any,
        target_model: type,
        rel_config: Any,
        depth: int,
    ) -> list[Any]:
        """Create related instances for a many-to-many relationship.

        Note: This creates the target instances but does NOT create
        link table entries. That would require database access.

        Args:
            parent: The parent instance
            target_model: The target model class
            rel_config: RelationshipConfig
            depth: Current cascade depth

        Returns:
            List of created target instances
        """
        targets = []

        count = self._get_collection_count()

        for _ in range(count):
            target, _ = self.create_with_cascade(
                model_class=target_model,
                depth=depth + 1,
            )
            targets.append(target)

        return targets

    def _get_relationships(self, model_class: type) -> dict[str, Any]:
        """Get relationships for a model class.

        Args:
            model_class: The model class

        Returns:
            Dict mapping relationship name -> RelationshipConfig
        """
        try:
            from ..relationships.registry import RelationshipRegistry

            return RelationshipRegistry.get_relationships(model_class.__name__)
        except ImportError:
            return {}
        except Exception:
            return {}

    def _get_collection_count(self) -> int:
        """Get the number of items to create for a collection relationship.

        Returns:
            Number of items to create
        """
        if isinstance(self._collection_size, tuple):
            min_size, max_size = self._collection_size
            return random.randint(min_size, max_size)
        return self._collection_size

    def reset_visited(self) -> None:
        """Reset the visited set for a new cascade operation."""
        self._visited.clear()


def cascade_create(
    model_class: type[T],
    registry: ValueGeneratorRegistry,
    overrides: dict[str, Any] | None = None,
    max_depth: int = 3,
    collection_size: int | tuple[int, int] = 3,
) -> tuple[T, dict[str, list[Any]]]:
    """Convenience function for cascading mock creation.

    Args:
        model_class: The Pydantic model class to instantiate
        registry: The ValueGeneratorRegistry to use
        overrides: Field values to override
        max_depth: Maximum cascade depth
        collection_size: Number of items for one-to-many relationships

    Returns:
        Tuple of (created_instance, related_instances_dict)

    Example:
        >>> from ff_storage.mock import ValueGeneratorRegistry, cascade_create
        >>>
        >>> registry = ValueGeneratorRegistry(seed=42)
        >>> author, related = cascade_create(Author, registry)
        >>> print(f"Created author with {len(related.get('posts', []))} posts")
    """
    manager = RelationshipCascadeManager(
        registry=registry,
        max_depth=max_depth,
        collection_size=collection_size,
    )
    return manager.create_with_cascade(model_class, overrides=overrides)
