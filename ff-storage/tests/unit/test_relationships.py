"""
Unit tests for relationships module.

Tests cover:
- W3-W4: RelationshipConfig None checks
- W5: WeakKeyDictionary cache fix
- Relationship descriptor functionality
"""

import pytest
from typing import List


class TestRelationshipConfig:
    """Tests for RelationshipConfig validation (W3, W4)."""

    def test_get_foreign_key_column_with_owner_model(self):
        """FK column should be generated from owner_model for collections."""
        from ff_storage.relationships.config import RelationshipConfig

        config = RelationshipConfig(
            target_model="Post",
            is_collection=True,
            owner_model="Author",
        )
        assert config.get_foreign_key_column() == "author_id"

    def test_get_foreign_key_column_with_attribute_name(self):
        """FK column should be generated from attribute_name for references."""
        from ff_storage.relationships.config import RelationshipConfig

        config = RelationshipConfig(
            target_model="Author",
            is_collection=False,
            attribute_name="author",
        )
        assert config.get_foreign_key_column() == "author_id"

    def test_get_foreign_key_column_explicit(self):
        """Explicit FK should be returned unchanged."""
        from ff_storage.relationships.config import RelationshipConfig

        config = RelationshipConfig(
            target_model="Post",
            foreign_key="custom_author_fk",
        )
        assert config.get_foreign_key_column() == "custom_author_fk"

    def test_get_foreign_key_column_raises_without_owner_model(self):
        """Should raise if owner_model is None for collection."""
        from ff_storage.relationships.config import RelationshipConfig

        config = RelationshipConfig(
            target_model="Post",
            is_collection=True,
            owner_model=None,  # Explicitly None
        )
        with pytest.raises(ValueError, match="owner_model not set"):
            config.get_foreign_key_column()

    def test_get_foreign_key_column_raises_without_attribute_name(self):
        """Should raise if attribute_name is None for reference."""
        from ff_storage.relationships.config import RelationshipConfig

        config = RelationshipConfig(
            target_model="Author",
            is_collection=False,
            attribute_name=None,  # Explicitly None
        )
        with pytest.raises(ValueError, match="attribute_name not set"):
            config.get_foreign_key_column()

    def test_get_link_table_config_with_valid_models(self):
        """Link table config should be generated with valid models."""
        from ff_storage.relationships.config import RelationshipConfig

        config = RelationshipConfig(
            target_model="Tag",
            link_model="PostTag",
            owner_model="Post",
        )
        link_config = config.get_link_table_config()
        assert link_config is not None
        assert link_config["link_model"] == "PostTag"
        assert link_config["local_key"] == "post_id"
        assert link_config["remote_key"] == "tag_id"

    def test_get_link_table_config_raises_without_owner_model(self):
        """Should raise if owner_model is None for M2M."""
        from ff_storage.relationships.config import RelationshipConfig

        config = RelationshipConfig(
            target_model="Tag",
            link_model="PostTag",
            owner_model=None,  # Explicitly None
        )
        with pytest.raises(ValueError, match="owner_model not set"):
            config.get_link_table_config()

    def test_get_link_table_config_raises_without_target_model(self):
        """Should raise if target_model is empty for M2M."""
        from ff_storage.relationships.config import RelationshipConfig

        config = RelationshipConfig(
            target_model="",  # Empty
            link_model="PostTag",
            owner_model="Post",
        )
        with pytest.raises(ValueError, match="target_model not set"):
            config.get_link_table_config()

    def test_is_many_to_many(self):
        """is_many_to_many should check for link_model presence."""
        from ff_storage.relationships.config import RelationshipConfig

        m2m_config = RelationshipConfig(
            target_model="Tag",
            link_model="PostTag",
        )
        assert m2m_config.is_many_to_many() is True

        non_m2m_config = RelationshipConfig(
            target_model="Author",
        )
        assert non_m2m_config.is_many_to_many() is False


class TestRelationshipDescriptorCache:
    """Tests for Relationship descriptor cache fix (W5)."""

    def test_cache_uses_instance_dict(self):
        """Cache should store data in instance __dict__, not WeakKeyDictionary."""
        from ff_storage.relationships.descriptor import Relationship
        from ff_storage.relationships.registry import RelationshipRegistry

        # Clear registry
        RelationshipRegistry.clear()

        # Create a test class with relationship
        # __set_name__ is automatically called by Python during class creation
        class TestModel:
            __annotations__ = {"related": List["OtherModel"]}  # noqa: F821 - forward reference for test
            related = Relationship(back_populates="parent")

        # Get the descriptor directly from __dict__ to avoid triggering __get__
        descriptor = TestModel.__dict__["related"]

        # Create instance and set value
        instance = TestModel()

        test_value = ["item1", "item2"]
        descriptor.__set__(instance, test_value)

        # Verify it's in __dict__, not WeakKeyDictionary
        assert "_rel_cache_related" in instance.__dict__
        assert instance.__dict__["_rel_cache_related"] == test_value

        # Verify __get__ retrieves from __dict__
        retrieved = descriptor.__get__(instance, TestModel)
        assert retrieved == test_value

    def test_cache_survives_without_external_references(self):
        """Cached data should survive even without external references.

        This tests that we don't use WeakKeyDictionary which could lose data
        when there are no external references to the value.
        """
        from ff_storage.relationships.descriptor import Relationship
        from ff_storage.relationships.registry import RelationshipRegistry

        RelationshipRegistry.clear()

        class TestModel:
            __annotations__ = {"items": List["Item"]}  # noqa: F821 - forward reference for test
            items = Relationship()

        descriptor = TestModel.__dict__["items"]

        instance = TestModel()

        # Set a value
        descriptor.__set__(instance, ["value"])

        # Get it back
        result = descriptor.__get__(instance, TestModel)
        assert result == ["value"]

    def test_empty_collection_default(self):
        """Should return empty list for collection relationships with no cached data."""
        from ff_storage.relationships.descriptor import Relationship
        from ff_storage.relationships.registry import RelationshipRegistry

        RelationshipRegistry.clear()

        class TestModel:
            __annotations__ = {"items": List["Item"]}  # noqa: F821 - forward reference for test
            items = Relationship()

        descriptor = TestModel.__dict__["items"]

        instance = TestModel()

        # Should return empty list, not None
        result = descriptor.__get__(instance, TestModel)
        assert result == []

    def test_none_default_for_single_reference(self):
        """Should return None for single reference relationships with no cached data."""
        from ff_storage.relationships.descriptor import Relationship
        from ff_storage.relationships.registry import RelationshipRegistry

        RelationshipRegistry.clear()

        class TestModel:
            __annotations__ = {"parent": "ParentModel"}
            parent = Relationship()

        descriptor = TestModel.__dict__["parent"]

        instance = TestModel()

        # Should return None for non-collection
        result = descriptor.__get__(instance, TestModel)
        assert result is None


class TestRelationshipRegistry:
    """Tests for RelationshipRegistry."""

    def test_register_and_get_relationship(self):
        """Should be able to register and retrieve relationships."""
        from ff_storage.relationships.config import RelationshipConfig
        from ff_storage.relationships.registry import RelationshipRegistry

        RelationshipRegistry.clear()

        config = RelationshipConfig(
            target_model="Post",
            back_populates="author",
        )
        RelationshipRegistry.register("Author", "posts", config)

        retrieved = RelationshipRegistry.get_relationship("Author", "posts")
        assert retrieved is config

    def test_get_all_relationships(self):
        """Should return all relationships for a model."""
        from ff_storage.relationships.config import RelationshipConfig
        from ff_storage.relationships.registry import RelationshipRegistry

        RelationshipRegistry.clear()

        config1 = RelationshipConfig(target_model="Post")
        config2 = RelationshipConfig(target_model="Comment")

        RelationshipRegistry.register("Author", "posts", config1)
        RelationshipRegistry.register("Author", "comments", config2)

        all_rels = RelationshipRegistry.get_relationships("Author")
        assert len(all_rels) == 2
        assert "posts" in all_rels
        assert "comments" in all_rels

    def test_register_and_resolve_model(self):
        """Should be able to register and resolve model classes."""
        from ff_storage.relationships.registry import RelationshipRegistry

        RelationshipRegistry.clear()

        class TestModel:
            pass

        RelationshipRegistry.register_model("TestModel", TestModel)
        resolved = RelationshipRegistry.resolve_model("TestModel")
        assert resolved is TestModel

    def test_resolve_unknown_model_returns_none(self):
        """Should return None for unknown model names."""
        from ff_storage.relationships.registry import RelationshipRegistry

        RelationshipRegistry.clear()

        resolved = RelationshipRegistry.resolve_model("UnknownModel")
        assert resolved is None
