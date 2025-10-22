"""
Example: Regulation Model with SCD2 (Slowly Changing Dimension Type 2).

This example demonstrates:
- Immutable version history
- Time travel queries
- Version comparison
- Regulatory compliance use case
"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from ff_storage import Field, PydanticModel, PydanticRepository
from ff_storage.db.connections.postgres import PostgresPool

# ==================== Model Definition ====================


class Regulation(PydanticModel):
    """
    Regulation model with immutable version history (SCD2).

    Features:
    - Immutable versions (every update creates new version)
    - Time travel queries (state at any point in time)
    - Version history tracking
    - Perfect for regulatory compliance
    """

    __table_name__ = "regulations"
    __temporal_strategy__ = "scd2"  # Slowly Changing Dimension Type 2
    __soft_delete__ = True  # Built-in for SCD2
    __multi_tenant__ = True  # Multi-tenant enabled

    # User-defined fields
    code: str = Field(
        max_length=50,
        description="Regulation code (e.g., GDPR, HIPAA)",
        db_index=True,
    )

    title: str = Field(
        max_length=255,
        description="Regulation title",
    )

    description: str = Field(
        description="Detailed description of the regulation",
    )

    effective_date: datetime = Field(
        description="When this regulation becomes effective",
    )

    authority: str = Field(
        max_length=100,
        description="Regulatory authority (e.g., EU, FDA)",
    )


# ==================== Usage Example ====================


async def main():
    """Demonstrate SCD2 immutable version history."""

    # Setup
    org_id = uuid4()
    user_id = uuid4()

    # Connect to database
    db_pool = PostgresPool(
        dbname="fenix_dev",
        user="fenix",
        password="password",
        host="localhost",
        port=5432,
    )
    await db_pool.connect()

    # Create repository
    repo = PydanticRepository(
        Regulation,
        db_pool,
        tenant_id=org_id,
    )

    print("=== Regulation SCD2 Example ===\n")

    # ==================== CREATE (Version 1) ====================

    print("1. Creating regulation (Version 1)...")
    regulation = Regulation(
        code="GDPR",
        title="General Data Protection Regulation",
        description="EU regulation on data protection and privacy",
        effective_date=datetime(2018, 5, 25, tzinfo=timezone.utc),
        authority="European Union",
    )

    v1 = await repo.create(regulation, user_id=user_id)
    print(f"   Created: {v1.title}")
    print(f"   Version: {v1.version}")
    print(f"   Valid from: {v1.valid_from}")
    print(f"   Valid to: {v1.valid_to}")  # None (current version)
    print()

    # Save timestamp for time travel later
    after_v1 = datetime.now(timezone.utc)

    # Wait a bit so timestamps are different
    await asyncio.sleep(0.1)

    # ==================== UPDATE (Version 2 - Immutable!) ====================

    print("2. Updating regulation (creates Version 2, Version 1 closed)...")
    v1.description = "EU regulation on data protection and privacy in the digital age"
    v1.title = "General Data Protection Regulation (Updated)"

    v2 = await repo.update(v1.id, v1, user_id=user_id)
    print(f"   Updated: {v2.title}")
    print(f"   Version: {v2.version}")  # Should be 2
    print(f"   Valid from: {v2.valid_from}")
    print(f"   Valid to: {v2.valid_to}")  # None (current version)
    print()

    after_v2 = datetime.now(timezone.utc)
    await asyncio.sleep(0.1)

    # ==================== UPDATE (Version 3) ====================

    print("3. Updating again (creates Version 3)...")
    v2.authority = "European Commission"

    v3 = await repo.update(v2.id, v2, user_id=user_id)
    print(f"   Version: {v3.version}")  # Should be 3
    print()

    # ==================== VERSION HISTORY ====================

    print("4. Getting complete version history...")
    versions = await repo.get_version_history(v1.id)
    print(f"   Total versions: {len(versions)}")
    for version in versions:
        print(f"   - Version {version.version}:")
        print(f"     Valid: {version.valid_from} → {version.valid_to or 'current'}")
        print(f"     Title: {version.title}")
        print(f"     Description: {version.description[:50]}...")
        print()

    # ==================== TIME TRAVEL QUERIES ====================

    print("5. Time travel: What was the regulation after Version 1?")
    historical_v1 = await repo.get(v1.id, as_of=after_v1)
    if historical_v1:
        print(f"   Version: {historical_v1.version}")
        print(f"   Title: {historical_v1.title}")
        print(f"   Authority: {historical_v1.authority}")
    print()

    print("6. Time travel: What was the regulation after Version 2?")
    historical_v2 = await repo.get(v1.id, as_of=after_v2)
    if historical_v2:
        print(f"   Version: {historical_v2.version}")
        print(f"   Title: {historical_v2.title}")
        print(f"   Authority: {historical_v2.authority}")
    print()

    # ==================== GET SPECIFIC VERSION ====================

    print("7. Getting specific version (Version 1)...")
    specific_v1 = await repo.get_version(v1.id, version=1)
    if specific_v1:
        print(f"   Title: {specific_v1.title}")
        print(f"   Description: {specific_v1.description}")
    print()

    # ==================== COMPARE VERSIONS ====================

    print("8. Comparing Version 1 vs Version 3...")
    diff = await repo.compare_versions(v1.id, version1=1, version2=3)

    changed_fields = [field for field, info in diff.items() if info["changed"]]
    print(f"   Changed fields: {len(changed_fields)}")
    for field in changed_fields:
        info = diff[field]
        print(f"   - {field}:")
        print(f"     Old: {info['old']}")
        print(f"     New: {info['new']}")
    print()

    # ==================== GET CURRENT VERSION ====================

    print("9. Getting current version (default behavior)...")
    current = await repo.get(v1.id)
    if current:
        print(f"   Current version: {current.version}")
        print(f"   Title: {current.title}")
        print(f"   Valid to: {current.valid_to}")  # Should be None
    print()

    # ==================== LIST CURRENT VERSIONS ====================

    print("10. Listing all current regulations...")
    current_regulations = await repo.list(limit=10)
    print(f"   Found {len(current_regulations)} current regulations")
    for reg in current_regulations:
        print(f"   - {reg.code} v{reg.version}: {reg.title}")
    print()

    # ==================== SOFT DELETE (Version stays, marked deleted) ====================

    print("11. Soft deleting current version...")
    deleted = await repo.delete(v1.id, user_id=user_id)
    print(f"   Deleted: {deleted}")
    print()

    print("12. Current version after delete...")
    deleted_reg = await repo.get(v1.id, include_deleted=True)
    if deleted_reg:
        print(f"   Version: {deleted_reg.version}")
        print(f"   Deleted at: {deleted_reg.deleted_at}")
        print(f"   Deleted by: {deleted_reg.deleted_by}")
    print()

    print("13. Version history still accessible...")
    all_versions = await repo.get_version_history(v1.id)
    print(f"   Total versions: {len(all_versions)}")
    print("   (History is immutable, even after delete)")
    print()

    # Cleanup
    await db_pool.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
