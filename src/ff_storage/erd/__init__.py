"""ERD (Entity Relationship Diagram) module for ff-storage.

This module provides tools for generating ERD data from PydanticModel classes,
including model discovery, relationship detection, and Mermaid diagram generation.

Example:
    >>> from ff_storage.erd import ERDBuilder, to_mermaid
    >>>
    >>> # Build ERD from all discovered models
    >>> builder = ERDBuilder()
    >>> erd = builder.build(schema_filter="public")
    >>>
    >>> # Generate Mermaid diagram
    >>> print(to_mermaid(erd))
    erDiagram
        users ||--o{ posts : "author_id"
        ...
    >>>
    >>> # Access model registry
    >>> User = builder.get_model_class("users")
"""

from .builder import ERDBuilder
from .mermaid import to_mermaid, to_mermaid_compact
from .models import ERDColumn, ERDRelationship, ERDResponse, ERDTable

__all__ = [
    # Builder
    "ERDBuilder",
    # Models
    "ERDColumn",
    "ERDTable",
    "ERDRelationship",
    "ERDResponse",
    # Mermaid
    "to_mermaid",
    "to_mermaid_compact",
]
