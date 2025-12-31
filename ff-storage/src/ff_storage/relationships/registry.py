"""Global registry for model relationships.

This module provides a global registry for storing and resolving relationships
between models without requiring circular imports.
"""

from __future__ import annotations

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
        The registry uses class-level dicts which are thread-safe for reads.
        Writes happen during class definition time, which is typically single-threaded.

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

    @classmethod
    def register(cls, model_name: str, attr_name: str, config: "RelationshipConfig") -> None:
        """
        Register a relationship for a model.

        Args:
            model_name: Name of the model class that owns the relationship
            attr_name: Name of the relationship attribute
            config: RelationshipConfig with relationship metadata
        """
        if model_name not in cls._registry:
            cls._registry[model_name] = {}
        cls._registry[model_name][attr_name] = config

    @classmethod
    def register_model(cls, model_name: str, model_class: type) -> None:
        """
        Register a model class for later resolution.

        This should be called when a model class is defined to allow
        string references to be resolved later.

        Args:
            model_name: Name of the model class
            model_class: The actual model class object
        """
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
        """
        cls._registry.clear()
        cls._models.clear()

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
