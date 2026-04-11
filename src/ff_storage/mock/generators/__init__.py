"""Mock data generators for ff-storage.

This module provides the value generation infrastructure:
- ValueGeneratorRegistry: Main registry orchestrating generation
- FieldMeta: Metadata about a field for generation
- Type generators: Generate values based on Python types
- Pattern generators: Generate values based on field name patterns
"""

from .pattern_generators import (
    DEFAULT_NAME_PATTERNS,
    NAMED_PATTERNS,
    GeneratorFunc,
    get_named_pattern_generator,
    get_pattern_generator,
)
from .registry import FieldMeta, ValueGeneratorRegistry
from .type_generators import TYPE_GENERATORS, get_type_generator

__all__ = [
    # Registry
    "ValueGeneratorRegistry",
    "FieldMeta",
    # Type generators
    "TYPE_GENERATORS",
    "get_type_generator",
    # Pattern generators
    "DEFAULT_NAME_PATTERNS",
    "NAMED_PATTERNS",
    "GeneratorFunc",
    "get_pattern_generator",
    "get_named_pattern_generator",
]
