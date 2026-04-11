"""Tests for MongoAdapter and detect_adapter integration."""

import pytest

from ff_storage.db.adapters import MongoAdapter, detect_adapter
from ff_storage.db.connections.mongo import MongoPool


class TestMongoAdapter:
    def test_get_query_builder_returns_none(self):
        adapter = MongoAdapter()
        assert adapter.get_query_builder() is None

    def test_get_param_style(self):
        adapter = MongoAdapter()
        assert adapter.get_param_style() == "document"

    @pytest.mark.asyncio
    async def test_execute_with_returning_raises(self):
        adapter = MongoAdapter()
        with pytest.raises(NotImplementedError):
            await adapter.execute_with_returning(None, "query", {})

    def test_convert_params_raises(self):
        adapter = MongoAdapter()
        with pytest.raises(NotImplementedError):
            adapter.convert_params("query", {})


class TestDetectAdapter:
    def test_detect_mongo_pool(self):
        pool = MongoPool(database="test")
        adapter = detect_adapter(pool)
        assert isinstance(adapter, MongoAdapter)

    def test_detect_unknown_raises(self):
        class FakePool:
            pool = None

        with pytest.raises(ValueError, match="Unsupported"):
            detect_adapter(FakePool())
