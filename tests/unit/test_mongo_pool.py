"""Tests for MongoPool — connection management, health check, configuration."""

import pytest

from ff_storage.db.connections.mongo import MongoPool, _require_motor
from ff_storage.exceptions import MongoConnectionError, MongoDuplicateKeyError, MongoError


class TestMongoPoolInit:
    def test_default_config(self):
        pool = MongoPool()
        assert pool.host == "localhost"
        assert pool.port == 27017
        assert pool.database == ""
        assert pool.min_pool_size == 1
        assert pool.max_pool_size == 20
        assert pool.cosmos_db is False
        assert pool.client is None
        assert pool.db is None

    def test_connection_string(self):
        pool = MongoPool(connection_string="mongodb://myhost:27018/mydb", database="testdb")
        assert pool.connection_string == "mongodb://myhost:27018/mydb"
        assert pool.database == "testdb"

    def test_individual_params(self):
        pool = MongoPool(
            host="db.example.com",
            port=27018,
            database="production",
            username="admin",
            password="secret",
        )
        assert pool.host == "db.example.com"
        assert pool.port == 27018
        assert pool.username == "admin"

    def test_cosmos_mode(self):
        pool = MongoPool(cosmos_db=True)
        assert pool.cosmos_db is True


class TestMongoPoolNotConnected:
    def test_ensure_connected_raises(self):
        pool = MongoPool()
        with pytest.raises(MongoError, match="not connected"):
            pool._ensure_connected()

    def test_collection_raises_when_not_connected(self):
        pool = MongoPool()
        with pytest.raises(MongoError):
            pool.collection("test")


class TestMongoPoolContextManager:
    @pytest.mark.asyncio
    async def test_context_manager_interface(self):
        """Verify the context manager protocol exists."""
        pool = MongoPool(connection_string="mongodb://nonexistent:27017", database="test")
        assert hasattr(pool, "__aenter__")
        assert hasattr(pool, "__aexit__")


class TestMongoExceptions:
    def test_mongo_error(self):
        err = MongoError("test error")
        assert str(err) == "test error"
        assert err.details == {}

    def test_mongo_connection_error(self):
        err = MongoConnectionError("host", 27017, "db", "timeout")
        assert "host" in str(err)
        assert "27017" in str(err)
        assert "timeout" in str(err)
        assert err.details["host"] == "host"
        assert err.details["port"] == 27017

    def test_mongo_duplicate_key_error(self):
        err = MongoDuplicateKeyError("users", "E11000 duplicate key")
        assert "users" in str(err)
        assert "duplicate" in str(err).lower()
        assert err.details["collection"] == "users"


class TestRequireMotor:
    def test_require_motor_gives_clear_message(self):
        """When motor is not installed, should give install instructions."""
        try:
            _require_motor()
        except ImportError as e:
            assert "pip install ff-storage[mongo]" in str(e)
