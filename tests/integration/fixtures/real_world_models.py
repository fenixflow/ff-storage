"""
Real-world complex models from ix-ds for comprehensive schema testing.

These are COPIES of actual production models from the InsurX ix-ds service.
They represent the complexity and edge cases of real-world Pydantic models
that need to work correctly with ff-storage's schema synchronization.

Why these models are important for testing:
- Complex nested JSONB structures (lists of Pydantic models)
- Custom serializers/validators
- SCD2 temporal strategy with soft delete and multi-tenancy
- Multiple field types: Decimal, date, datetime, UUID, str, int, list, dict
- Field constraints: max_length, max_digits, decimal_places, ge, le
- Optional vs required fields
- Custom JSON encoding for list[str] fields

These models have historically caught edge cases that simpler test models miss.
"""

from datetime import date
from decimal import Decimal
from typing import Any, ClassVar

from ff_storage.pydantic_support import PydanticModel
from pydantic import BaseModel, Field, field_validator

# ==================== NESTED FINANCIAL MODELS ====================
# These are NOT PydanticModels - they're embedded as JSONB within the parent table


class Premium(BaseModel):
    """Premium amount and currency - stored as JSONB."""

    gross_premium: Decimal = Field(
        ...,
        description="Gross premium amount",
        max_digits=18,
        decimal_places=2,
    )

    currency: str = Field(
        default="USD",
        description="Currency code (ISO 4217)",
        max_length=3,
    )


class Limit(BaseModel):
    """Policy limit amount and currency - stored as JSONB."""

    amount: Decimal = Field(
        ...,
        description="Policy limit amount",
        max_digits=18,
        decimal_places=2,
    )

    currency: str = Field(
        default="USD",
        description="Currency code (ISO 4217)",
        max_length=3,
    )

    option_number: int | None = Field(
        None,
        description="Option number if multiple limits",
    )


class RiskCodeAllocation(BaseModel):
    """Risk code with allocation percentage - stored as JSONB."""

    code: str = Field(
        ...,
        description="Risk classification code",
        max_length=10,
    )

    allocation_percentage: Decimal = Field(
        ...,
        description="Allocation percentage (0.0 to 1.0)",
        ge=0,
        le=1,
    )


class InsuredPerson(BaseModel):
    """Artist/band member for non-appearance coverage - stored as JSONB."""

    name: str = Field(
        ...,
        description="Artist/performer name",
        max_length=200,
    )

    date_of_birth: date = Field(
        ...,
        description="Date of birth for age calculations",
    )

    role: str | None = Field(
        None,
        description="Role in band",
        max_length=100,
    )


class ExposureEvent(BaseModel):
    """Individual event in exposure schedule - stored as JSONB."""

    artist_or_event: str = Field(
        ...,
        description="Artist or event name",
        max_length=200,
    )

    event_date: date = Field(
        ...,
        description="Date of event",
    )

    event_type: str | None = Field(
        None,
        description="Type of event",
        max_length=50,
    )

    venue: str | None = Field(
        None,
        description="Venue name",
        max_length=200,
    )

    city: str | None = Field(
        None,
        description="City name",
        max_length=100,
    )

    state: str | None = Field(
        None,
        description="State/province",
        max_length=50,
    )

    country: str = Field(
        ...,
        description="Country name or code",
        max_length=100,
    )

    currency: str = Field(
        default="USD",
        description="Currency code for guarantees",
        max_length=3,
    )

    gross_guarantees: Decimal = Field(
        ...,
        description="Gross guarantees for this event",
        max_digits=18,
        decimal_places=2,
    )


# ==================== MAIN INSCOPING MODEL ====================


class RealWorldContingencySUI(PydanticModel):
    """
    Real-world SUI model from ix-ds with full complexity.

    This model represents actual production code with:
    - SCD2 versioning (immutable versions)
    - Soft delete (logical deletes)
    - Multi-tenant isolation
    - Complex nested JSONB structures
    - Custom serializers/validators
    - Multiple field types and constraints

    Auto-injected temporal fields (by ff-storage):
    - id, tenant_id, version, valid_from, valid_to
    - created_at, updated_at, created_by, updated_by
    - deleted_at, deleted_by
    """

    # ==================== TABLE CONFIGURATION ====================

    __table_name__: ClassVar[str] = "real_world_contingency_sui"
    __schema__: ClassVar[str] = "public"

    # ==================== TEMPORAL CONFIGURATION ====================

    __temporal_strategy__: ClassVar[str] = "scd2"
    __soft_delete__: ClassVar[bool] = True
    __multi_tenant__: ClassVar[bool] = True

    # ==================== CORE IDENTIFIERS ====================

    ixr_number: str = Field(
        ...,
        description="IXR reference ID",
        max_length=50,
    )

    # ==================== POLICY STRUCTURE ====================

    broker: str = Field(
        ...,
        description="Broker name",
        max_length=200,
    )

    placement_type: str = Field(
        ...,
        description="Placement method: Direct or Reinsurance",
        max_length=50,
    )

    insured_interest: str = Field(
        ...,
        description="Type of coverage: Tour, Festival, Event",
        max_length=200,
    )

    # ==================== RISK CLASSIFICATION ====================

    risk_codes: list[RiskCodeAllocation] = Field(
        ...,
        description="Risk codes with allocation (must sum to 100%)",
    )

    class_of_business: str = Field(
        ...,
        description="Class of business (usually Contingency)",
        max_length=100,
    )

    regulatory_risk_location: str = Field(
        ...,
        description="Regulatory risk location",
        max_length=200,
    )

    # ==================== FINANCIAL TERMS ====================

    limits: list[Limit] = Field(
        ...,
        description="Policy limits (can have multiple options)",
    )

    selected_limit_index: int = Field(
        default=0,
        description="Which limit option to use",
        ge=0,
    )

    attachment_point: Decimal = Field(
        default=Decimal("0"),
        description="Attachment point/deductible (0 = primary layer)",
        ge=0,
    )

    premiums: list[Premium] = Field(
        ...,
        description="Premiums",
    )

    brokerage_percentage: Decimal = Field(
        ...,
        description="Brokerage percentage (0.0 to 1.0)",
        ge=0,
        le=1,
    )

    order_hereon: Decimal = Field(
        default=Decimal("0"),
        description="Order hereon percentage",
        ge=0,
        le=1,
    )

    # ==================== COVERAGE PERIOD ====================

    risk_inception_date: date = Field(
        ...,
        description="Policy inception date",
    )

    risk_expiry_date: date = Field(
        ...,
        description="Policy expiry date",
    )

    # ==================== EXPOSURE DETAILS ====================

    exposure_schedule: list[ExposureEvent] = Field(
        default_factory=list,
        description="Event-by-event tour schedule",
    )

    # ==================== ARTIST DETAILS ====================

    insured_persons: list[InsuredPerson] = Field(
        default_factory=list,
        description="Artists/band members with DOB",
    )

    # ==================== LINE OFFERED ====================

    monetary_offered_line: Decimal | None = Field(
        None,
        description="Monetary offered line",
    )

    # ==================== ADDITIONAL COVERAGE ====================

    additional_coverages: list[str] = Field(
        default_factory=list,
        description="Additional coverage types (e.g., LCSF 2, National Mourning)",
    )

    rule_trigger_participant: str | None = Field(
        None,
        description="Participant triggering rule review",
        max_length=200,
    )

    client_classification: str | None = Field(
        None,
        description="Client classification",
        max_length=100,
    )

    # ==================== SYSTEM OUTPUTS ====================

    expected_decisioning: str | None = Field(
        None,
        description="Expected decision from rules: Fail, Referral, Pass",
        max_length=50,
    )

    decision_reason: str | None = Field(
        None,
        description="Reason for decision",
        max_length=500,
    )

    # ==================== SUPPLEMENTARY DATA ====================

    supplementary_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Flexible supplementary data stored as JSONB",
    )

    # ==================== CUSTOM VALIDATORS ====================

    @field_validator("supplementary_data", mode="before")
    @classmethod
    def ensure_supplementary_data(cls, value):
        """Ensure supplementary_data is never None to satisfy NOT NULL constraint."""
        if value is None:
            return {}
        return value
