"""
Pydantic integration for ff-storage.

Provides Pydantic base model with temporal management and repository pattern.
"""

from .base import PydanticModel
from .introspector import PydanticSchemaIntrospector
from .jsonb_utils import deserialize_jsonb_fields, serialize_jsonb_fields
from .mongo_repository import MongoRepository
from .repository import PydanticRepository
from .type_mapping import map_pydantic_type_to_column_type

__all__ = [
    "PydanticModel",
    "PydanticRepository",
    "MongoRepository",
    "PydanticSchemaIntrospector",
    "deserialize_jsonb_fields",
    "map_pydantic_type_to_column_type",
    "serialize_jsonb_fields",
]
