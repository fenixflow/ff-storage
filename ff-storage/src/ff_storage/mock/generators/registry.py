"""Value generator registry for mock data generation.

This module provides the ValueGeneratorRegistry which orchestrates
value generation using the priority:

1. Overrides (passed to create_mock)
2. mock_generator (custom function from Field)
3. mock_pattern (explicit pattern name from Field)
4. Field name pattern matching
5. Field constraints (ge/le/max_length)
6. Type fallback

Example:
    >>> from ff_storage.mock.generators import ValueGeneratorRegistry
    >>> registry = ValueGeneratorRegistry(seed=42)
    >>> value = registry.generate("email", meta)  # Uses email pattern
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from faker import Faker

from .pattern_generators import (
    GeneratorFunc,
    get_named_pattern_generator,
    get_pattern_generator,
)
from .type_generators import get_type_generator

if TYPE_CHECKING:
    from ..extensions import GeneratorExtension


@dataclass
class FieldMeta:
    """Metadata about a field for value generation.

    This is extracted from Pydantic FieldInfo and model annotations.

    Attributes:
        name: Field name
        type_name: Simplified type name (e.g., "str", "uuid", "decimal")
        python_type: Original Python type annotation
        is_nullable: Whether field allows None
        is_required: Whether field is required
        max_length: Maximum string length
        min_length: Minimum string length
        ge: Greater than or equal constraint
        le: Less than or equal constraint
        gt: Greater than constraint
        lt: Less than constraint
        precision: Decimal precision (total digits)
        scale: Decimal scale (digits after decimal point)
        enum_class: Enum class if field is an enum
        enum_values: List of enum values
        mock_pattern: Explicit pattern name from Field()
        mock_generator: Custom generator function from Field()
        mock_skip: Whether to skip this field
        description: Field description
    """

    name: str
    type_name: str
    python_type: type | None = None
    is_nullable: bool = False
    is_required: bool = True
    max_length: int | None = None
    min_length: int | None = None
    ge: float | None = None
    le: float | None = None
    gt: float | None = None
    lt: float | None = None
    precision: int | None = None
    scale: int | None = None
    enum_class: type | None = None
    enum_values: list[Any] | None = None
    mock_pattern: str | None = None
    mock_generator: Callable | None = None
    mock_skip: bool = False
    description: str | None = None


class ValueGeneratorRegistry:
    """Registry for value generators with pattern matching and type fallback.

    The registry maintains generators in priority order:
    1. Field-specific overrides (registered per field name)
    2. Custom patterns (registered regex patterns)
    3. Default patterns (built-in field name patterns)
    4. Type generators (based on Python type)

    Example:
        >>> registry = ValueGeneratorRegistry(seed=42)
        >>>
        >>> # Generate with pattern detection
        >>> meta = FieldMeta(name="email", type_name="str")
        >>> value = registry.generate(meta)  # Uses email pattern
        >>>
        >>> # Register custom pattern
        >>> registry.register_pattern(
        ...     r"^policy_number$",
        ...     lambda f, m: f.bothify("POL-####-????").upper()
        ... )
        >>>
        >>> # Extend with domain-specific patterns
        >>> registry = registry.extend(InsuranceExtension())
    """

    def __init__(self, seed: int | None = None):
        """Initialize registry with optional seed for reproducibility.

        Args:
            seed: Random seed for reproducible generation
        """
        self._seed = seed
        self.faker = Faker()

        if seed is not None:
            Faker.seed(seed)
            self.faker.seed_instance(seed)
            random.seed(seed)

        # Field-specific overrides (highest priority)
        self._field_overrides: dict[str, GeneratorFunc] = {}

        # Custom patterns (registered by user)
        self._custom_patterns: list[tuple[re.Pattern, GeneratorFunc]] = []

        # Type generator overrides
        self._type_overrides: dict[str, GeneratorFunc] = {}

    def register_field_override(self, field_name: str, generator: GeneratorFunc) -> None:
        """Register an override for a specific field name.

        This has the highest priority and will always be used for the named field.

        Args:
            field_name: Exact field name to match
            generator: Generator function (receives Faker and FieldMeta)
        """
        self._field_overrides[field_name] = generator

    def register_pattern(self, pattern: str, generator: GeneratorFunc) -> None:
        """Register a custom pattern generator.

        Custom patterns are checked before default patterns.

        Args:
            pattern: Regex pattern to match field names
            generator: Generator function (receives Faker and FieldMeta)
        """
        compiled = re.compile(pattern, re.IGNORECASE)
        self._custom_patterns.append((compiled, generator))

    def register_type_generator(self, type_name: str, generator: GeneratorFunc) -> None:
        """Override or add a type-based generator.

        Args:
            type_name: Type name (e.g., "str", "uuid", "decimal")
            generator: Generator function (receives Faker and FieldMeta)
        """
        self._type_overrides[type_name.lower()] = generator

    def extend(self, extension: GeneratorExtension) -> ValueGeneratorRegistry:
        """Create a new registry extended with patterns from an extension.

        This returns a NEW registry with the extension's patterns added.
        The original registry is not modified.

        Args:
            extension: GeneratorExtension with additional patterns

        Returns:
            New ValueGeneratorRegistry with extension patterns
        """
        # Create new registry with same seed
        new_registry = ValueGeneratorRegistry(seed=self._seed)

        # Copy existing registrations
        new_registry._field_overrides = dict(self._field_overrides)
        new_registry._custom_patterns = list(self._custom_patterns)
        new_registry._type_overrides = dict(self._type_overrides)

        # Add extension's patterns
        for pattern, func in extension.get_patterns():
            new_registry.register_pattern(pattern, func)

        for type_name, func in extension.get_type_overrides().items():
            new_registry.register_type_generator(type_name, func)

        for field_name, func in extension.get_field_overrides().items():
            new_registry.register_field_override(field_name, func)

        return new_registry

    def generate(self, meta: FieldMeta) -> Any:
        """Generate a value for a field based on its metadata.

        Generation priority:
        1. mock_generator from Field() (if set)
        2. mock_pattern from Field() (if set)
        3. Field-specific override (if registered)
        4. Custom pattern match (if matches)
        5. Default pattern match (if matches)
        6. Type-based generator

        Args:
            meta: Field metadata

        Returns:
            Generated value appropriate for the field
        """
        # Skip if mock_skip is True
        if meta.mock_skip:
            return None

        # 1. Custom generator from Field()
        if meta.mock_generator is not None:
            return meta.mock_generator(self.faker)

        # 2. Explicit pattern from Field()
        if meta.mock_pattern:
            generator = get_named_pattern_generator(meta.mock_pattern)
            if generator:
                return generator(self.faker, meta)

        # 3. Field-specific override
        if meta.name in self._field_overrides:
            return self._field_overrides[meta.name](self.faker, meta)

        # 4. Custom pattern match
        for pattern, generator in self._custom_patterns:
            if pattern.search(meta.name):
                return generator(self.faker, meta)

        # 5. Default pattern match
        generator = get_pattern_generator(meta.name)
        if generator:
            return generator(self.faker, meta)

        # 6. Type-based generator
        # Check overrides first
        if meta.type_name.lower() in self._type_overrides:
            return self._type_overrides[meta.type_name.lower()](self.faker, meta)

        # Use default type generator
        type_gen = get_type_generator(meta.type_name)
        if type_gen:
            return type_gen(self.faker, meta)

        # Final fallback: return None for nullable, empty string otherwise
        if meta.is_nullable:
            return None
        return ""

    def reset_seed(self, seed: int) -> None:
        """Reset the random seed for reproducible generation.

        Args:
            seed: New random seed
        """
        self._seed = seed
        Faker.seed(seed)
        self.faker.seed_instance(seed)
        random.seed(seed)
