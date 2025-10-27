"""
Temporal field and table definitions.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import UUID


@dataclass
class AuditEntry:
    """
    Represents a single audit log entry (copy_on_change strategy).
    """

    audit_id: UUID
    record_id: UUID
    tenant_id: Optional[UUID]
    field_name: str
    old_value: Any
    new_value: Any
    operation: str  # INSERT, UPDATE, DELETE
    changed_at: datetime
    changed_by: Optional[UUID]
    transaction_id: Optional[UUID]
    metadata: Optional[dict] = None


@dataclass
class VersionInfo:
    """
    Represents version metadata (scd2 strategy).
    """

    version: int
    valid_from: datetime
    valid_to: Optional[datetime]
    is_current: bool
    is_deleted: bool
