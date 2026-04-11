"""Tests for mock generator extensions."""

from decimal import Decimal


from ff_storage.mock import (
    ExampleExtension,
    FieldMeta,
    GeneratorExtension,
    ValueGeneratorRegistry,
)


class TestGeneratorExtension:
    """Tests for GeneratorExtension base class."""

    def test_extension_base_class(self):
        """GeneratorExtension base class should work correctly."""

        class TestExtension(GeneratorExtension):
            NAME_PATTERNS = [
                (r"^test_field$", lambda f, m: "TEST_VALUE"),
            ]
            TYPE_OVERRIDES = {
                "custom_type": lambda f, m: "CUSTOM_TYPE_VALUE",
            }
            FIELD_OVERRIDES = {
                "specific_field": lambda f, m: "FIELD_VALUE",
            }

        ext = TestExtension()

        patterns = ext.get_patterns()
        assert len(patterns) == 1
        assert patterns[0][0] == r"^test_field$"

        type_overrides = ext.get_type_overrides()
        assert "custom_type" in type_overrides

        field_overrides = ext.get_field_overrides()
        assert "specific_field" in field_overrides

    def test_extension_empty_defaults(self):
        """GeneratorExtension with no overrides should return empty defaults."""

        class EmptyExtension(GeneratorExtension):
            pass

        ext = EmptyExtension()

        assert ext.get_patterns() == []
        assert ext.get_type_overrides() == {}
        assert ext.get_field_overrides() == {}

    def test_example_extension(self):
        """ExampleExtension should provide example patterns."""
        ext = ExampleExtension()

        patterns = ext.get_patterns()
        assert len(patterns) > 0

        # Should have order patterns
        pattern_strings = [p[0] for p in patterns]
        assert any("order" in p for p in pattern_strings)


class TestExtensionWithRegistry:
    """Tests for using extensions with ValueGeneratorRegistry."""

    def test_extend_registry_with_patterns(self):
        """Registry.extend() should add extension patterns."""

        class InsuranceExtension(GeneratorExtension):
            NAME_PATTERNS = [
                (r"^policy_number$", lambda f, m: f.bothify("POL-####-????").upper()),
                (
                    r"^premium$",
                    lambda f, m: Decimal(str(f.pyfloat(min_value=100, max_value=10000))),
                ),
            ]

        registry = ValueGeneratorRegistry(seed=42)
        extended = registry.extend(InsuranceExtension())

        # Test policy_number pattern
        meta = FieldMeta(name="policy_number", type_name="str")
        value = extended.generate(meta)
        assert value.startswith("POL-")
        assert len(value) == 13  # POL-####-????

        # Test premium pattern
        meta = FieldMeta(name="premium", type_name="decimal")
        value = extended.generate(meta)
        assert isinstance(value, Decimal)

    def test_extend_registry_with_field_overrides(self):
        """Registry.extend() should add field overrides."""

        class CustomExtension(GeneratorExtension):
            FIELD_OVERRIDES = {
                "ixr_number": lambda f, m: f"IXR{f.random_int(1, 999999):06d}-R0",
            }

        registry = ValueGeneratorRegistry(seed=42)
        extended = registry.extend(CustomExtension())

        meta = FieldMeta(name="ixr_number", type_name="str")
        value = extended.generate(meta)

        assert value.startswith("IXR")
        assert "-R0" in value

    def test_extend_registry_with_type_overrides(self):
        """Registry.extend() should add type overrides."""

        class TypeExtension(GeneratorExtension):
            TYPE_OVERRIDES = {
                "custom_money": lambda f, m: Decimal("100.00"),
            }

        registry = ValueGeneratorRegistry(seed=42)
        extended = registry.extend(TypeExtension())

        # Use a field name that won't match any pattern and type_name that matches our override
        meta = FieldMeta(name="xyz_field_123", type_name="custom_money")
        value = extended.generate(meta)

        assert value == Decimal("100.00")

    def test_extend_preserves_original(self):
        """Registry.extend() should not modify original registry."""
        original = ValueGeneratorRegistry(seed=42)

        class TestExtension(GeneratorExtension):
            FIELD_OVERRIDES = {
                "test_field": lambda f, m: "OVERRIDE",
            }

        extended = original.extend(TestExtension())

        # Extended should have the override
        meta = FieldMeta(name="test_field", type_name="str")
        assert extended.generate(meta) == "OVERRIDE"

        # Original should NOT have the override (will use default generation)
        value = original.generate(meta)
        assert value != "OVERRIDE"

    def test_chain_extensions(self):
        """Multiple extensions should be chainable."""

        class Extension1(GeneratorExtension):
            FIELD_OVERRIDES = {
                "field1": lambda f, m: "VALUE1",
            }

        class Extension2(GeneratorExtension):
            FIELD_OVERRIDES = {
                "field2": lambda f, m: "VALUE2",
            }

        registry = ValueGeneratorRegistry(seed=42)
        extended = registry.extend(Extension1()).extend(Extension2())

        meta1 = FieldMeta(name="field1", type_name="str")
        meta2 = FieldMeta(name="field2", type_name="str")

        assert extended.generate(meta1) == "VALUE1"
        assert extended.generate(meta2) == "VALUE2"


class TestDomainSpecificExtension:
    """Tests simulating real-world domain extensions (like insurance)."""

    def test_insurance_domain_extension(self):
        """Simulate insurance domain extension patterns."""

        class InsuranceExtension(GeneratorExtension):
            NAME_PATTERNS = [
                # Insurance-specific patterns
                (r"^policy_number$", lambda f, m: f.bothify("POL-####-????").upper()),
                (r"^claim_number$", lambda f, m: f.bothify("CLM-########")),
                (r"^broker_code$", lambda f, m: f.bothify("BRK-???-###").upper()),
            ]

            FIELD_OVERRIDES = {
                "ixr_number": lambda f, m: f"IXR{f.random_int(1, 999999):06d}-R0",
                "umr": lambda f, m: (
                    f"{f.random_element(['AON', 'MAR'])}{f.year()}{f.random_int(10000, 99999)}"
                ),
            }

        registry = ValueGeneratorRegistry(seed=42)
        extended = registry.extend(InsuranceExtension())

        # Test policy_number
        meta = FieldMeta(name="policy_number", type_name="str")
        policy = extended.generate(meta)
        assert policy.startswith("POL-")

        # Test claim_number
        meta = FieldMeta(name="claim_number", type_name="str")
        claim = extended.generate(meta)
        assert claim.startswith("CLM-")

        # Test ixr_number
        meta = FieldMeta(name="ixr_number", type_name="str")
        ixr = extended.generate(meta)
        assert ixr.startswith("IXR")
        assert "-R0" in ixr

        # Test umr
        meta = FieldMeta(name="umr", type_name="str")
        umr = extended.generate(meta)
        assert umr.startswith("AON") or umr.startswith("MAR")

    def test_ecommerce_domain_extension(self):
        """Simulate e-commerce domain extension patterns."""

        class EcommerceExtension(GeneratorExtension):
            NAME_PATTERNS = [
                (r"^order_id$|^order_number$", lambda f, m: f.bothify("ORD-########")),
                (r"^tracking_number$", lambda f, m: f.bothify("TRK??########").upper()),
                (r"^product_code$", lambda f, m: f.bothify("???-###").upper()),
            ]

        registry = ValueGeneratorRegistry(seed=42)
        extended = registry.extend(EcommerceExtension())

        # Test order_number
        meta = FieldMeta(name="order_number", type_name="str")
        order = extended.generate(meta)
        assert order.startswith("ORD-")

        # Test tracking_number
        meta = FieldMeta(name="tracking_number", type_name="str")
        tracking = extended.generate(meta)
        assert tracking.startswith("TRK")
        assert tracking.isupper()
