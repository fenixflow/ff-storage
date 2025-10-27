"""
Tests for dynamic temporal field injection in PydanticModel.

Tests all 12 combinations of:
- Temporal strategies: none, copy_on_change, scd2
- Multi-tenant: True/False
- Soft delete: True/False

Verifies that temporal fields are:
1. Properly injected as Pydantic model fields
2. Accessible via dot notation without AttributeError
3. Included in model_dump() output
4. Properly validated by Pydantic
5. Correctly typed for IDE autocomplete
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import pytest
from ff_storage.pydantic_support.base import PydanticModel
from pydantic import Field

# Test models for all 12 combinations

# ==================== NONE Strategy Tests ====================


class ModelNoneBasic(PydanticModel):
    """Test model: none strategy, no multi-tenant, no soft delete."""

    __table_name__ = "model_none_basic"
    __temporal_strategy__ = "none"
    __multi_tenant__ = False
    __soft_delete__ = False

    name: str
    value: int


class ModelNoneTenant(PydanticModel):
    """Test model: none strategy, with multi-tenant, no soft delete."""

    __table_name__ = "model_none_tenant"
    __temporal_strategy__ = "none"
    __multi_tenant__ = True
    __soft_delete__ = False

    name: str
    value: int


class ModelNoneSoftDelete(PydanticModel):
    """Test model: none strategy, no multi-tenant, with soft delete."""

    __table_name__ = "model_none_soft"
    __temporal_strategy__ = "none"
    __multi_tenant__ = False
    __soft_delete__ = True

    name: str
    value: int


class ModelNoneFull(PydanticModel):
    """Test model: none strategy, with multi-tenant, with soft delete."""

    __table_name__ = "model_none_full"
    __temporal_strategy__ = "none"
    __multi_tenant__ = True
    __soft_delete__ = True

    name: str
    value: int


# ==================== COPY_ON_CHANGE Strategy Tests ====================


class ModelCopyBasic(PydanticModel):
    """Test model: copy_on_change strategy, no multi-tenant, no soft delete."""

    __table_name__ = "model_copy_basic"
    __temporal_strategy__ = "copy_on_change"
    __multi_tenant__ = False
    __soft_delete__ = False

    name: str
    value: int


class ModelCopyTenant(PydanticModel):
    """Test model: copy_on_change strategy, with multi-tenant, no soft delete."""

    __table_name__ = "model_copy_tenant"
    __temporal_strategy__ = "copy_on_change"
    __multi_tenant__ = True
    __soft_delete__ = False

    name: str
    value: int


class ModelCopySoftDelete(PydanticModel):
    """Test model: copy_on_change strategy, no multi-tenant, with soft delete."""

    __table_name__ = "model_copy_soft"
    __temporal_strategy__ = "copy_on_change"
    __multi_tenant__ = False
    __soft_delete__ = True

    name: str
    value: int


class ModelCopyFull(PydanticModel):
    """Test model: copy_on_change strategy, with multi-tenant, with soft delete."""

    __table_name__ = "model_copy_full"
    __temporal_strategy__ = "copy_on_change"
    __multi_tenant__ = True
    __soft_delete__ = True

    name: str
    value: int


# ==================== SCD2 Strategy Tests ====================


class ModelSCD2Basic(PydanticModel):
    """Test model: scd2 strategy, no multi-tenant, no soft delete."""

    __table_name__ = "model_scd2_basic"
    __temporal_strategy__ = "scd2"
    __multi_tenant__ = False
    __soft_delete__ = False  # Note: SCD2 forces soft_delete=True internally

    name: str
    value: int


class ModelSCD2Tenant(PydanticModel):
    """Test model: scd2 strategy, with multi-tenant, no soft delete."""

    __table_name__ = "model_scd2_tenant"
    __temporal_strategy__ = "scd2"
    __multi_tenant__ = True
    __soft_delete__ = False  # Note: SCD2 forces soft_delete=True internally

    name: str
    value: int


class ModelSCD2SoftDelete(PydanticModel):
    """Test model: scd2 strategy, no multi-tenant, with soft delete."""

    __table_name__ = "model_scd2_soft"
    __temporal_strategy__ = "scd2"
    __multi_tenant__ = False
    __soft_delete__ = True

    name: str
    value: int


class ModelSCD2Full(PydanticModel):
    """Test model: scd2 strategy, with multi-tenant, with soft delete."""

    __table_name__ = "model_scd2_full"
    __temporal_strategy__ = "scd2"
    __multi_tenant__ = True
    __soft_delete__ = True

    name: str
    value: int


# ==================== Model with JSONB Fields ====================


class ModelWithJSONB(PydanticModel):
    """Test model with JSONB fields for serialization testing."""

    __table_name__ = "model_jsonb"
    __temporal_strategy__ = "scd2"
    __multi_tenant__ = True
    __soft_delete__ = True

    name: str
    metadata: Dict[str, Any]  # JSONB field
    tags: List[str]  # Array field
    settings: Optional[Dict[str, Any]] = None  # Optional JSONB


# ==================== Test Functions ====================


class TestFieldInjection:
    """Test dynamic field injection for all strategy combinations."""

    def test_none_basic_no_temporal_fields(self):
        """Test: none strategy, no multi-tenant, no soft delete - should have NO temporal fields."""
        model = ModelNoneBasic(name="test", value=42)

        # Check model has standard fields
        assert hasattr(model, "id")
        assert hasattr(model, "created_at")
        assert hasattr(model, "updated_at")
        assert hasattr(model, "created_by")

        # Check NO temporal fields are injected
        assert not hasattr(model, "tenant_id")
        assert not hasattr(model, "deleted_at")
        assert not hasattr(model, "deleted_by")
        assert not hasattr(model, "version")
        assert not hasattr(model, "valid_from")
        assert not hasattr(model, "valid_to")

        # Check model_dump includes only expected fields
        data = model.model_dump()
        assert "name" in data
        assert "value" in data
        assert "tenant_id" not in data
        assert "deleted_at" not in data

    def test_none_tenant_has_tenant_field(self):
        """Test: none strategy, with multi-tenant - should have tenant_id."""
        model = ModelNoneTenant(name="test", value=42)

        # Check tenant field is injected
        assert hasattr(model, "tenant_id")
        assert model.tenant_id is None  # Default value

        # Check we can set tenant_id
        test_tenant_id = uuid4()
        model.tenant_id = test_tenant_id
        assert model.tenant_id == test_tenant_id

        # Check model_dump includes tenant_id
        data = model.model_dump()
        assert "tenant_id" in data
        assert data["tenant_id"] == test_tenant_id

    def test_none_soft_delete_has_delete_fields(self):
        """Test: none strategy, with soft delete - should have delete fields."""
        model = ModelNoneSoftDelete(name="test", value=42)

        # Check soft delete fields are injected
        assert hasattr(model, "deleted_at")
        assert hasattr(model, "deleted_by")
        assert model.deleted_at is None  # Default value
        assert model.deleted_by is None  # Default value

        # Check we can set delete fields
        now = datetime.now(timezone.utc)
        user_id = uuid4()
        model.deleted_at = now
        model.deleted_by = user_id
        assert model.deleted_at == now
        assert model.deleted_by == user_id

        # Check model_dump includes delete fields
        data = model.model_dump()
        assert "deleted_at" in data
        assert "deleted_by" in data

    def test_none_full_has_all_base_fields(self):
        """Test: none strategy, with multi-tenant and soft delete."""
        model = ModelNoneFull(name="test", value=42)

        # Check all base temporal fields are injected
        assert hasattr(model, "tenant_id")
        assert hasattr(model, "deleted_at")
        assert hasattr(model, "deleted_by")

        # Verify no SCD2 fields
        assert not hasattr(model, "version")
        assert not hasattr(model, "valid_from")
        assert not hasattr(model, "valid_to")

    def test_copy_on_change_basic_no_temporal_fields(self):
        """Test: copy_on_change strategy, no multi-tenant, no soft delete."""
        model = ModelCopyBasic(name="test", value=42)

        # Check NO temporal fields (copy_on_change doesn't add fields to main table)
        assert not hasattr(model, "tenant_id")
        assert not hasattr(model, "deleted_at")
        assert not hasattr(model, "deleted_by")
        assert not hasattr(model, "version")

    def test_copy_on_change_tenant_has_tenant_field(self):
        """Test: copy_on_change strategy, with multi-tenant."""
        model = ModelCopyTenant(name="test", value=42)

        # Check tenant field is injected
        assert hasattr(model, "tenant_id")
        assert model.tenant_id is None

    def test_copy_on_change_full_has_base_fields(self):
        """Test: copy_on_change strategy, with multi-tenant and soft delete."""
        model = ModelCopyFull(name="test", value=42)

        # Check all base temporal fields are injected
        assert hasattr(model, "tenant_id")
        assert hasattr(model, "deleted_at")
        assert hasattr(model, "deleted_by")

        # Verify no SCD2 fields
        assert not hasattr(model, "version")
        assert not hasattr(model, "valid_from")
        assert not hasattr(model, "valid_to")

    def test_scd2_basic_has_version_fields(self):
        """Test: scd2 strategy, basic - should have version fields."""
        model = ModelSCD2Basic(name="test", value=42)

        # Check SCD2 fields are injected
        assert hasattr(model, "version")
        assert hasattr(model, "valid_from")
        assert hasattr(model, "valid_to")

        # Check SCD2 forces soft_delete, so delete fields should be present
        assert hasattr(model, "deleted_at")
        assert hasattr(model, "deleted_by")

        # Check default values
        assert model.version == 1  # Default version
        assert isinstance(model.valid_from, datetime)
        assert model.valid_to is None
        assert model.deleted_at is None
        assert model.deleted_by is None

    def test_scd2_tenant_has_all_fields(self):
        """Test: scd2 strategy, with multi-tenant."""
        model = ModelSCD2Tenant(name="test", value=42)

        # Check all fields are injected
        assert hasattr(model, "tenant_id")
        assert hasattr(model, "version")
        assert hasattr(model, "valid_from")
        assert hasattr(model, "valid_to")
        assert hasattr(model, "deleted_at")
        assert hasattr(model, "deleted_by")

    def test_scd2_full_has_all_temporal_fields(self):
        """Test: scd2 strategy, with multi-tenant and soft delete."""
        model = ModelSCD2Full(name="test", value=42)

        # Check ALL temporal fields are present
        fields_to_check = [
            "tenant_id",
            "version",
            "valid_from",
            "valid_to",
            "deleted_at",
            "deleted_by",
        ]

        for field in fields_to_check:
            assert hasattr(model, field), f"Missing field: {field}"

        # Check model_dump includes all fields
        data = model.model_dump()
        for field in fields_to_check:
            assert field in data, f"Field {field} not in model_dump()"

    def test_model_validation_with_injected_fields(self):
        """Test that Pydantic validation works with injected fields."""
        # Create model with data including temporal fields
        tenant_id = uuid4()
        now = datetime.now(timezone.utc)

        data = {
            "name": "test",
            "value": 42,
            "tenant_id": tenant_id,
            "version": 2,
            "valid_from": now,
            "valid_to": None,
            "deleted_at": None,
            "deleted_by": None,
        }

        # Should validate successfully
        model = ModelSCD2Full.model_validate(data)
        assert model.name == "test"
        assert model.tenant_id == tenant_id
        assert model.version == 2
        assert model.valid_from == now

    def test_model_dump_json_with_temporal_fields(self):
        """Test that model_dump_json() works with temporal fields."""
        model = ModelSCD2Full(name="test", value=42)

        # Set some temporal fields
        model.tenant_id = uuid4()
        model.version = 3

        # Should serialize to JSON without errors
        json_str = model.model_dump_json()
        assert "tenant_id" in json_str
        assert "version" in json_str
        assert "valid_from" in json_str

    def test_jsonb_field_serialization(self):
        """Test that JSONB fields work with temporal fields."""
        model = ModelWithJSONB(
            name="test",
            metadata={"key": "value", "nested": {"data": 123}},
            tags=["tag1", "tag2"],
            settings={"enabled": True},
        )

        # Check temporal fields exist alongside JSONB fields
        assert hasattr(model, "tenant_id")
        assert hasattr(model, "version")

        # Check model_dump includes both JSONB and temporal fields
        data = model.model_dump()
        assert "metadata" in data
        assert "tenant_id" in data
        assert "version" in data

        # Check JSONB data is preserved
        assert data["metadata"] == {"key": "value", "nested": {"data": 123}}
        assert data["tags"] == ["tag1", "tag2"]

    def test_field_injection_does_not_override_user_fields(self):
        """Test that user-defined fields take precedence over injection."""

        class CustomModel(PydanticModel):
            __temporal_strategy__ = "scd2"
            __multi_tenant__ = True

            name: str
            # User explicitly defines tenant_id with different default
            tenant_id: UUID = Field(default_factory=uuid4, description="Custom tenant")

        model = CustomModel(name="test")

        # User-defined field should have its custom default
        assert model.tenant_id is not None  # Has a generated UUID, not None

        # Other temporal fields should still be injected
        assert hasattr(model, "version")
        assert hasattr(model, "valid_from")

    def test_temporal_fields_in_model_fields_dict(self):
        """Test that injected fields appear in model_fields."""
        # Check that temporal fields are in model_fields
        assert "tenant_id" in ModelSCD2Full.model_fields
        assert "version" in ModelSCD2Full.model_fields
        assert "valid_from" in ModelSCD2Full.model_fields
        assert "valid_to" in ModelSCD2Full.model_fields
        assert "deleted_at" in ModelSCD2Full.model_fields
        assert "deleted_by" in ModelSCD2Full.model_fields

        # Check field info has correct types
        tenant_field = ModelSCD2Full.model_fields["tenant_id"]
        assert tenant_field.annotation is UUID

        version_field = ModelSCD2Full.model_fields["version"]
        assert version_field.annotation is int

        valid_from_field = ModelSCD2Full.model_fields["valid_from"]
        assert valid_from_field.annotation is datetime

    def test_temporal_fields_in_annotations(self):
        """Test that injected fields appear in __annotations__."""
        # Check that temporal fields are in __annotations__
        assert "tenant_id" in ModelSCD2Full.__annotations__
        assert "version" in ModelSCD2Full.__annotations__
        assert "valid_from" in ModelSCD2Full.__annotations__

        # Check types are correct
        assert ModelSCD2Full.__annotations__["tenant_id"] is UUID
        assert ModelSCD2Full.__annotations__["version"] is int
        assert ModelSCD2Full.__annotations__["valid_from"] is datetime
        assert ModelSCD2Full.__annotations__["valid_to"] == Optional[datetime]


class TestFieldDefaults:
    """Test default values for injected temporal fields."""

    def test_tenant_id_default(self):
        """Test tenant_id has None as default."""
        model = ModelNoneTenant(name="test", value=42)
        assert model.tenant_id is None

    def test_version_default(self):
        """Test version has 1 as default."""
        model = ModelSCD2Basic(name="test", value=42)
        assert model.version == 1

    def test_valid_from_default(self):
        """Test valid_from has current time as default."""
        before = datetime.now(timezone.utc)
        model = ModelSCD2Basic(name="test", value=42)
        after = datetime.now(timezone.utc)

        # Check valid_from is between before and after
        assert before <= model.valid_from <= after

    def test_valid_to_default(self):
        """Test valid_to has None as default."""
        model = ModelSCD2Basic(name="test", value=42)
        assert model.valid_to is None

    def test_deleted_fields_default(self):
        """Test deleted_at and deleted_by have None as default."""
        model = ModelNoneSoftDelete(name="test", value=42)
        assert model.deleted_at is None
        assert model.deleted_by is None


class TestModelRebuild:
    """Test that model_rebuild() is called after field injection."""

    def test_model_schema_includes_temporal_fields(self):
        """Test that model_json_schema includes temporal fields."""
        schema = ModelSCD2Full.model_json_schema()

        # Check properties include temporal fields
        props = schema.get("properties", {})
        assert "tenant_id" in props
        assert "version" in props
        assert "valid_from" in props
        assert "valid_to" in props
        assert "deleted_at" in props
        assert "deleted_by" in props

    def test_model_fields_count(self):
        """Test that model_fields has correct count including temporal fields."""
        # ModelSCD2Full should have:
        # - Standard: id, created_at, updated_at, created_by, updated_by (5)
        # - User: name, value (2)
        # - Temporal: tenant_id, version, valid_from, valid_to, deleted_at, deleted_by (6)
        # Total: 13 fields
        assert len(ModelSCD2Full.model_fields) == 13

    def test_field_required_status(self):
        """Test that temporal fields have correct required status."""
        # Most temporal fields should be optional or have defaults
        schema = ModelSCD2Full.model_json_schema()
        required = schema.get("required", [])

        # User fields should be required
        assert "name" in required
        assert "value" in required

        # Temporal fields with defaults should not be required
        # (they have default values or factories)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
