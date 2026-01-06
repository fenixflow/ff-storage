"""Relationship configuration dataclass.

This module provides RelationshipConfig for storing relationship metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .types import RelationType

if TYPE_CHECKING:
    pass


@dataclass
class RelationshipConfig:
    """
    Configuration for a model relationship.

    This dataclass stores all metadata about a relationship, including:
    - Target model reference
    - Back-reference information
    - Foreign key configuration
    - Many-to-many junction table configuration
    - Loading behavior

    Attributes:
        target_model: String reference to the target model class name
        back_populates: Name of the reverse relationship on target model
        foreign_key: Explicit foreign key column (auto-detected if not provided)
        relationship_type: Type of relationship (auto-detected from type hints)
        link_model: For M2M, the junction table model name
        link_local_key: For M2M, FK column pointing to this model
        link_remote_key: For M2M, FK column pointing to target model
        lazy: Loading strategy ("select", "joined", "subquery", "noload")
        is_collection: True for List[Model], False for Model
        order_by: Default ordering for collection relationships
        owner_model: Name of the model that owns this relationship
        attribute_name: Name of this relationship attribute on the owner
    """

    # Core configuration
    target_model: str  # String reference to avoid circular imports
    back_populates: str | None = None
    foreign_key: str | None = None  # Auto-detected if not provided

    # Relationship type (auto-detected from type hints)
    relationship_type: RelationType = RelationType.MANY_TO_ONE

    # For many-to-many relationships
    link_model: str | None = None
    link_local_key: str | None = None
    link_remote_key: str | None = None

    # Loading behavior
    lazy: str = "select"  # "select", "joined", "subquery", "noload"

    # Collection flag (set during type hint analysis)
    is_collection: bool = False  # True for List[Model], False for Model

    # Ordering
    order_by: str | None = None

    # Metadata (set by descriptor)
    owner_model: str | None = None
    attribute_name: str | None = None

    def get_foreign_key_column(self) -> str:
        """
        Get the foreign key column name for this relationship.

        Auto-detection logic:
        - For collections (one-to-many): FK is on target model, named {owner}_id
        - For references (many-to-one): FK is on owner model, named {attribute}_id

        Returns:
            The foreign key column name

        Example:
            >>> # Author.posts (one-to-many)
            >>> config.is_collection = True
            >>> config.owner_model = "Author"
            >>> config.get_foreign_key_column()
            'author_id'

            >>> # Post.author (many-to-one)
            >>> config.is_collection = False
            >>> config.attribute_name = "author"
            >>> config.get_foreign_key_column()
            'author_id'
        """
        if self.foreign_key:
            return self.foreign_key

        # Auto-detect based on relationship type
        if self.is_collection:
            # One-to-many: FK is on target table, named after owner
            # Author.posts -> Post.author_id
            if not self.owner_model:
                raise ValueError(
                    "Cannot auto-detect foreign key: owner_model not set. "
                    "Set owner_model or provide explicit foreign_key."
                )
            return f"{self.owner_model.lower()}_id"
        else:
            # Many-to-one: FK is on owner table, named after attribute
            # Post.author -> Post.author_id
            if not self.attribute_name:
                raise ValueError(
                    "Cannot auto-detect foreign key: attribute_name not set. "
                    "Set attribute_name or provide explicit foreign_key."
                )
            return f"{self.attribute_name}_id"

    def is_many_to_many(self) -> bool:
        """Check if this is a many-to-many relationship."""
        return self.link_model is not None

    def get_link_table_config(self) -> dict[str, str] | None:
        """
        Get many-to-many link table configuration.

        Returns:
            Dict with link table info or None if not M2M
        """
        if not self.is_many_to_many():
            return None

        # Validate required fields for M2M configuration
        if not self.owner_model:
            raise ValueError(
                "Cannot generate link table config: owner_model not set. "
                "Set owner_model for many-to-many relationships."
            )
        if not self.target_model:
            raise ValueError(
                "Cannot generate link table config: target_model not set. "
                "Set target_model for many-to-many relationships."
            )

        return {
            "link_model": self.link_model,
            "local_key": self.link_local_key or f"{self.owner_model.lower()}_id",
            "remote_key": self.link_remote_key or f"{self.target_model.lower()}_id",
        }
