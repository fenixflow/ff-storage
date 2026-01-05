"""Global registry for model relationships.

This module provides a global registry for storing and resolving relationships
between models without requiring circular imports.
"""

from __future__ import annotations

import threading
import warnings
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from .config import RelationshipConfig


class RelationshipRegistry:
    """
    Global registry mapping model names to their relationships.

    This singleton registry allows relationships to be resolved across modules
    without circular import issues. It stores:
    - Model name -> relationships mapping
    - Model name -> class mapping (for resolving string references)

    Thread Safety:
        The registry uses RLock to protect write operations during model registration.
        Read operations (get_relationship, resolve_model) are lock-free since Python
        dict reads are atomic. RLock is used instead of Lock to allow re-entrant
        registration during nested class definitions.

    Example:
        # Registration happens automatically via Relationship descriptor
        class Author(PydanticModel):
            posts: List["Post"] = Relationship(back_populates="author")

        # Later, resolve the relationship
        config = RelationshipRegistry.get_relationship("Author", "posts")
        target_class = RelationshipRegistry.resolve_model("Post")
    """

    _registry: Dict[str, Dict[str, "RelationshipConfig"]] = {}
    _models: Dict[str, type] = {}
    _lock: threading.RLock = threading.RLock()
    _validated: bool = False

    @classmethod
    def register(cls, model_name: str, attr_name: str, config: "RelationshipConfig") -> None:
        """
        Register a relationship for a model.

        Thread-safe: Uses RLock to protect concurrent writes.

        Args:
            model_name: Name of the model class that owns the relationship
            attr_name: Name of the relationship attribute
            config: RelationshipConfig with relationship metadata
        """
        with cls._lock:
            if model_name not in cls._registry:
                cls._registry[model_name] = {}
            cls._registry[model_name][attr_name] = config

    @classmethod
    def register_model(cls, model_name: str, model_class: type) -> None:
        """
        Register a model class for later resolution.

        This should be called when a model class is defined to allow
        string references to be resolved later.

        Thread-safe: Uses RLock to protect concurrent writes.

        Args:
            model_name: Name of the model class
            model_class: The actual model class object
        """
        with cls._lock:
            cls._models[model_name] = model_class

    @classmethod
    def get_relationships(cls, model_name: str) -> Dict[str, "RelationshipConfig"]:
        """
        Get all relationships for a model.

        Args:
            model_name: Name of the model class

        Returns:
            Dict mapping attribute name -> RelationshipConfig
        """
        return cls._registry.get(model_name, {})

    @classmethod
    def get_relationship(cls, model_name: str, attr_name: str) -> "RelationshipConfig | None":
        """
        Get a specific relationship configuration.

        Args:
            model_name: Name of the model class
            attr_name: Name of the relationship attribute

        Returns:
            RelationshipConfig or None if not found
        """
        return cls._registry.get(model_name, {}).get(attr_name)

    @classmethod
    def resolve_model(cls, model_name: str) -> type | None:
        """
        Resolve a model name to its class.

        Args:
            model_name: Name of the model class

        Returns:
            The model class or None if not registered
        """
        return cls._models.get(model_name)

    @classmethod
    def get_all_models(cls) -> Dict[str, type]:
        """
        Get all registered models.

        Returns:
            Dict mapping model name -> class
        """
        return cls._models.copy()

    @classmethod
    def clear(cls) -> None:
        """
        Clear the registry.

        Useful for testing to reset state between tests.
        Thread-safe: Uses RLock to protect concurrent access.
        """
        with cls._lock:
            cls._registry.clear()
            cls._models.clear()
            cls._validated = False

    @classmethod
    def ensure_validated(cls) -> None:
        """
        Validate all relationships once, on first usage.

        This method is designed to be called before the first query execution.
        It validates that all back_populates references are valid and emits
        warnings for any invalid configurations.

        Thread-safe: Uses double-checked locking pattern.
        """
        if cls._validated:
            return

        with cls._lock:
            if cls._validated:
                return

            errors = cls.validate_back_populates()
            if errors:
                for err in errors:
                    warnings.warn(f"Relationship configuration error: {err}", UserWarning)

            cls._validated = True

    @classmethod
    def validate_back_populates(cls) -> list[str]:
        """
        Validate that all back_populates references are valid.

        This should be called after all models are defined to verify
        that back_populates references point to valid relationships.

        Returns:
            List of error messages (empty if all valid)
        """
        errors = []

        for model_name, relationships in cls._registry.items():
            for attr_name, config in relationships.items():
                if config.back_populates:
                    # Check that target model exists
                    target_model = cls.resolve_model(config.target_model)
                    if not target_model:
                        errors.append(
                            f"{model_name}.{attr_name}: target model "
                            f"'{config.target_model}' not found"
                        )
                        continue

                    # Check that back_populates attribute exists
                    target_rel = cls.get_relationship(config.target_model, config.back_populates)
                    if not target_rel:
                        errors.append(
                            f"{model_name}.{attr_name}: back_populates "
                            f"'{config.back_populates}' not found on "
                            f"'{config.target_model}'"
                        )

        return errors
