"""Relationship definitions for ff-storage models.

This module provides relationship support for defining associations between
PydanticModel classes with automatic query builder integration.

Example:
    from ff_storage import PydanticModel, Field
    from ff_storage.relationships import Relationship
    from typing import List
    from uuid import UUID

    class Author(PydanticModel):
        __table_name__ = "authors"
        name: str

        # One-to-many: Author has many Posts
        posts: List["Post"] = Relationship(back_populates="author")

    class Post(PydanticModel):
        __table_name__ = "posts"
        title: str
        author_id: UUID = Field(json_schema_extra={"db_foreign_key": "authors.id"})

        # Many-to-one: Post belongs to Author
        author: "Author" = Relationship(back_populates="posts")

    # Many-to-many example
    class Tag(PydanticModel):
        __table_name__ = "tags"
        name: str

    class Post(PydanticModel):
        # Many-to-many via PostTag junction table
        tags: List["Tag"] = Relationship(
            link_model="PostTag",
            link_local_key="post_id",
            link_remote_key="tag_id",
        )
"""

from .config import RelationshipConfig
from .descriptor import Relationship, RelationshipProxy
from .loader import RelationshipLoader
from .registry import RelationshipRegistry
from .types import RelationType

__all__ = [
    "Relationship",
    "RelationshipConfig",
    "RelationshipLoader",
    "RelationshipProxy",
    "RelationshipRegistry",
    "RelationType",
]
