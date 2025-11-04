"""
Temporal strategy enumerations.
"""

from enum import Enum


class TemporalStrategyType(str, Enum):
    """
    Supported temporal versioning strategies.

    Strategies determine how changes to data are tracked over time:

    - NONE: Standard CRUD with basic timestamps (created_at, updated_at)
           No change history, direct UPDATE/DELETE

    - COPY_ON_CHANGE: Field-level audit trail
           Main table: Standard CRUD with timestamps
           Auxiliary table: {table}_audit with field-level change tracking
           Benefits: Lightweight, concurrent updates, granular history

    - SCD2: Slowly Changing Dimension Type 2 (immutable version history)
           Main table: All versions with valid_from/valid_to/version fields
           Immutable records, time-travel queries, complete audit trail
           Benefits: Point-in-time queries, regulatory compliance
    """

    NONE = "none"
    COPY_ON_CHANGE = "copy_on_change"
    SCD2 = "scd2"
