"""
MongoDB repository for PydanticModel classes.

Provides the same CRUD interface as PydanticRepository but operates via
MongoDB (motor). Supports soft deletes, multi-tenancy, field-level audit
trails (copy_on_change), and the F expression query syntax.

Usage:
    from ff_storage import PydanticModel, MongoPool, MongoRepository, F

    class Product(PydanticModel):
        __table_name__ = "products"
        __soft_delete__ = True
        __mongo_indexes__ = [
            {"keys": [("sku", 1)], "unique": True},
        ]
        name: str
        sku: str
        price: Decimal

    mongo = MongoPool(connection_string="mongodb://localhost:27017", database="myapp")
    await mongo.connect()

    repo = MongoRepository(Product, mongo, tenant_id=org_id)
    await repo.ensure_indexes()

    product = await repo.create(Product(name="Widget", sku="W-001", price=Decimal("9.99")))
    results = await repo.find(F.price > 5, sort=[("created_at", -1)])
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union
from uuid import UUID

from ..exceptions import MongoDuplicateKeyError, MongoError
from ..query.expressions import CompositeExpression, FilterExpression
from ..query.mongo_compiler import compile_filters

T = TypeVar("T")


class MongoRepository(Generic[T]):
    """
    MongoDB repository with PydanticModel support.

    Same CRUD interface as PydanticRepository but operates on MongoDB.
    Does NOT inherit from TemporalRepository (SQL-coupled).

    Features:
        - Type-safe CRUD returning Pydantic model instances
        - Soft delete support (__soft_delete__)
        - Multi-tenancy (__multi_tenant__ with tenant_id/tenant_ids)
        - F expression queries via mongo_compiler
        - Atomic find_one_and_update for state transitions
        - Index management via ensure_indexes()
        - Audit trail (copy_on_change) via separate audit collection
    """

    def __init__(
        self,
        model_class: type[T],
        mongo_pool: Any,
        tenant_id: Optional[UUID] = None,
        tenant_ids: Optional[List[UUID]] = None,
        logger: Any = None,
    ):
        self.model_class = model_class
        self._pool = mongo_pool
        self._tenant_id = tenant_id
        self._tenant_ids = tenant_ids
        self._logger = logger or logging.getLogger(__name__)

        # Read model metadata
        self._collection_name = model_class.table_name()
        self._soft_delete = getattr(model_class, "__soft_delete__", False)
        self._multi_tenant = getattr(model_class, "__multi_tenant__", False)
        self._tenant_field = getattr(model_class, "__tenant_field__", "tenant_id")
        self._temporal_strategy = getattr(model_class, "__temporal_strategy__", "none")

    # ── Collection Access ───────────────────────────────────────────

    @property
    def _collection(self):
        return self._pool.collection(self._collection_name)

    @property
    def _audit_collection(self):
        return self._pool.collection(f"{self._collection_name}_audit")

    # ── Document Translation ────────────────────────────────────────

    def _model_to_document(self, model: T) -> Dict[str, Any]:
        """Convert a PydanticModel instance to a MongoDB document."""
        data = model.model_dump(mode="python")
        # Translate id -> _id for MongoDB
        if "id" in data:
            data["_id"] = data.pop("id")
        return data

    def _document_to_model(self, doc: Dict[str, Any]) -> T:
        """Convert a MongoDB document to a PydanticModel instance."""
        if doc is None:
            return None
        doc = dict(doc)
        # Translate _id -> id
        if "_id" in doc:
            doc["id"] = doc.pop("_id")
        return self.model_class.model_validate(doc)

    # ── Base Filter ─────────────────────────────────────────────────

    def _build_base_filter(self, include_deleted: bool = False) -> Dict[str, Any]:
        """Build base MongoDB filter with tenant and soft-delete conditions."""
        base: Dict[str, Any] = {}

        # Multi-tenancy
        if self._multi_tenant:
            if self._tenant_id is not None:
                base[self._tenant_field] = self._tenant_id
            elif self._tenant_ids is not None:
                base[self._tenant_field] = {"$in": self._tenant_ids}

        # Soft delete
        if self._soft_delete and not include_deleted:
            base["deleted_at"] = None

        return base

    def _merge_filters(
        self,
        base: Dict[str, Any],
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Merge base filter with additional filter conditions."""
        if not extra:
            return base
        if not base:
            return extra
        return {"$and": [base, extra]}

    # ── CRUD Operations ─────────────────────────────────────────────

    async def create(self, model: T, user_id: Optional[UUID] = None) -> T:
        """
        Insert a new document.

        :param model: PydanticModel instance to insert.
        :param user_id: Optional user ID for audit fields.
        :return: The inserted model instance.
        """
        doc = self._model_to_document(model)
        now = datetime.now(timezone.utc)
        doc.setdefault("created_at", now)
        doc.setdefault("updated_at", now)
        if user_id is not None:
            doc.setdefault("created_by", user_id)
            doc.setdefault("updated_by", user_id)

        try:
            await self._collection.insert_one(doc)
        except Exception as e:
            if "duplicate key" in str(e).lower() or "E11000" in str(e):
                raise MongoDuplicateKeyError(self._collection_name, str(e))
            raise

        return self._document_to_model(doc)

    async def create_many(self, models: List[T], user_id: Optional[UUID] = None) -> List[T]:
        """
        Insert multiple documents.

        :param models: List of PydanticModel instances.
        :param user_id: Optional user ID for audit fields.
        :return: List of inserted model instances.
        """
        now = datetime.now(timezone.utc)
        docs = []
        for model in models:
            doc = self._model_to_document(model)
            doc.setdefault("created_at", now)
            doc.setdefault("updated_at", now)
            if user_id is not None:
                doc.setdefault("created_by", user_id)
                doc.setdefault("updated_by", user_id)
            docs.append(doc)

        await self._collection.insert_many(docs)
        return [self._document_to_model(doc) for doc in docs]

    async def get(self, id: Any, include_deleted: bool = False) -> Optional[T]:
        """
        Fetch a single document by ID.

        :param id: Document ID (UUID or string).
        :param include_deleted: Include soft-deleted documents.
        :return: Model instance or None.
        """
        base = self._build_base_filter(include_deleted)
        base["_id"] = id
        doc = await self._collection.find_one(base)
        return self._document_to_model(doc) if doc else None

    async def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        sort: Optional[List[tuple]] = None,
        include_deleted: bool = False,
    ) -> List[T]:
        """
        Query multiple documents.

        :param filters: Optional MongoDB filter dict.
        :param limit: Maximum results.
        :param offset: Number of documents to skip.
        :param sort: List of (field, direction) tuples.
        :param include_deleted: Include soft-deleted documents.
        :return: List of model instances.
        """
        base = self._build_base_filter(include_deleted)
        query = self._merge_filters(base, filters)

        cursor = self._collection.find(query)
        if sort:
            cursor = cursor.sort(sort)
        if offset:
            cursor = cursor.skip(offset)
        if limit:
            cursor = cursor.limit(limit)

        docs = await cursor.to_list(length=limit or None)
        return [self._document_to_model(doc) for doc in docs]

    async def update(self, id: Any, model: T, user_id: Optional[UUID] = None) -> T:
        """
        Update a document by ID.

        If copy_on_change temporal strategy is enabled, records field-level
        changes to the audit collection.

        :param id: Document ID.
        :param model: Updated model instance.
        :param user_id: Optional user ID for audit.
        :return: Updated model instance.
        """
        base = self._build_base_filter()
        base["_id"] = id

        # Read current document for audit trail
        old_doc = None
        if self._temporal_strategy == "copy_on_change":
            old_doc = await self._collection.find_one(base)

        doc = self._model_to_document(model)
        doc.pop("_id", None)  # Don't update _id
        doc.pop("created_at", None)  # Don't overwrite creation timestamp
        doc.pop("created_by", None)
        doc["updated_at"] = datetime.now(timezone.utc)
        if user_id is not None:
            doc["updated_by"] = user_id

        result = await self._collection.find_one_and_update(
            base,
            {"$set": doc},
            return_document=True,
        )

        if result is None:
            raise MongoError(
                f"Document {id} not found in {self._collection_name}",
                {"id": str(id), "collection": self._collection_name},
            )

        # Record audit trail
        if self._temporal_strategy == "copy_on_change" and old_doc:
            await self._record_audit(id, old_doc, result, user_id)

        return self._document_to_model(result)

    async def delete(self, id: Any, user_id: Optional[UUID] = None) -> bool:
        """
        Delete a document. Soft-delete if enabled, hard-delete otherwise.

        :param id: Document ID.
        :param user_id: Optional user ID for audit.
        :return: True if document was deleted.
        """
        base = self._build_base_filter()
        base["_id"] = id

        if self._soft_delete:
            now = datetime.now(timezone.utc)
            update: Dict[str, Any] = {"$set": {"deleted_at": now, "updated_at": now}}
            if user_id is not None:
                update["$set"]["deleted_by"] = user_id
            result = await self._collection.update_one(base, update)
            return result.modified_count > 0
        else:
            result = await self._collection.delete_one(base)
            return result.deleted_count > 0

    # ── Query with F Expressions ────────────────────────────────────

    async def find(
        self,
        *expressions: Union[FilterExpression, CompositeExpression],
        limit: int = 100,
        offset: int = 0,
        sort: Optional[List[tuple]] = None,
        include_deleted: bool = False,
    ) -> List[T]:
        """
        Query using F expression syntax.

        :param expressions: FilterExpression or CompositeExpression objects.
        :param limit: Maximum results.
        :param offset: Skip count.
        :param sort: List of (field, direction) tuples.
        :param include_deleted: Include soft-deleted documents.
        :return: List of model instances.

        Example:
            results = await repo.find(F.price > 100, F.status == "active")
        """
        base = self._build_base_filter(include_deleted)
        expr_filter = compile_filters(list(expressions)) if expressions else {}
        query = self._merge_filters(base, expr_filter)

        cursor = self._collection.find(query)
        if sort:
            cursor = cursor.sort(sort)
        if offset:
            cursor = cursor.skip(offset)
        if limit:
            cursor = cursor.limit(limit)

        docs = await cursor.to_list(length=limit or None)
        return [self._document_to_model(doc) for doc in docs]

    async def find_one(
        self,
        *expressions: Union[FilterExpression, CompositeExpression],
        include_deleted: bool = False,
    ) -> Optional[T]:
        """
        Find a single document using F expression syntax.

        :param expressions: Filter expressions.
        :param include_deleted: Include soft-deleted documents.
        :return: Model instance or None.
        """
        base = self._build_base_filter(include_deleted)
        expr_filter = compile_filters(list(expressions)) if expressions else {}
        query = self._merge_filters(base, expr_filter)

        doc = await self._collection.find_one(query)
        return self._document_to_model(doc) if doc else None

    async def count(
        self,
        *expressions: Union[FilterExpression, CompositeExpression],
        include_deleted: bool = False,
    ) -> int:
        """
        Count documents matching F expression filters.

        :param expressions: Filter expressions.
        :param include_deleted: Include soft-deleted documents.
        :return: Document count.
        """
        base = self._build_base_filter(include_deleted)
        expr_filter = compile_filters(list(expressions)) if expressions else {}
        query = self._merge_filters(base, expr_filter)
        return await self._collection.count_documents(query)

    async def exists(
        self,
        *expressions: Union[FilterExpression, CompositeExpression],
        include_deleted: bool = False,
    ) -> bool:
        """
        Check if any documents match the given filters.

        :param expressions: Filter expressions.
        :param include_deleted: Include soft-deleted documents.
        :return: True if at least one document matches.
        """
        base = self._build_base_filter(include_deleted)
        expr_filter = compile_filters(list(expressions)) if expressions else {}
        query = self._merge_filters(base, expr_filter)
        doc = await self._collection.find_one(query, projection={"_id": 1})
        return doc is not None

    # ── Atomic Operations ───────────────────────────────────────────

    async def find_one_and_update(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        return_document: bool = True,
    ) -> Optional[T]:
        """
        Atomically find and update a document.

        The base filter (tenant + soft delete) is merged with the provided filter.
        Use this for atomic state transitions (e.g., run status updates).

        :param filter: Additional query filter.
        :param update: MongoDB update operations (e.g., {"$set": {...}}).
        :param return_document: Return the updated document (True) or original (False).
        :return: Model instance or None.
        """
        from pymongo import ReturnDocument

        base = self._build_base_filter()
        query = self._merge_filters(base, filter)

        doc = await self._collection.find_one_and_update(
            query,
            update,
            return_document=ReturnDocument.AFTER if return_document else ReturnDocument.BEFORE,
        )
        return self._document_to_model(doc) if doc else None

    # ── Aggregation ─────────────────────────────────────────────────

    async def aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute an aggregation pipeline on this collection.

        The base filter is NOT automatically prepended — add a $match stage
        yourself if needed.

        :param pipeline: MongoDB aggregation pipeline stages.
        :return: List of result documents.
        """
        cursor = self._collection.aggregate(pipeline)
        return await cursor.to_list(length=None)

    # ── Index Management ────────────────────────────────────────────

    async def ensure_indexes(self) -> None:
        """
        Create indexes declared on the model class.

        Reads both:
        - __mongo_indexes__: compound index definitions
        - Field-level db_index / db_unique metadata

        Idempotent — safe to call on every startup.
        """
        indexes = []

        # Class-level compound indexes
        for idx_def in getattr(self.model_class, "__mongo_indexes__", []):
            indexes.append(copy.deepcopy(idx_def))

        # Field-level indexes from Pydantic field metadata
        for field_name, field_info in self.model_class.model_fields.items():
            extra = (
                (field_info.json_schema_extra or {})
                if hasattr(field_info, "json_schema_extra")
                else {}
            )
            if not isinstance(extra, dict):
                continue
            if extra.get("db_index"):
                indexes.append({"keys": [(field_name, 1)]})
            if extra.get("db_unique"):
                indexes.append({"keys": [(field_name, 1)], "unique": True})

        if indexes:
            await self._pool.ensure_indexes(self._collection_name, indexes)
            self._logger.info(f"Ensured {len(indexes)} indexes on {self._collection_name}")

    # ── Audit Trail (copy_on_change) ────────────────────────────────

    async def _record_audit(
        self,
        record_id: Any,
        old_doc: Dict[str, Any],
        new_doc: Dict[str, Any],
        user_id: Optional[UUID],
    ) -> None:
        """Record field-level changes to the audit collection."""
        changes = []
        for key in set(old_doc.keys()) | set(new_doc.keys()):
            if key in ("_id", "updated_at", "updated_by"):
                continue
            old_val = old_doc.get(key)
            new_val = new_doc.get(key)
            if old_val != new_val:
                changes.append(
                    {
                        "field": key,
                        "old_value": old_val,
                        "new_value": new_val,
                    }
                )

        if changes:
            await self._audit_collection.insert_one(
                {
                    "record_id": record_id,
                    "changes": changes,
                    "changed_by": user_id,
                    "changed_at": datetime.now(timezone.utc),
                }
            )

    async def get_audit_history(self, id: Any) -> List[Dict[str, Any]]:
        """
        Fetch audit trail for a document.

        Only available when __temporal_strategy__ = "copy_on_change".

        :param id: Document ID.
        :return: List of audit records, newest first.
        """
        cursor = self._audit_collection.find({"record_id": id}).sort("changed_at", -1)
        return await cursor.to_list(length=None)
