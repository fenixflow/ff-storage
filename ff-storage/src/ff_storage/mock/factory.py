"""Mock data factory for Pydantic models.

This module provides the MockFactory class that generates mock instances
of PydanticModel subclasses using the Field() metadata as the source of truth.

Example:
    >>> from ff_storage.mock import MockFactory
    >>> from myapp.models import User
    >>>
    >>> factory = MockFactory(seed=42)
    >>> user = factory.create(User)
    >>> users = factory.create_batch(User, 100)
"""

from __future__ import annotations

import enum
import random
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Iterator, Optional, TypeVar, get_args, get_origin
from uuid import UUID

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from .generators import FieldMeta, ValueGeneratorRegistry

if TYPE_CHECKING:
    pass

T = TypeVar("T", bound=BaseModel)


class MockFactory:
    """Factory for creating mock instances of Pydantic models.

    Uses Field() metadata as the source of truth for generation rules:
    - max_length, ge, le, gt, lt → value constraints
    - db_precision, db_scale → decimal precision
    - mock_pattern → explicit pattern generator
    - mock_generator → custom generator function
    - mock_skip → skip field (must provide via overrides)

    Example:
        >>> factory = MockFactory(seed=42)
        >>>
        >>> # Create a single mock
        >>> user = factory.create(User)
        >>>
        >>> # Create with overrides
        >>> admin = factory.create(User, overrides={"role": "admin"})
        >>>
        >>> # Create batch
        >>> users = factory.create_batch(User, 100)
        >>>
        >>> # Streaming for large datasets
        >>> for user in factory.create_stream(User, 10000):
        ...     process(user)
    """

    def __init__(
        self,
        seed: int | None = None,
        registry: ValueGeneratorRegistry | None = None,
    ):
        """Initialize the factory.

        Args:
            seed: Random seed for reproducible generation
            registry: Custom ValueGeneratorRegistry. If None, creates default.
        """
        self._seed = seed
        self._registry = registry or ValueGeneratorRegistry(seed=seed)

    @property
    def registry(self) -> ValueGeneratorRegistry:
        """Access the underlying value generator registry."""
        return self._registry

    def create(
        self,
        model_class: type[T],
        *,
        overrides: dict[str, Any] | None = None,
        cascade: bool = False,
        cascade_depth: int = 3,
    ) -> T:
        """Create a single mock instance of a Pydantic model.

        Args:
            model_class: The Pydantic model class to instantiate
            overrides: Field values to override (highest priority)
            cascade: If True, also create related models via relationships
            cascade_depth: Maximum depth for relationship cascading

        Returns:
            A new instance of model_class with generated values

        Example:
            >>> user = factory.create(User)
            >>> user.email  # Generated email
            'john.doe@example.com'

            >>> admin = factory.create(User, overrides={"role": "admin"})
            >>> admin.role
            'admin'
        """
        overrides = overrides or {}

        # Extract field metadata and generate values
        field_values = {}
        for field_name, field_info in model_class.model_fields.items():
            # Check if override provided
            if field_name in overrides:
                field_values[field_name] = overrides[field_name]
                continue

            # Extract metadata and generate value
            meta = self._extract_field_meta(field_name, field_info)

            # Skip if mock_skip is True
            if meta.mock_skip:
                # Must be provided via overrides or be nullable
                if meta.is_nullable:
                    field_values[field_name] = None
                continue

            # Generate value using registry
            value = self._registry.generate(meta)
            field_values[field_name] = value

        # Handle relationship cascading if enabled
        if cascade:
            field_values = self._cascade_relationships(
                model_class,
                field_values,
                depth=cascade_depth,
            )

        # Create instance
        return model_class(**field_values)

    def create_batch(
        self,
        model_class: type[T],
        count: int,
        *,
        overrides: dict[str, Any] | None = None,
        cascade: bool = False,
        cascade_depth: int = 3,
    ) -> list[T]:
        """Create multiple mock instances.

        Args:
            model_class: The Pydantic model class to instantiate
            count: Number of instances to create
            overrides: Field values to override (applied to all instances)
            cascade: If True, also create related models via relationships
            cascade_depth: Maximum depth for relationship cascading

        Returns:
            List of mock instances

        Example:
            >>> users = factory.create_batch(User, 100)
            >>> len(users)
            100
        """
        return [
            self.create(
                model_class,
                overrides=overrides,
                cascade=cascade,
                cascade_depth=cascade_depth,
            )
            for _ in range(count)
        ]

    def create_stream(
        self,
        model_class: type[T],
        count: int,
        *,
        overrides: dict[str, Any] | None = None,
        cascade: bool = False,
        cascade_depth: int = 3,
    ) -> Iterator[T]:
        """Create mock instances as a generator for memory-efficient batch processing.

        Args:
            model_class: The Pydantic model class to instantiate
            count: Number of instances to generate
            overrides: Field values to override (applied to all instances)
            cascade: If True, also create related models via relationships
            cascade_depth: Maximum depth for relationship cascading

        Yields:
            Mock instances one at a time

        Example:
            >>> for user in factory.create_stream(User, 10000):
            ...     await repository.create(user)
        """
        for _ in range(count):
            yield self.create(
                model_class,
                overrides=overrides,
                cascade=cascade,
                cascade_depth=cascade_depth,
            )

    def _extract_field_meta(self, field_name: str, field_info: FieldInfo) -> FieldMeta:
        """Extract FieldMeta from Pydantic FieldInfo.

        Args:
            field_name: Name of the field
            field_info: Pydantic FieldInfo object

        Returns:
            FieldMeta with all relevant metadata for generation
        """
        # Get type annotation
        field_type = field_info.annotation

        # Determine type name and extract inner type for Optional
        type_name, is_nullable, inner_type = self._analyze_type(field_type)

        # Check if enum
        enum_class = None
        enum_values = None
        if inner_type and isinstance(inner_type, type) and issubclass(inner_type, enum.Enum):
            enum_class = inner_type
            enum_values = list(inner_type)
            type_name = "enum"

        # Get json_schema_extra metadata
        extra = field_info.json_schema_extra or {}

        # Extract constraints from Pydantic metadata
        ge = self._get_constraint(field_info, "ge")
        le = self._get_constraint(field_info, "le")
        gt = self._get_constraint(field_info, "gt")
        lt = self._get_constraint(field_info, "lt")
        max_length = self._get_constraint(field_info, "max_length") or extra.get("max_length")
        min_length = self._get_constraint(field_info, "min_length") or extra.get("min_length")

        # Extract decimal precision/scale from db metadata
        precision = extra.get("db_precision")
        scale = extra.get("db_scale")

        # Extract mock-specific metadata
        mock_pattern = extra.get("mock_pattern")
        mock_generator = extra.get("mock_generator")
        mock_skip = extra.get("mock_skip", False)

        # Determine if required
        is_required = field_info.is_required() if hasattr(field_info, "is_required") else True
        if field_info.default is not None or field_info.default_factory is not None:
            is_required = False

        return FieldMeta(
            name=field_name,
            type_name=type_name,
            python_type=inner_type or field_type,
            is_nullable=is_nullable,
            is_required=is_required,
            max_length=max_length,
            min_length=min_length,
            ge=ge,
            le=le,
            gt=gt,
            lt=lt,
            precision=precision,
            scale=scale,
            enum_class=enum_class,
            enum_values=enum_values,
            mock_pattern=mock_pattern,
            mock_generator=mock_generator,
            mock_skip=mock_skip,
            description=field_info.description,
        )

    def _analyze_type(self, field_type: type) -> tuple[str, bool, Optional[type]]:
        """Analyze a type annotation to get type name, nullability, and inner type.

        Args:
            field_type: The type annotation to analyze

        Returns:
            Tuple of (type_name, is_nullable, inner_type)
        """
        origin = get_origin(field_type)
        args = get_args(field_type)

        # Check for Optional (Union[X, None])
        is_nullable = False
        inner_type = field_type

        if origin is type(None):
            return "none", True, type(None)

        # Handle Union types (including Optional)
        if str(origin) == "typing.Union" or origin is type(None):
            if len(args) == 2 and type(None) in args:
                is_nullable = True
                inner_type = args[0] if args[1] is type(None) else args[1]
                # Recursively analyze inner type
                type_name, _, _ = self._analyze_type(inner_type)
                return type_name, is_nullable, inner_type

        # Handle list types
        if origin is list:
            return "list", is_nullable, inner_type

        # Handle dict types
        if origin is dict:
            return "dict", is_nullable, inner_type

        # Map Python types to type names
        type_mapping = {
            str: "str",
            int: "int",
            float: "float",
            bool: "bool",
            bytes: "bytes",
            UUID: "uuid",
            datetime: "datetime",
            date: "date",
            Decimal: "decimal",
        }

        if inner_type in type_mapping:
            return type_mapping[inner_type], is_nullable, inner_type

        # Check if it's a subclass of known types
        if isinstance(inner_type, type):
            for base_type, type_name in type_mapping.items():
                if issubclass(inner_type, base_type):
                    return type_name, is_nullable, inner_type

        # Check for enum
        if isinstance(inner_type, type) and issubclass(inner_type, enum.Enum):
            return "enum", is_nullable, inner_type

        # Default to string for unknown types
        return "str", is_nullable, inner_type

    def _get_constraint(self, field_info: FieldInfo, name: str) -> Any:
        """Extract a constraint value from Pydantic FieldInfo.

        Args:
            field_info: Pydantic FieldInfo object
            name: Constraint name (ge, le, gt, lt, max_length, etc.)

        Returns:
            Constraint value or None
        """
        # Check metadata for constraints (Pydantic v2)
        if field_info.metadata:
            for meta in field_info.metadata:
                if hasattr(meta, name):
                    return getattr(meta, name)
                # Also check for Annotated constraints
                if hasattr(meta, name.upper()):
                    return getattr(meta, name.upper())

        # Check json_schema_extra
        extra = field_info.json_schema_extra or {}
        if name in extra:
            return extra[name]

        return None

    def _cascade_relationships(
        self,
        model_class: type[T],
        field_values: dict[str, Any],
        depth: int,
    ) -> dict[str, Any]:
        """Handle relationship cascading.

        Creates related models when cascade=True.

        Args:
            model_class: The model being created
            field_values: Current field values
            depth: Remaining cascade depth

        Returns:
            Updated field_values with cascaded relationships
        """
        if depth <= 0:
            return field_values

        try:
            from ..relationships.registry import RelationshipRegistry

            # Get relationships for this model
            relationships = RelationshipRegistry.get_relationships_for_model(model_class)

            for rel_name, rel_info in relationships.items():
                # Skip if already provided in field_values
                if rel_name in field_values:
                    continue

                # Get the related model class
                related_model = rel_info.get("related_model")
                if not related_model:
                    continue

                # For one-to-many, create empty list (related objects reference this one)
                # For many-to-one, we'd need to create the parent first
                # For now, just populate FK fields with UUIDs
                if rel_info.get("relationship_type") == "many_to_one":
                    fk_field = rel_info.get("foreign_key_field")
                    if fk_field and fk_field not in field_values:
                        # Create a related instance and use its ID
                        related_instance = self.create(
                            related_model,
                            cascade=False,  # Don't recursively cascade
                        )
                        field_values[fk_field] = related_instance.id
        except ImportError:
            # Relationships module not available
            pass
        except Exception:
            # Silently handle relationship cascade errors
            pass

        return field_values

    def reset_seed(self, seed: int) -> None:
        """Reset the random seed for reproducible generation.

        Args:
            seed: New random seed
        """
        self._seed = seed
        self._registry.reset_seed(seed)
        random.seed(seed)
