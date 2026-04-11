"""Unit tests for JSONB deserialization in Query executor.

Tests that the Query executor correctly deserializes JSONB columns
from JSON strings back to Python objects before Pydantic validation.
"""

import json
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel

from ff_storage.pydantic_support import PydanticModel
from ff_storage.pydantic_support.field_metadata import Field
from ff_storage.pydantic_support.jsonb_utils import (
    deserialize_jsonb_fields,
    serialize_jsonb_fields,
)


class SimpleMetadata(BaseModel):
    """Nested Pydantic model for JSONB field."""

    key: str
    value: str


class SampleJsonbModel(PydanticModel):
    """Sample model with various JSONB field types for testing.

    Note: list[str] maps to PostgreSQL TEXT[] (native array), not JSONB.
    For JSONB list testing, we use list[dict] which maps to JSONB.
    """

    __table_name__ = "test_jsonb"
    __multi_tenant__ = False
    __soft_delete__ = False

    name: str = Field(max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)  # Maps to TEXT[] (native array)
    config: list[dict[str, Any]] = Field(default_factory=list)  # Maps to JSONB
    nested: Optional[SimpleMetadata] = None


class TestDeserializeJsonbFields:
    """Tests for deserialize_jsonb_fields utility."""

    def test_deserialize_empty_dict_string(self):
        """Deserialize empty JSON object string '{}'."""
        data = {"name": "test", "metadata": "{}"}
        result = deserialize_jsonb_fields(SampleJsonbModel, data)

        assert result["name"] == "test"
        assert result["metadata"] == {}
        assert isinstance(result["metadata"], dict)

    def test_deserialize_dict_with_values(self):
        """Deserialize JSON object string with values."""
        data = {"name": "test", "metadata": '{"key": "value", "count": 42}'}
        result = deserialize_jsonb_fields(SampleJsonbModel, data)

        assert result["metadata"] == {"key": "value", "count": 42}
        assert isinstance(result["metadata"], dict)

    def test_deserialize_list_string(self):
        """Deserialize JSON array of dicts string (JSONB type).

        Note: list[str] maps to PostgreSQL TEXT[] (native array) which asyncpg
        handles automatically. We test list[dict] which maps to JSONB.
        """
        data = {"name": "test", "config": '[{"env": "prod"}, {"env": "dev"}]'}
        result = deserialize_jsonb_fields(SampleJsonbModel, data)

        assert result["config"] == [{"env": "prod"}, {"env": "dev"}]
        assert isinstance(result["config"], list)

    def test_deserialize_list_of_dicts(self):
        """Deserialize JSON array of objects string."""
        data = {"name": "test", "config": '[{"env": "prod"}, {"env": "dev"}]'}
        result = deserialize_jsonb_fields(SampleJsonbModel, data)

        assert result["config"] == [{"env": "prod"}, {"env": "dev"}]
        assert isinstance(result["config"], list)
        assert isinstance(result["config"][0], dict)

    def test_skip_already_deserialized(self):
        """Skip fields that are already Python objects (not strings)."""
        data = {"name": "test", "metadata": {"key": "value"}}
        result = deserialize_jsonb_fields(SampleJsonbModel, data)

        assert result["metadata"] == {"key": "value"}
        assert isinstance(result["metadata"], dict)

    def test_skip_none_values(self):
        """Skip None values without error."""
        data = {"name": "test", "metadata": None, "tags": None}
        result = deserialize_jsonb_fields(SampleJsonbModel, data)

        assert result["metadata"] is None
        assert result["tags"] is None

    def test_preserve_non_jsonb_fields(self):
        """Non-JSONB fields should be unchanged."""
        data = {"name": "test", "metadata": "{}"}
        result = deserialize_jsonb_fields(SampleJsonbModel, data)

        assert result["name"] == "test"

    def test_skip_unknown_fields(self):
        """Unknown fields not in model should be preserved unchanged."""
        data = {"name": "test", "unknown_field": '{"data": "value"}'}
        result = deserialize_jsonb_fields(SampleJsonbModel, data)

        # Unknown field is passed through unchanged (not a JSONB field in model)
        assert result["unknown_field"] == '{"data": "value"}'

    def test_handle_invalid_json_gracefully(self):
        """Invalid JSON strings should be kept as-is."""
        data = {"name": "test", "metadata": "not valid json"}
        result = deserialize_jsonb_fields(SampleJsonbModel, data)

        # Invalid JSON kept as string, let Pydantic handle validation error
        assert result["metadata"] == "not valid json"


class TestSerializeJsonbFields:
    """Tests for serialize_jsonb_fields utility."""

    def test_serialize_dict(self):
        """Serialize Python dict to JSON string."""
        data = {"name": "test", "metadata": {"key": "value"}}
        result = serialize_jsonb_fields(SampleJsonbModel, data)

        assert result["metadata"] == '{"key": "value"}'
        assert isinstance(result["metadata"], str)

    def test_serialize_list(self):
        """Serialize Python list of dicts to JSON string (JSONB type).

        Note: list[str] maps to PostgreSQL TEXT[] (native array) which doesn't
        need JSON serialization. We test list[dict] which maps to JSONB.
        """
        data = {"name": "test", "config": [{"env": "prod"}, {"env": "dev"}]}
        result = serialize_jsonb_fields(SampleJsonbModel, data)

        assert result["config"] == '[{"env": "prod"}, {"env": "dev"}]'
        assert isinstance(result["config"], str)

    def test_skip_already_serialized(self):
        """Skip fields that are already JSON strings."""
        data = {"name": "test", "metadata": '{"key": "value"}'}
        result = serialize_jsonb_fields(SampleJsonbModel, data)

        assert result["metadata"] == '{"key": "value"}'

    def test_skip_none_values(self):
        """Skip None values without error."""
        data = {"name": "test", "metadata": None}
        result = serialize_jsonb_fields(SampleJsonbModel, data)

        assert result["metadata"] is None

    def test_serialize_uuid_in_dict(self):
        """UUIDs in dicts should be serialized using default=str."""
        test_uuid = uuid4()
        data = {"name": "test", "metadata": {"id": test_uuid}}
        result = serialize_jsonb_fields(SampleJsonbModel, data)

        parsed = json.loads(result["metadata"])
        assert parsed["id"] == str(test_uuid)


class TestRoundtrip:
    """Tests for serialize/deserialize roundtrip."""

    def test_roundtrip_preserves_data(self):
        """Serialize then deserialize should preserve original data."""
        original = {
            "name": "test",
            "metadata": {"key": "value", "nested": {"a": 1}},
            "tags": ["x", "y", "z"],
        }

        serialized = serialize_jsonb_fields(SampleJsonbModel, original.copy())
        deserialized = deserialize_jsonb_fields(SampleJsonbModel, serialized)

        assert deserialized["metadata"] == original["metadata"]
        assert deserialized["tags"] == original["tags"]
