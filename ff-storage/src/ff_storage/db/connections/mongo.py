"""
MongoDB implementation for ff-storage.
Provides an async connection pool using motor with Cosmos DB compatibility.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...exceptions import MongoConnectionError, MongoDuplicateKeyError, MongoError
from ...health import HealthCheckResult, HealthStatus

try:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

    HAS_MOTOR = True
except ImportError:
    HAS_MOTOR = False
    AsyncIOMotorClient = None
    AsyncIOMotorCollection = None
    AsyncIOMotorDatabase = None


def _require_motor():
    if not HAS_MOTOR:
        raise ImportError(
            "motor is required for MongoDB support. "
            "Install it with: pip install ff-storage[mongo]"
        )


@dataclass
class MongoPool:
    """
    Async MongoDB connection pool using motor.

    Provides a consistent interface alongside PostgresPool, MySQLPool, and SQLServerPool.
    Motor manages connection pooling internally via its AsyncIOMotorClient.

    Supports MongoDB, Cosmos DB (MongoDB API), and AWS DocumentDB.

    :param connection_string: MongoDB connection URI (takes precedence over individual params).
    :param host: MongoDB host.
    :param port: MongoDB port.
    :param database: Database name.
    :param username: Optional username.
    :param password: Optional password.
    :param min_pool_size: Minimum connections in the pool (default: 1).
    :param max_pool_size: Maximum connections in the pool (default: 20).
    :param server_selection_timeout_ms: Timeout for server selection (default: 5000).
    :param connect_timeout_ms: Connection timeout (default: 10000).
    :param socket_timeout_ms: Socket timeout (default: 30000).
    :param cosmos_db: Enable Cosmos DB API compatibility (default: False).
    :param collect_metrics: Enable metrics collection (default: True).
    """

    # Connection (string OR individual params)
    connection_string: Optional[str] = None
    host: str = "localhost"
    port: int = 27017
    database: str = ""
    username: Optional[str] = None
    password: Optional[str] = None

    # Pool config
    min_pool_size: int = 1
    max_pool_size: int = 20
    server_selection_timeout_ms: int = 5000
    connect_timeout_ms: int = 10000
    socket_timeout_ms: int = 30000

    # Cosmos DB compatibility
    cosmos_db: bool = False

    # Monitoring
    collect_metrics: bool = True
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))

    # Internal state
    client: Optional[Any] = field(default=None, init=False)
    db: Optional[Any] = field(default=None, init=False)

    async def connect(self) -> None:
        """
        Create the async MongoDB client.

        Call once at application startup (e.g., FastAPI lifespan).

        :raises MongoConnectionError: If connection fails.
        """
        _require_motor()

        if self.client is not None:
            return  # Already connected

        try:
            from bson.codec_options import CodecOptions
            from bson.binary import UuidRepresentation

            codec_options = CodecOptions(uuid_representation=UuidRepresentation.STANDARD)

            kwargs: Dict[str, Any] = {
                "minPoolSize": self.min_pool_size,
                "maxPoolSize": self.max_pool_size,
                "serverSelectionTimeoutMS": self.server_selection_timeout_ms,
                "connectTimeoutMS": self.connect_timeout_ms,
                "socketTimeoutMS": self.socket_timeout_ms,
            }

            if self.cosmos_db:
                kwargs["retryWrites"] = False
                kwargs["directConnection"] = False

            if self.connection_string:
                self.client = AsyncIOMotorClient(self.connection_string, **kwargs)
            else:
                conn_kwargs = {
                    "host": self.host,
                    "port": self.port,
                    **kwargs,
                }
                if self.username:
                    conn_kwargs["username"] = self.username
                if self.password:
                    conn_kwargs["password"] = self.password
                self.client = AsyncIOMotorClient(**conn_kwargs)

            self.db = self.client.get_database(self.database, codec_options=codec_options)

            # Verify connectivity with a ping
            await self.client.admin.command("ping")

            self.logger.info(
                f"Connected to MongoDB: {self.database} "
                f"(pool={self.min_pool_size}-{self.max_pool_size})"
            )

        except Exception as e:
            self.client = None
            self.db = None
            self.logger.error(f"Failed to connect to MongoDB: {e}", exc_info=True)
            raise MongoConnectionError(self.host, self.port, self.database, str(e))

    async def disconnect(self) -> None:
        """
        Close the MongoDB client.

        Call once at application shutdown.
        """
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None
            self.logger.info("Closed MongoDB connection")

    def _ensure_connected(self) -> None:
        """Raise if not connected."""
        if self.db is None:
            raise MongoError("MongoPool is not connected. Call connect() first.")

    def collection(self, name: str) -> "AsyncIOMotorCollection":
        """
        Get a collection handle by name.

        :param name: Collection name.
        :return: Motor collection instance.
        """
        self._ensure_connected()
        return self.db[name]

    # ── Raw operations for power users ──────────────────────────────

    async def find_one(
        self, collection: str, filter: Dict[str, Any], **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Find a single document.

        :param collection: Collection name.
        :param filter: MongoDB query filter.
        :return: Document dict or None.
        """
        self._ensure_connected()
        return await self.db[collection].find_one(filter, **kwargs)

    async def find(
        self,
        collection: str,
        filter: Dict[str, Any],
        limit: int = 0,
        skip: int = 0,
        sort: Optional[List[tuple]] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Find multiple documents.

        :param collection: Collection name.
        :param filter: MongoDB query filter.
        :param limit: Maximum number of documents to return (0 = unlimited).
        :param skip: Number of documents to skip.
        :param sort: List of (field, direction) tuples.
        :return: List of document dicts.
        """
        self._ensure_connected()
        cursor = self.db[collection].find(filter, **kwargs)
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit or None)

    async def insert_one(self, collection: str, document: Dict[str, Any]) -> Any:
        """
        Insert a single document.

        :param collection: Collection name.
        :param document: Document to insert.
        :return: InsertOneResult.
        """
        self._ensure_connected()
        try:
            return await self.db[collection].insert_one(document)
        except Exception as e:
            if "duplicate key" in str(e).lower() or "E11000" in str(e):
                raise MongoDuplicateKeyError(collection, str(e))
            raise

    async def insert_many(self, collection: str, documents: List[Dict[str, Any]]) -> Any:
        """
        Insert multiple documents.

        :param collection: Collection name.
        :param documents: List of documents to insert.
        :return: InsertManyResult.
        """
        self._ensure_connected()
        try:
            return await self.db[collection].insert_many(documents)
        except Exception as e:
            if "duplicate key" in str(e).lower() or "E11000" in str(e):
                raise MongoDuplicateKeyError(collection, str(e))
            raise

    async def update_one(
        self, collection: str, filter: Dict[str, Any], update: Dict[str, Any], **kwargs
    ) -> Any:
        """
        Update a single document.

        :param collection: Collection name.
        :param filter: Query filter.
        :param update: Update operations (e.g., {"$set": {...}}).
        :return: UpdateResult.
        """
        self._ensure_connected()
        return await self.db[collection].update_one(filter, update, **kwargs)

    async def update_many(
        self, collection: str, filter: Dict[str, Any], update: Dict[str, Any], **kwargs
    ) -> Any:
        """
        Update multiple documents.

        :param collection: Collection name.
        :param filter: Query filter.
        :param update: Update operations.
        :return: UpdateResult.
        """
        self._ensure_connected()
        return await self.db[collection].update_many(filter, update, **kwargs)

    async def delete_one(self, collection: str, filter: Dict[str, Any]) -> bool:
        """
        Delete a single document.

        :param collection: Collection name.
        :param filter: Query filter.
        :return: True if a document was deleted.
        """
        self._ensure_connected()
        result = await self.db[collection].delete_one(filter)
        return result.deleted_count > 0

    async def delete_many(self, collection: str, filter: Dict[str, Any]) -> int:
        """
        Delete multiple documents.

        :param collection: Collection name.
        :param filter: Query filter.
        :return: Number of documents deleted.
        """
        self._ensure_connected()
        result = await self.db[collection].delete_many(filter)
        return result.deleted_count

    async def find_one_and_update(
        self,
        collection: str,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        return_document: bool = True,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Atomically find and update a single document.

        :param collection: Collection name.
        :param filter: Query filter.
        :param update: Update operations.
        :param return_document: If True, return the updated document.
        :return: The document (before or after update) or None.
        """
        self._ensure_connected()
        from pymongo import ReturnDocument

        return await self.db[collection].find_one_and_update(
            filter,
            update,
            return_document=ReturnDocument.AFTER if return_document else ReturnDocument.BEFORE,
            **kwargs,
        )

    async def count_documents(
        self, collection: str, filter: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Count documents matching a filter.

        :param collection: Collection name.
        :param filter: Optional query filter.
        :return: Document count.
        """
        self._ensure_connected()
        return await self.db[collection].count_documents(filter or {})

    async def aggregate(
        self, collection: str, pipeline: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute an aggregation pipeline.

        :param collection: Collection name.
        :param pipeline: Aggregation pipeline stages.
        :return: List of result documents.
        """
        self._ensure_connected()
        cursor = self.db[collection].aggregate(pipeline)
        return await cursor.to_list(length=None)

    # ── Index Management ────────────────────────────────────────────

    async def ensure_indexes(self, collection: str, indexes: List[Dict[str, Any]]) -> None:
        """
        Create indexes idempotently. Safe for Cosmos DB.

        :param collection: Collection name.
        :param indexes: List of index definitions.
            Each dict should have:
            - "keys": list of (field, direction) tuples
            - Optional "name", "unique", "sparse", "expireAfterSeconds", etc.
        """
        self._ensure_connected()
        coll = self.db[collection]

        for index_def in indexes:
            keys = index_def.pop("keys")
            name = index_def.pop("name", None)
            try:
                await coll.create_index(keys, name=name, background=True, **index_def)
            except Exception as e:
                # Cosmos DB may reject certain index options; log and continue
                if self.cosmos_db:
                    self.logger.warning(f"Index creation warning for {collection}: {e}")
                else:
                    raise

    # ── Health Check ────────────────────────────────────────────────

    async def health_check(self, name: str = "mongodb") -> HealthCheckResult:
        """
        Check MongoDB connectivity by issuing a ping command.

        :param name: Name for the health check result.
        :return: HealthCheckResult.
        """
        start_time = time.perf_counter()

        try:
            if self.client is None:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message="MongoDB client not initialized",
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                    error="Client is None",
                )

            await self.client.admin.command("ping")

            # Collect server info if available
            details: Dict[str, Any] = {"database": self.database}
            try:
                server_info = await self.client.server_info()
                details["version"] = server_info.get("version", "unknown")
            except Exception:
                pass

            return HealthCheckResult(
                name=name,
                status=HealthStatus.HEALTHY,
                message="MongoDB connection healthy",
                duration_ms=(time.perf_counter() - start_time) * 1000,
                details=details,
            )

        except Exception as e:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="MongoDB health check failed",
                duration_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    # ── Context Manager ─────────────────────────────────────────────

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
