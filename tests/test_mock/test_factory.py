"""Tests for MockFactory."""

from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID


from ff_storage import Field, PydanticModel
from ff_storage.mock import MockFactory, ValueGeneratorRegistry


class UserRole(Enum):
    """Test enum for user roles."""

    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


class SampleUser(PydanticModel):
    """Sample model for mock generation."""

    __table_name__ = "sample_users"
    __temporal_strategy__ = "none"
    __soft_delete__ = False
    __multi_tenant__ = False

    email: str = Field(max_length=255)
    first_name: str = Field(max_length=100)
    last_name: str = Field(max_length=100)
    age: int = Field(ge=18, le=120)
    balance: Decimal = Field(
        ge=0, le=1000000, json_schema_extra={"db_precision": 15, "db_scale": 2}
    )
    is_active: bool = Field(default=True)
    role: UserRole = Field(default=UserRole.USER)
    notes: Optional[str] = Field(default=None, max_length=500)


class SampleProduct(PydanticModel):
    """Sample model with explicit mock patterns."""

    __table_name__ = "sample_products"
    __temporal_strategy__ = "none"
    __soft_delete__ = False
    __multi_tenant__ = False

    name: str = Field(max_length=255, json_schema_extra={"mock_pattern": "title"})
    description: str = Field(max_length=1000)
    price: Decimal = Field(
        ge=0,
        le=100000,
        json_schema_extra={"db_precision": 10, "db_scale": 2, "mock_pattern": "money"},
    )
    sku: str = Field(
        max_length=20,
        json_schema_extra={"mock_generator": lambda f: f.bothify("SKU-####-????").upper()},
    )
    internal_code: str = Field(
        max_length=50,
        json_schema_extra={"mock_skip": True},
    )


class TestMockFactory:
    """Tests for MockFactory."""

    def test_factory_initialization(self):
        """Factory should initialize correctly."""
        factory = MockFactory()
        assert factory is not None
        assert factory.registry is not None

    def test_factory_with_seed(self):
        """Factory with seed should produce reproducible results."""
        factory1 = MockFactory(seed=42)
        factory2 = MockFactory(seed=42)

        user1 = factory1.create(SampleUser)
        user2 = factory2.create(SampleUser)

        assert user1.email == user2.email
        assert user1.first_name == user2.first_name

    def test_factory_create_basic(self):
        """Factory should create valid model instances."""
        factory = MockFactory(seed=42)
        user = factory.create(SampleUser)

        assert isinstance(user, SampleUser)
        assert isinstance(user.id, UUID)
        assert isinstance(user.email, str)
        assert "@" in user.email
        assert isinstance(user.first_name, str)
        assert isinstance(user.last_name, str)
        assert isinstance(user.age, int)
        assert 18 <= user.age <= 120
        assert isinstance(user.balance, Decimal)
        assert user.balance >= 0
        assert isinstance(user.is_active, bool)
        assert isinstance(user.role, UserRole)

    def test_factory_create_with_overrides(self):
        """Factory should respect overrides."""
        factory = MockFactory(seed=42)
        user = factory.create(
            SampleUser,
            overrides={
                "email": "admin@example.com",
                "is_active": False,
                "role": UserRole.ADMIN,
            },
        )

        assert user.email == "admin@example.com"
        assert user.is_active is False
        assert user.role == UserRole.ADMIN

    def test_factory_create_with_mock_pattern(self):
        """Factory should use mock_pattern from Field."""
        factory = MockFactory(seed=42)
        product = factory.create(
            SampleProduct,
            overrides={"internal_code": "INT-001"},  # mock_skip field
        )

        assert isinstance(product.name, str)
        assert isinstance(product.price, Decimal)

    def test_factory_create_with_mock_generator(self):
        """Factory should use mock_generator from Field."""
        factory = MockFactory(seed=42)
        product = factory.create(
            SampleProduct,
            overrides={"internal_code": "INT-001"},
        )

        assert product.sku.startswith("SKU-")
        assert product.sku.isupper()

    def test_factory_create_with_mock_skip(self):
        """Factory should skip mock_skip fields."""
        factory = MockFactory(seed=42)

        # Without override, should fail validation (required field)
        # With override, should work
        product = factory.create(
            SampleProduct,
            overrides={"internal_code": "INT-001"},
        )

        assert product.internal_code == "INT-001"

    def test_factory_create_batch(self):
        """Factory should create multiple instances."""
        factory = MockFactory(seed=42)
        users = factory.create_batch(SampleUser, 10)

        assert len(users) == 10
        assert all(isinstance(u, SampleUser) for u in users)
        # All should have different IDs
        ids = [u.id for u in users]
        assert len(set(ids)) == 10

    def test_factory_create_batch_with_overrides(self):
        """Factory batch should apply overrides to all instances."""
        factory = MockFactory(seed=42)
        users = factory.create_batch(
            SampleUser,
            5,
            overrides={"is_active": False},
        )

        assert all(u.is_active is False for u in users)

    def test_factory_create_stream(self):
        """Factory stream should yield instances one at a time."""
        factory = MockFactory(seed=42)
        count = 0

        for user in factory.create_stream(SampleUser, 5):
            assert isinstance(user, SampleUser)
            count += 1

        assert count == 5

    def test_factory_with_custom_registry(self):
        """Factory should accept custom registry."""
        registry = ValueGeneratorRegistry(seed=42)
        registry.register_field_override(
            "email",
            lambda f, m: "custom@test.com",
        )

        factory = MockFactory(registry=registry)
        user = factory.create(SampleUser)

        assert user.email == "custom@test.com"

    def test_factory_reset_seed(self):
        """Factory reset_seed should allow reproducible regeneration."""
        factory = MockFactory(seed=42)
        user1 = factory.create(SampleUser)

        factory.reset_seed(42)
        user2 = factory.create(SampleUser)

        assert user1.email == user2.email


class TestPydanticModelMockMethods:
    """Tests for PydanticModel.create_mock() methods."""

    def test_create_mock(self):
        """PydanticModel.create_mock should work correctly."""
        user = SampleUser.create_mock(seed=42)

        assert isinstance(user, SampleUser)
        assert isinstance(user.email, str)
        assert "@" in user.email

    def test_create_mock_with_overrides(self):
        """PydanticModel.create_mock should accept overrides."""
        user = SampleUser.create_mock(
            overrides={"email": "test@example.com"},
            seed=42,
        )

        assert user.email == "test@example.com"

    def test_create_mock_reproducible(self):
        """PydanticModel.create_mock should be reproducible with seed."""
        user1 = SampleUser.create_mock(seed=42)
        user2 = SampleUser.create_mock(seed=42)

        assert user1.email == user2.email
        assert user1.first_name == user2.first_name

    def test_create_mock_batch(self):
        """PydanticModel.create_mock_batch should create multiple instances."""
        users = SampleUser.create_mock_batch(10, seed=42)

        assert len(users) == 10
        assert all(isinstance(u, SampleUser) for u in users)

    def test_create_mock_batch_reproducible(self):
        """PydanticModel.create_mock_batch should be reproducible."""
        users1 = SampleUser.create_mock_batch(5, seed=42)
        users2 = SampleUser.create_mock_batch(5, seed=42)

        for u1, u2 in zip(users1, users2):
            assert u1.email == u2.email

    def test_mock_factory(self):
        """PydanticModel.mock_factory should return a MockFactory."""
        factory = SampleUser.mock_factory(seed=42)

        assert isinstance(factory, MockFactory)

        user = factory.create(SampleUser)
        assert isinstance(user, SampleUser)
