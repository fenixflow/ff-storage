"""Relationship descriptor for PydanticModel classes.

This module provides the Relationship descriptor that enables defining
relationships between models with a clean, declarative syntax.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, List, TypeVar, get_args, get_origin, overload

from .config import RelationshipConfig
from .registry import RelationshipRegistry
from .types import RelationType

if TYPE_CHECKING:
    from ..pydantic_support.base import PydanticModel

T = TypeVar("T", bound="PydanticModel")


class Relationship(Generic[T]):
    """
    Descriptor for defining relationships between PydanticModel classes.

    This descriptor enables declarative relationship definitions that:
    - Auto-register with RelationshipRegistry
    - Support one-to-many, many-to-one, and many-to-many relationships
    - Provide RelationshipProxy for query building at class level
    - Cache loaded relationship data at instance level

    Example:
        class Author(PydanticModel):
            __table_name__ = "authors"
            name: str
            posts: List["Post"] = Relationship(back_populates="author")

        class Post(PydanticModel):
            __table_name__ = "posts"
            title: str
            author_id: UUID = Field(json_schema_extra={"db_foreign_key": "authors.id"})
            author: "Author" = Relationship(back_populates="posts")

        # Many-to-many example
        class Post(PydanticModel):
            tags: List["Tag"] = Relationship(
                link_model="PostTag",
                link_local_key="post_id",
                link_remote_key="tag_id",
            )

    Attributes:
        back_populates: Name of the reverse relationship on target model
        foreign_key: Explicit foreign key column (auto-detected if not provided)
        link_model: For M2M, the junction table model name
        link_local_key: For M2M, FK column pointing to this model
        link_remote_key: For M2M, FK column pointing to target model
        lazy: Loading strategy ("select", "joined", "subquery", "noload")
        order_by: Default ordering for collection relationships
    """

    def __init__(
        self,
        *,
        back_populates: str | None = None,
        foreign_key: str | None = None,
        link_model: str | None = None,
        link_local_key: str | None = None,
        link_remote_key: str | None = None,
        lazy: str = "select",
        order_by: str | None = None,
    ):
        """
        Initialize a relationship.

        Args:
            back_populates: Name of the reverse relationship on target model
            foreign_key: Explicit FK column (auto-detected if not provided)
            link_model: For M2M, the junction table model name
            link_local_key: For M2M, FK column pointing to this model
            link_remote_key: For M2M, FK column pointing to target model
            lazy: Loading strategy ("select", "joined", "subquery", "noload")
            order_by: Default ordering for collection relationships
        """
        self.back_populates = back_populates
        self.foreign_key = foreign_key
        self.link_model = link_model
        self.link_local_key = link_local_key
        self.link_remote_key = link_remote_key
        self.lazy = lazy
        self.order_by = order_by

        # Set by __set_name__
        self._name: str | None = None
        self._owner: type | None = None
        self._config: RelationshipConfig | None = None

    def __set_name__(self, owner: type, name: str) -> None:
        """
        Called when the descriptor is assigned to a class attribute.

        This method:
        1. Analyzes the type annotation to determine relationship type
        2. Creates RelationshipConfig with all metadata
        3. Registers with RelationshipRegistry

        Args:
            owner: The class this descriptor is assigned to
            name: The attribute name
        """
        self._name = name
        self._owner = owner

        # Get type hint to determine if this is a collection
        annotations = getattr(owner, "__annotations__", {})
        type_hint = annotations.get(name)

        is_collection = False
        target_model = ""
        relationship_type = RelationType.MANY_TO_ONE

        if type_hint:
            origin = get_origin(type_hint)
            if origin is list:
                is_collection = True
                args = get_args(type_hint)
                if args:
                    arg = args[0]
                    # Handle forward references (strings)
                    if isinstance(arg, str):
                        target_model = arg.strip("'\"")
                    else:
                        target_model = getattr(arg, "__name__", str(arg))

                # Determine relationship type based on link_model
                if self.link_model:
                    relationship_type = RelationType.MANY_TO_MANY
                else:
                    relationship_type = RelationType.ONE_TO_MANY
            else:
                # Single reference
                if isinstance(type_hint, str):
                    target_model = type_hint.strip("'\"")
                else:
                    target_model = getattr(type_hint, "__name__", str(type_hint))
                relationship_type = RelationType.MANY_TO_ONE

        # Create configuration
        self._config = RelationshipConfig(
            target_model=target_model,
            back_populates=self.back_populates,
            foreign_key=self.foreign_key,
            relationship_type=relationship_type,
            link_model=self.link_model,
            link_local_key=self.link_local_key,
            link_remote_key=self.link_remote_key,
            lazy=self.lazy,
            is_collection=is_collection,
            order_by=self.order_by,
            owner_model=owner.__name__,
            attribute_name=name,
        )

        # Register with the global registry
        RelationshipRegistry.register(owner.__name__, name, self._config)

        # Store on the class for introspection
        if not hasattr(owner, "_relationships"):
            owner._relationships = {}
        owner._relationships[name] = self._config

    @overload
    def __get__(self, instance: None, owner: type) -> "RelationshipProxy":
        """Class-level access returns RelationshipProxy for query building."""
        ...

    @overload
    def __get__(self, instance: "PydanticModel", owner: type) -> T | List[T] | None:
        """Instance-level access returns the cached relationship data."""
        ...

    def __get__(
        self, instance: "PydanticModel | None", owner: type
    ) -> "T | List[T] | RelationshipProxy | None":
        """
        Get the relationship value.

        At class level: Returns RelationshipProxy for query building
        At instance level: Returns cached relationship data or empty collection/None

        Args:
            instance: The model instance (or None for class access)
            owner: The model class

        Returns:
            RelationshipProxy (class access) or cached data (instance access)
        """
        if instance is None:
            # Class-level access returns the descriptor for query building
            return RelationshipProxy(self._name, self._config, owner)

        # Instance-level access returns cached data from instance __dict__
        # We use __dict__ directly instead of WeakKeyDictionary to ensure
        # the cached data lives as long as the instance
        cache_key = f"_rel_cache_{self._name}"
        if cache_key in instance.__dict__:
            return instance.__dict__[cache_key]

        # Return appropriate empty value
        if self._config and self._config.is_collection:
            return []
        return None

    def __set__(self, instance: Any, value: Any) -> None:
        """
        Set the relationship value.

        Used by RelationshipLoader to populate loaded relationships.
        Stores in instance __dict__ to ensure data lives with instance.

        Args:
            instance: The model instance
            value: The related model(s) to cache
        """
        cache_key = f"_rel_cache_{self._name}"
        instance.__dict__[cache_key] = value

    @property
    def config(self) -> RelationshipConfig | None:
        """Get the relationship configuration."""
        return self._config


class RelationshipProxy:
    """
    Proxy returned when accessing a relationship at class level.

    This proxy is used for building queries with joins. It holds a reference
    to the relationship configuration and can be passed to Query.join().

    Example:
        # Query.join() accepts RelationshipProxy
        Query(Author).join(Author.posts)  # Author.posts returns RelationshipProxy

    Attributes:
        name: The relationship attribute name
        config: The RelationshipConfig
        owner: The owner model class
    """

    def __init__(self, name: str | None, config: RelationshipConfig | None, owner: type):
        """
        Initialize the proxy.

        Args:
            name: Relationship attribute name
            config: RelationshipConfig with relationship metadata
            owner: The model class that owns this relationship
        """
        self.name = name
        self.config = config
        self.owner = owner

    def __repr__(self) -> str:
        owner_name = getattr(self.owner, "__name__", "Unknown") if self.owner else "None"
        return f"<RelationshipProxy {owner_name}.{self.name or 'unknown'}>"

    def __hash__(self) -> int:
        owner_name = getattr(self.owner, "__name__", "") if self.owner else ""
        return hash((owner_name, self.name or ""))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RelationshipProxy):
            return False
        self_owner = getattr(self.owner, "__name__", "") if self.owner else ""
        other_owner = getattr(other.owner, "__name__", "") if other.owner else ""
        return self_owner == other_owner and self.name == other.name
