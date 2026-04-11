"""Extension system for domain-specific mock generators.

This module provides the GeneratorExtension base class that allows
projects to add custom patterns and generators.

Example:
    >>> from ff_storage.mock import GeneratorExtension, ValueGeneratorRegistry
    >>> from decimal import Decimal
    >>>
    >>> class InsuranceExtension(GeneratorExtension):
    ...     NAME_PATTERNS = [
    ...         (r"^policy_number$", lambda f, m: f.bothify("POL-####-????").upper()),
    ...         (r"^premium$", lambda f, m: Decimal(f.pyfloat(100, 1000000)).quantize(Decimal("0.01"))),
    ...     ]
    ...
    ...     FIELD_OVERRIDES = {
    ...         "ixr_number": lambda f, m: f"IXR{f.random_int(1, 999999):06d}-R0",
    ...     }
    >>>
    >>> registry = ValueGeneratorRegistry(seed=42).extend(InsuranceExtension())
    >>> policy = Policy.create_mock(registry=registry)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from faker import Faker

    from .generators.registry import FieldMeta

# Type alias for generator functions
GeneratorFunc = Callable[["Faker", "FieldMeta"], Any]


class GeneratorExtension:
    """Base class for domain-specific generator extensions.

    Subclass this to add custom patterns and generators for your domain.

    Class Attributes:
        NAME_PATTERNS: List of (regex_pattern, generator_function) tuples.
            Patterns are matched against field names.
        TYPE_OVERRIDES: Dict mapping type names to generator functions.
            Overrides default type generators.
        FIELD_OVERRIDES: Dict mapping exact field names to generator functions.
            Highest priority - always used for matching field names.

    Example:
        >>> class MyExtension(GeneratorExtension):
        ...     NAME_PATTERNS = [
        ...         (r"^order_id$", lambda f, m: f.bothify("ORD-########")),
        ...         (r"^tracking_number$", lambda f, m: f.bothify("TRK??########")),
        ...     ]
        ...
        ...     FIELD_OVERRIDES = {
        ...         "merchant_id": lambda f, m: f"MER-{f.random_int(1000, 9999)}",
        ...     }
    """

    # Override in subclasses
    NAME_PATTERNS: list[tuple[str, GeneratorFunc]] = []
    TYPE_OVERRIDES: dict[str, GeneratorFunc] = {}
    FIELD_OVERRIDES: dict[str, GeneratorFunc] = {}

    def get_patterns(self) -> list[tuple[str, GeneratorFunc]]:
        """Return name patterns to register.

        Override this method if you need dynamic pattern generation.

        Returns:
            List of (regex_pattern, generator_function) tuples
        """
        return self.NAME_PATTERNS

    def get_type_overrides(self) -> dict[str, GeneratorFunc]:
        """Return type generator overrides.

        Override this method if you need dynamic type overrides.

        Returns:
            Dict mapping type names to generator functions
        """
        return self.TYPE_OVERRIDES

    def get_field_overrides(self) -> dict[str, GeneratorFunc]:
        """Return field-specific overrides.

        Override this method if you need dynamic field overrides.

        Returns:
            Dict mapping exact field names to generator functions
        """
        return self.FIELD_OVERRIDES


# Example extension for demonstration
class ExampleExtension(GeneratorExtension):
    """Example extension showing how to add custom patterns.

    This is provided as a reference - create your own extension
    for your domain.
    """

    NAME_PATTERNS = [
        # Order patterns
        (r"^order_id$|^order_number$", lambda f, m: f.bothify("ORD-########")),
        (r"^tracking_number$", lambda f, m: f.bothify("TRK??########").upper()),
        # Product patterns
        (r"^product_code$", lambda f, m: f.bothify("???-###").upper()),
        (r"^barcode$|^upc$", lambda f, m: f.ean13()),
    ]
