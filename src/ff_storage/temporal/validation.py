"""
Temporal configuration validation.

Validates temporal strategy configurations and model setup to catch
common errors before they reach production.
"""

from dataclasses import dataclass
from typing import List, Optional

from .enums import TemporalStrategyType


@dataclass
class ValidationError:
    """
    Single validation error/warning/info.

    Attributes:
        level: Severity level ("error", "warning", "info")
        message: Human-readable message
        field: Optional field name this error relates to
    """

    level: str  # "error", "warning", "info"
    message: str
    field: Optional[str] = None

    def __str__(self) -> str:
        """Format as human-readable string."""
        prefix = self.level.upper()
        field_part = f" [{self.field}]" if self.field else ""
        return f"{prefix}{field_part}: {self.message}"


class TemporalValidator:
    """
    Validate temporal strategy configurations and model setup.

    Catches common configuration errors:
    - Invalid strategy names
    - Missing required class variables
    - Multi-tenant configuration issues
    - FK relationships in SCD2 models
    - Missing temporal indexes

    Usage:
        errors = TemporalValidator.validate_model(MyModel)
        for error in errors:
            if error.level == "error":
                raise ValueError(error.message)
            elif error.level == "warning":
                warnings.warn(error.message)
    """

    @staticmethod
    def validate_model(model_class: type) -> List[ValidationError]:
        """
        Validate Pydantic model temporal configuration.

        Checks:
        - Required class variables present
        - Strategy compatibility with features
        - Index coverage for temporal queries
        - FK relationships (if SCD2)
        - Multi-tenant configuration

        Args:
            model_class: Pydantic model class to validate

        Returns:
            List of ValidationError objects (errors, warnings, info)

        Example:
            >>> class Product(PydanticModel):
            ...     __temporal_strategy__ = "scd2"
            ...     name: str
            ...
            >>> errors = TemporalValidator.validate_model(Product)
            >>> for error in errors:
            ...     print(error)
        """
        errors = []

        # Check required class vars
        if not hasattr(model_class, "__temporal_strategy__"):
            errors.append(
                ValidationError(
                    "warning",
                    "__temporal_strategy__ not set, defaulting to 'none'",
                )
            )
            return errors  # Can't validate further without strategy

        strategy = getattr(model_class, "__temporal_strategy__", "none")

        # Validate strategy value
        try:
            TemporalStrategyType(strategy)
        except ValueError:
            errors.append(
                ValidationError(
                    "error",
                    f"Invalid temporal strategy: '{strategy}'. Must be one of: none, copy_on_change, scd2",
                )
            )
            return errors  # Can't validate further with invalid strategy

        # Check multi-tenant configuration
        multi_tenant = getattr(model_class, "__multi_tenant__", True)
        tenant_field = getattr(model_class, "__tenant_field__", "tenant_id")

        if multi_tenant:
            # Check if tenant_field is explicitly defined
            if hasattr(model_class, "model_fields"):
                if tenant_field in model_class.model_fields:
                    errors.append(
                        ValidationError(
                            "info",
                            f"Multi-tenant field '{tenant_field}' explicitly defined in model "
                            "(will not be auto-injected)",
                        )
                    )
                else:
                    errors.append(
                        ValidationError(
                            "info",
                            f"Multi-tenant field '{tenant_field}' will be auto-injected by temporal strategy",
                        )
                    )

        # Strategy-specific validations
        if strategy == "scd2":
            errors.extend(TemporalValidator._validate_scd2(model_class))
        elif strategy == "copy_on_change":
            errors.extend(TemporalValidator._validate_copy_on_change(model_class))

        return errors

    @staticmethod
    def _validate_scd2(model_class: type) -> List[ValidationError]:
        """
        Validate SCD2-specific configuration.

        Checks:
        - FK relationships (warn about FK to logical ID vs version)
        - Remind about (id, version) UNIQUE constraint
        """
        errors = []

        # Check for FK fields
        if hasattr(model_class, "model_fields"):
            fk_count = 0
            for field_name, field_info in model_class.model_fields.items():
                metadata = getattr(field_info, "json_schema_extra", {}) or {}
                if metadata.get("db_foreign_key"):
                    fk_count += 1
                    errors.append(
                        ValidationError(
                            "warning",
                            f"FK field '{field_name}' in SCD2 model. Ensure FK points to logical ID, "
                            "not version-specific rows. See docs/guides/scd2_foreign_keys.md for details.",
                            field=field_name,
                        )
                    )

            if fk_count > 0:
                errors.append(
                    ValidationError(
                        "info",
                        f"Found {fk_count} FK field(s) in SCD2 model. "
                        "Children will reference logical ID across all versions.",
                    )
                )

        # Remind about UNIQUE constraint
        errors.append(
            ValidationError(
                "info",
                "SCD2 strategy automatically creates UNIQUE constraint on (id, version)",
            )
        )

        return errors

    @staticmethod
    def _validate_copy_on_change(model_class: type) -> List[ValidationError]:
        """
        Validate copy_on_change-specific configuration.

        Checks:
        - Warn about concurrency (row-level locking)
        - Remind about audit table creation
        """
        errors = []

        # Warn about concurrency
        errors.append(
            ValidationError(
                "info",
                "copy_on_change uses row-level locking (SELECT FOR UPDATE) during updates. "
                "Write concurrency is limited per row (acceptable for <100 updates/sec per row).",
            )
        )

        # Remind about auxiliary table
        table_name = (
            model_class.table_name()
            if hasattr(model_class, "table_name")
            else model_class.__name__.lower() + "s"
        )
        errors.append(
            ValidationError(
                "info",
                f"copy_on_change will create auxiliary audit table: {table_name}_audit",
            )
        )

        return errors

    @staticmethod
    def validate_indexes(table_def) -> List[ValidationError]:
        """
        Validate temporal index coverage.

        Checks:
        - SCD2 tables have (valid_from, valid_to) index
        - Multi-tenant tables have tenant_id index
        - Current version partial index exists

        Args:
            table_def: TableDefinition object

        Returns:
            List of ValidationError objects
        """
        errors = []

        # Get column names
        column_names = {col.name for col in table_def.columns}

        # Get index column tuples
        index_columns = {tuple(idx.columns) for idx in table_def.indexes}

        # Check for SCD2 temporal range index
        if "valid_from" in column_names and "valid_to" in column_names:
            if ("valid_from", "valid_to") not in index_columns:
                errors.append(
                    ValidationError(
                        "warning",
                        "SCD2 table missing temporal range index (valid_from, valid_to). "
                        "Time-travel queries may be slow.",
                    )
                )

        # Check for tenant_id index (if multi-tenant)
        if "tenant_id" in column_names:
            # Check if there's any index including tenant_id
            has_tenant_index = any("tenant_id" in idx.columns for idx in table_def.indexes)
            if not has_tenant_index:
                errors.append(
                    ValidationError(
                        "warning",
                        "Multi-tenant table missing index on tenant_id. "
                        "Queries filtered by tenant will be slow.",
                    )
                )

        # Check for current version partial index (SCD2)
        if "valid_to" in column_names:
            has_current_version_index = any(
                idx.where_clause and "valid_to IS NULL" in idx.where_clause
                for idx in table_def.indexes
            )
            if not has_current_version_index:
                errors.append(
                    ValidationError(
                        "info",
                        "Consider adding partial index for current versions (WHERE valid_to IS NULL)",
                    )
                )

        return errors
