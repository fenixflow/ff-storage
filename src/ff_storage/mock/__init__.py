"""Mock data generation for ff-storage Pydantic models.

This module provides infrastructure for generating realistic mock data
for testing and development, using the Field() metadata as the source of truth.

Example:
    >>> from ff_storage import PydanticModel, Field
    >>> from ff_storage.mock import MockFactory, ValueGeneratorRegistry
    >>>
    >>> class User(PydanticModel):
    ...     email: str = Field(max_length=255)
    ...     first_name: str = Field(max_length=100)
    ...     age: int = Field(ge=18, le=120)
    ...
    >>> # Simple creation
    >>> user = User.create_mock()
    >>>
    >>> # With overrides
    >>> admin = User.create_mock(overrides={"role": "admin"})
    >>>
    >>> # Batch creation
    >>> users = User.create_mock_batch(100, seed=42)
    >>>
    >>> # Using factory directly
    >>> factory = MockFactory(seed=42)
    >>> user = factory.create(User)

Extension Pattern:
    >>> from ff_storage.mock import GeneratorExtension, ValueGeneratorRegistry
    >>>
    >>> class InsuranceExtension(GeneratorExtension):
    ...     NAME_PATTERNS = [
    ...         (r"^policy_number$", lambda f, m: f.bothify("POL-####-????").upper()),
    ...     ]
    >>>
    >>> registry = ValueGeneratorRegistry(seed=42).extend(InsuranceExtension())
    >>> policy = Policy.create_mock(registry=registry)
"""

from .extensions import ExampleExtension, GeneratorExtension, GeneratorFunc
from .generators import (
    DEFAULT_NAME_PATTERNS,
    NAMED_PATTERNS,
    TYPE_GENERATORS,
    FieldMeta,
    ValueGeneratorRegistry,
    get_named_pattern_generator,
    get_pattern_generator,
    get_type_generator,
)

__all__ = [
    # Main classes
    "ValueGeneratorRegistry",
    "FieldMeta",
    # Extensions
    "GeneratorExtension",
    "ExampleExtension",
    "GeneratorFunc",
    # Pattern generators
    "DEFAULT_NAME_PATTERNS",
    "NAMED_PATTERNS",
    "get_pattern_generator",
    "get_named_pattern_generator",
    # Type generators
    "TYPE_GENERATORS",
    "get_type_generator",
]

# Import factory and cascade after defining __all__ to avoid circular imports
# These will be added as the implementation progresses
try:
    from .cascade import RelationshipCascadeManager  # noqa: F401

    __all__.append("RelationshipCascadeManager")
except ImportError:
    pass

try:
    from .factory import MockFactory  # noqa: F401

    __all__.append("MockFactory")
except ImportError:
    pass
