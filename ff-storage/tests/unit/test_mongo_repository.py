"""Tests for MongoRepository — document translation, base filters, model integration."""

from datetime import datetime, timezone
from uuid import uuid4

from ff_storage.pydantic_support.base import PydanticModel
from ff_storage.pydantic_support.mongo_repository import MongoRepository


# Test model
class SampleWidget(PydanticModel):
    __table_name__ = "widgets"
    __soft_delete__ = True
    __multi_tenant__ = True
    __mongo_indexes__ = [
        {"keys": [("sku", 1)], "unique": True},
        {"keys": [("category", 1), ("created_at", -1)]},
    ]

    name: str
    sku: str
    price: float
    category: str = "general"


class SimpleModel(PydanticModel):
    __table_name__ = "simple"
    __soft_delete__ = False
    __multi_tenant__ = False

    value: str


class TestDocumentTranslation:
    """Test id <-> _id translation."""

    def test_model_to_document_translates_id(self):
        widget = SampleWidget(name="Bolt", sku="B-001", price=1.50)
        # Create a mock repo just for the translation methods
        repo = MongoRepository.__new__(MongoRepository)
        repo.model_class = SampleWidget

        doc = repo._model_to_document(widget)
        assert "_id" in doc
        assert "id" not in doc
        assert doc["_id"] == widget.id
        assert doc["name"] == "Bolt"

    def test_document_to_model_translates_id(self):
        doc = {
            "_id": uuid4(),
            "name": "Nut",
            "sku": "N-001",
            "price": 0.50,
            "category": "hardware",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        repo = MongoRepository.__new__(MongoRepository)
        repo.model_class = SampleWidget

        model = repo._document_to_model(doc)
        assert model.id == doc["_id"]  # _id was moved to id
        assert model.name == "Nut"
        assert model.sku == "N-001"

    def test_document_to_model_none_returns_none(self):
        repo = MongoRepository.__new__(MongoRepository)
        repo.model_class = SampleWidget
        assert repo._document_to_model(None) is None


class TestBaseFilter:
    """Test _build_base_filter for tenant and soft-delete filtering."""

    def _make_repo(self, model_class, tenant_id=None, tenant_ids=None):
        repo = MongoRepository.__new__(MongoRepository)
        repo.model_class = model_class
        repo._tenant_id = tenant_id
        repo._tenant_ids = tenant_ids
        repo._soft_delete = getattr(model_class, "__soft_delete__", False)
        repo._multi_tenant = getattr(model_class, "__multi_tenant__", False)
        repo._tenant_field = getattr(model_class, "__tenant_field__", "tenant_id")
        return repo

    def test_no_filters_when_disabled(self):
        repo = self._make_repo(SimpleModel)
        assert repo._build_base_filter() == {}

    def test_soft_delete_filter(self):
        repo = self._make_repo(SampleWidget)
        base = repo._build_base_filter()
        assert base.get("deleted_at") is None  # filters out deleted

    def test_soft_delete_include_deleted(self):
        repo = self._make_repo(SampleWidget)
        base = repo._build_base_filter(include_deleted=True)
        assert "deleted_at" not in base

    def test_tenant_single_id(self):
        tid = uuid4()
        repo = self._make_repo(SampleWidget, tenant_id=tid)
        base = repo._build_base_filter()
        assert base["tenant_id"] == tid

    def test_tenant_multiple_ids(self):
        tids = [uuid4(), uuid4()]
        repo = self._make_repo(SampleWidget, tenant_ids=tids)
        base = repo._build_base_filter()
        assert base["tenant_id"] == {"$in": tids}

    def test_tenant_and_soft_delete_combined(self):
        tid = uuid4()
        repo = self._make_repo(SampleWidget, tenant_id=tid)
        base = repo._build_base_filter()
        assert base["tenant_id"] == tid
        assert base["deleted_at"] is None


class TestMergeFilters:
    def _make_repo(self):
        repo = MongoRepository.__new__(MongoRepository)
        repo.model_class = SimpleModel
        repo._soft_delete = False
        repo._multi_tenant = False
        repo._tenant_id = None
        repo._tenant_ids = None
        repo._tenant_field = "tenant_id"
        return repo

    def test_empty_base_returns_extra(self):
        repo = self._make_repo()
        result = repo._merge_filters({}, {"status": "active"})
        assert result == {"status": "active"}

    def test_empty_extra_returns_base(self):
        repo = self._make_repo()
        result = repo._merge_filters({"tenant_id": "abc"}, None)
        assert result == {"tenant_id": "abc"}

    def test_both_present_uses_and(self):
        repo = self._make_repo()
        result = repo._merge_filters({"a": 1}, {"b": 2})
        assert result == {"$and": [{"a": 1}, {"b": 2}]}

    def test_both_empty(self):
        repo = self._make_repo()
        result = repo._merge_filters({}, {})
        assert result == {}


class TestMongoIndexes:
    def test_model_has_mongo_indexes(self):
        indexes = SampleWidget.__mongo_indexes__
        assert len(indexes) == 2
        assert indexes[0]["keys"] == [("sku", 1)]
        assert indexes[0]["unique"] is True

    def test_default_empty_indexes(self):
        assert SimpleModel.__mongo_indexes__ == []

    def test_table_name_as_collection(self):
        assert SampleWidget.table_name() == "widgets"
        assert SimpleModel.table_name() == "simple"
