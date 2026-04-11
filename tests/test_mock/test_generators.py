"""Tests for mock data generators."""

from decimal import Decimal
from uuid import UUID


from ff_storage.mock import (
    DEFAULT_NAME_PATTERNS,
    FieldMeta,
    NAMED_PATTERNS,
    TYPE_GENERATORS,
    ValueGeneratorRegistry,
    get_named_pattern_generator,
    get_pattern_generator,
    get_type_generator,
)


class TestPatternGenerators:
    """Tests for pattern-based generators."""

    def test_get_pattern_generator_email(self):
        """Pattern generator should match email field."""
        gen = get_pattern_generator("email")
        assert gen is not None

        gen = get_pattern_generator("user_email")
        assert gen is not None

    def test_get_pattern_generator_name(self):
        """Pattern generator should match name fields."""
        gen = get_pattern_generator("first_name")
        assert gen is not None

        gen = get_pattern_generator("last_name")
        assert gen is not None

        gen = get_pattern_generator("company_name")
        assert gen is not None

    def test_get_pattern_generator_datetime(self):
        """Pattern generator should match datetime fields."""
        gen = get_pattern_generator("created_at")
        assert gen is not None

        gen = get_pattern_generator("updated_datetime")
        assert gen is not None

    def test_get_pattern_generator_boolean(self):
        """Pattern generator should match boolean fields."""
        gen = get_pattern_generator("is_active")
        assert gen is not None

        gen = get_pattern_generator("has_permission")
        assert gen is not None

    def test_get_pattern_generator_no_match(self):
        """Pattern generator should return None for unmatched fields."""
        gen = get_pattern_generator("xyz_random_field_123")
        assert gen is None

    def test_get_named_pattern_generator(self):
        """Named pattern generator should return correct generators."""
        gen = get_named_pattern_generator("email")
        assert gen is not None

        gen = get_named_pattern_generator("money")
        assert gen is not None

        gen = get_named_pattern_generator("nonexistent")
        assert gen is None

    def test_default_patterns_not_empty(self):
        """DEFAULT_NAME_PATTERNS should contain patterns."""
        assert len(DEFAULT_NAME_PATTERNS) > 0

    def test_named_patterns_not_empty(self):
        """NAMED_PATTERNS should contain patterns."""
        assert len(NAMED_PATTERNS) > 0


class TestTypeGenerators:
    """Tests for type-based generators."""

    def test_get_type_generator_uuid(self):
        """Type generator should return UUID generator."""
        gen = get_type_generator("uuid")
        assert gen is not None

    def test_get_type_generator_str(self):
        """Type generator should return string generator."""
        gen = get_type_generator("str")
        assert gen is not None

        gen = get_type_generator("string")
        assert gen is not None

    def test_get_type_generator_int(self):
        """Type generator should return int generator."""
        gen = get_type_generator("int")
        assert gen is not None

        gen = get_type_generator("integer")
        assert gen is not None

    def test_get_type_generator_decimal(self):
        """Type generator should return decimal generator."""
        gen = get_type_generator("decimal")
        assert gen is not None

    def test_get_type_generator_bool(self):
        """Type generator should return bool generator."""
        gen = get_type_generator("bool")
        assert gen is not None

        gen = get_type_generator("boolean")
        assert gen is not None

    def test_get_type_generator_datetime(self):
        """Type generator should return datetime generator."""
        gen = get_type_generator("datetime")
        assert gen is not None

    def test_type_generators_dict_not_empty(self):
        """TYPE_GENERATORS should contain generators."""
        assert len(TYPE_GENERATORS) > 0


class TestValueGeneratorRegistry:
    """Tests for ValueGeneratorRegistry."""

    def test_registry_initialization(self):
        """Registry should initialize correctly."""
        registry = ValueGeneratorRegistry()
        assert registry is not None
        assert registry.faker is not None

    def test_registry_with_seed(self):
        """Registry with seed should produce reproducible results."""
        registry1 = ValueGeneratorRegistry(seed=42)
        registry2 = ValueGeneratorRegistry(seed=42)

        meta = FieldMeta(name="email", type_name="str")

        value1 = registry1.generate(meta)
        value2 = registry2.generate(meta)

        assert value1 == value2

    def test_registry_generate_email(self):
        """Registry should generate email for email field."""
        registry = ValueGeneratorRegistry(seed=42)
        meta = FieldMeta(name="email", type_name="str")

        value = registry.generate(meta)
        assert "@" in value

    def test_registry_generate_uuid(self):
        """Registry should generate UUID for uuid type."""
        registry = ValueGeneratorRegistry(seed=42)
        meta = FieldMeta(name="id", type_name="uuid")

        value = registry.generate(meta)
        assert isinstance(value, UUID)

    def test_registry_generate_decimal_with_constraints(self):
        """Registry should respect decimal constraints."""
        registry = ValueGeneratorRegistry(seed=42)
        meta = FieldMeta(
            name="price",
            type_name="decimal",
            ge=0,
            le=1000,
            precision=10,
            scale=2,
        )

        value = registry.generate(meta)
        assert isinstance(value, Decimal)
        assert value >= 0
        assert value <= 1000

    def test_registry_generate_with_mock_pattern(self):
        """Registry should use explicit mock_pattern."""
        registry = ValueGeneratorRegistry(seed=42)
        meta = FieldMeta(
            name="some_field",
            type_name="str",
            mock_pattern="email",
        )

        value = registry.generate(meta)
        assert "@" in value

    def test_registry_generate_with_mock_generator(self):
        """Registry should use custom mock_generator."""
        registry = ValueGeneratorRegistry(seed=42)
        custom_value = "CUSTOM-123"
        meta = FieldMeta(
            name="custom_field",
            type_name="str",
            mock_generator=lambda f: custom_value,
        )

        value = registry.generate(meta)
        assert value == custom_value

    def test_registry_generate_with_mock_skip(self):
        """Registry should return None for mock_skip fields."""
        registry = ValueGeneratorRegistry(seed=42)
        meta = FieldMeta(
            name="skipped_field",
            type_name="str",
            mock_skip=True,
        )

        value = registry.generate(meta)
        assert value is None

    def test_registry_register_custom_pattern(self):
        """Registry should allow registering custom patterns."""
        registry = ValueGeneratorRegistry(seed=42)
        registry.register_pattern(
            r"^order_number$",
            lambda f, m: f"ORD-{f.random_int(1000, 9999)}",
        )

        meta = FieldMeta(name="order_number", type_name="str")
        value = registry.generate(meta)

        assert value.startswith("ORD-")

    def test_registry_register_field_override(self):
        """Registry should allow field-specific overrides."""
        registry = ValueGeneratorRegistry(seed=42)
        registry.register_field_override(
            "special_field",
            lambda f, m: "OVERRIDE_VALUE",
        )

        meta = FieldMeta(name="special_field", type_name="str")
        value = registry.generate(meta)

        assert value == "OVERRIDE_VALUE"

    def test_registry_extend(self):
        """Registry extend should create new registry with extension patterns."""
        from ff_storage.mock import GeneratorExtension

        class TestExtension(GeneratorExtension):
            NAME_PATTERNS = [
                (r"^test_pattern$", lambda f, m: "TEST_VALUE"),
            ]
            FIELD_OVERRIDES = {
                "test_field": lambda f, m: "FIELD_OVERRIDE",
            }

        registry = ValueGeneratorRegistry(seed=42)
        extended_registry = registry.extend(TestExtension())

        # Extended registry should have the new patterns
        meta = FieldMeta(name="test_pattern", type_name="str")
        value = extended_registry.generate(meta)
        assert value == "TEST_VALUE"

        meta = FieldMeta(name="test_field", type_name="str")
        value = extended_registry.generate(meta)
        assert value == "FIELD_OVERRIDE"

        # Original registry should NOT have the new patterns
        meta = FieldMeta(name="test_field", type_name="str")
        value = registry.generate(meta)
        assert value != "FIELD_OVERRIDE"

    def test_registry_reset_seed(self):
        """Registry reset_seed should allow reproducible regeneration."""
        registry = ValueGeneratorRegistry(seed=42)
        meta = FieldMeta(name="email", type_name="str")

        value1 = registry.generate(meta)

        registry.reset_seed(42)
        value2 = registry.generate(meta)

        assert value1 == value2
