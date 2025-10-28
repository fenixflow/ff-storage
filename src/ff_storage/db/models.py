"""
Base model classes for database entities.
Provides dataclass-based models with UUID primary keys and timestamps.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional
from uuid import UUID, uuid4


@dataclass
class BaseModel:
    """
    Base class for all database models.

    Provides common fields and methods for database entities.
    All models should inherit from this class.
    """

    # Common fields
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Class-level configuration
    __table_name__: ClassVar[Optional[str]] = None
    __schema__: ClassVar[str] = "public"

    @classmethod
    def table_name(cls) -> str:
        """
        Get the database table name for this model.

        :return: Table name (defaults to lowercase class name + 's').
        """
        if cls.__table_name__:
            return cls.__table_name__
        return cls.__name__.lower() + "s"

    @classmethod
    def full_table_name(cls) -> str:
        """
        Get the fully qualified table name (schema.table).

        :return: Full table name with schema.
        """
        return f"{cls.__schema__}.{cls.table_name()}"

    @classmethod
    def from_row(cls, row: tuple, columns: List[str]) -> "BaseModel":
        """
        Create an instance from a database row.

        :param row: Tuple of values from database.
        :param columns: List of column names in same order as row.
        :return: Model instance.
        """
        data = dict(zip(columns, row))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseModel":
        """
        Create an instance from a dictionary.

        Handles type conversions for common fields like UUID and datetime.

        :param data: Dictionary of field values.
        :return: Model instance.
        """
        # Convert string UUIDs to UUID objects
        if "id" in data and isinstance(data["id"], str):
            data["id"] = UUID(data["id"])

        # Convert string timestamps to datetime objects
        for field_name in ["created_at", "updated_at"]:
            if field_name in data and isinstance(data[field_name], str):
                data[field_name] = datetime.fromisoformat(data[field_name])

        # Filter to only fields that exist in the class
        field_names = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in field_names}

        return cls(**filtered_data)

    def to_dict(self, exclude: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Convert model instance to dictionary.

        :param exclude: Optional list of field names to exclude.
        :return: Dictionary representation.
        """
        data = asdict(self)

        # Convert UUID to string
        if "id" in data and isinstance(data["id"], UUID):
            data["id"] = str(data["id"])

        # Convert datetime to ISO format
        for field_name in ["created_at", "updated_at"]:
            if field_name in data and isinstance(data[field_name], datetime):
                data[field_name] = data[field_name].isoformat()

        # Exclude specified fields
        if exclude:
            for field_name in exclude:
                data.pop(field_name, None)

        return data

    def to_json(self, exclude: Optional[List[str]] = None) -> str:
        """
        Convert model instance to JSON string.

        :param exclude: Optional list of field names to exclude.
        :return: JSON string representation.
        """
        return json.dumps(self.to_dict(exclude), default=str)

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp to current time."""
        self.updated_at = datetime.now(timezone.utc)

    @classmethod
    def create_table_sql(cls) -> str:
        """
        Generate SQL for creating the table.

        Subclasses should override this to provide specific table structure.

        :return: CREATE TABLE SQL statement.
        """
        return f"""
        CREATE TABLE IF NOT EXISTS {cls.full_table_name()} (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """

    @classmethod
    def get_create_table_sql(cls) -> str:
        """
        Alias for create_table_sql() for compatibility with SchemaManager.

        :return: CREATE TABLE SQL statement.
        """
        return cls.create_table_sql()

    @classmethod
    def get_table_name(cls) -> str:
        """
        Alias for table_name() for compatibility with SchemaManager.

        :return: Table name.
        """
        return cls.table_name()

    @classmethod
    def drop_table_sql(cls) -> str:
        """
        Generate SQL for dropping the table.

        :return: DROP TABLE SQL statement.
        """
        return f"DROP TABLE IF EXISTS {cls.full_table_name()} CASCADE;"


@dataclass
class SoftDeleteModel(BaseModel):
    """
    Base model with soft delete functionality.

    Records are marked as deleted rather than being physically removed.
    """

    is_deleted: bool = False
    deleted_at: Optional[datetime] = None

    def soft_delete(self) -> None:
        """Mark the record as deleted."""
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)
        self.update_timestamp()

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None
        self.update_timestamp()

    @classmethod
    def create_table_sql(cls) -> str:
        """
        Generate SQL for creating table with soft delete fields.

        :return: CREATE TABLE SQL statement.
        """
        return f"""
        CREATE TABLE IF NOT EXISTS {cls.full_table_name()} (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            is_deleted BOOLEAN DEFAULT FALSE,
            deleted_at TIMESTAMP WITH TIME ZONE
        );

        CREATE INDEX IF NOT EXISTS idx_{cls.table_name()}_deleted
        ON {cls.full_table_name()}(is_deleted)
        WHERE is_deleted = FALSE;
        """


@dataclass
class VersionedModel(BaseModel):
    """
    Base model with version tracking.

    Supports optimistic locking and version history.
    """

    version: int = 1

    def increment_version(self) -> None:
        """Increment the version number."""
        self.version += 1
        self.update_timestamp()

    @classmethod
    def create_table_sql(cls) -> str:
        """
        Generate SQL for creating table with version field.

        :return: CREATE TABLE SQL statement.
        """
        return f"""
        CREATE TABLE IF NOT EXISTS {cls.full_table_name()} (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            version INTEGER DEFAULT 1
        );
        """


@dataclass
class AuditModel(BaseModel):
    """
    Base model with audit fields.

    Tracks who created and last modified the record.
    """

    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    def set_created_by(self, user_id: UUID) -> None:
        """Set the creator of the record."""
        self.created_by = user_id

    def set_updated_by(self, user_id: UUID) -> None:
        """Set who last updated the record."""
        self.updated_by = user_id
        self.update_timestamp()

    @classmethod
    def create_table_sql(cls) -> str:
        """
        Generate SQL for creating table with audit fields.

        :return: CREATE TABLE SQL statement.
        """
        return f"""
        CREATE TABLE IF NOT EXISTS {cls.full_table_name()} (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            created_by UUID,
            updated_by UUID
        );

        CREATE INDEX IF NOT EXISTS idx_{cls.table_name()}_created_by
        ON {cls.full_table_name()}(created_by);

        CREATE INDEX IF NOT EXISTS idx_{cls.table_name()}_updated_by
        ON {cls.full_table_name()}(updated_by);
        """


@dataclass
class MetadataModel(BaseModel):
    """
    Base model with JSON metadata field.

    Allows storing arbitrary additional data.
    """

    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_metadata(self, key: str, value: Any) -> None:
        """Add or update a metadata entry."""
        self.metadata[key] = value
        self.update_timestamp()

    def remove_metadata(self, key: str) -> None:
        """Remove a metadata entry."""
        self.metadata.pop(key, None)
        self.update_timestamp()

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get a metadata value."""
        return self.metadata.get(key, default)

    @classmethod
    def create_table_sql(cls) -> str:
        """
        Generate SQL for creating table with metadata field.

        :return: CREATE TABLE SQL statement.
        """
        return f"""
        CREATE TABLE IF NOT EXISTS {cls.full_table_name()} (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            metadata JSONB DEFAULT '{{}}'::JSONB
        );

        CREATE INDEX IF NOT EXISTS idx_{cls.table_name()}_metadata
        ON {cls.full_table_name()} USING GIN(metadata);
        """


@dataclass
class FullFeaturedModel(SoftDeleteModel, VersionedModel, AuditModel, MetadataModel):
    """
    Model with all features: soft delete, versioning, audit, and metadata.

    Use this for entities that need comprehensive tracking.
    """

    @classmethod
    def create_table_sql(cls) -> str:
        """
        Generate SQL for creating table with all features.

        :return: CREATE TABLE SQL statement.
        """
        return f"""
        CREATE TABLE IF NOT EXISTS {cls.full_table_name()} (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

            -- Soft delete fields
            is_deleted BOOLEAN DEFAULT FALSE,
            deleted_at TIMESTAMP WITH TIME ZONE,

            -- Version field
            version INTEGER DEFAULT 1,

            -- Audit fields
            created_by UUID,
            updated_by UUID,

            -- Metadata field
            metadata JSONB DEFAULT '{{}}'::JSONB
        );

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_{cls.table_name()}_deleted
        ON {cls.full_table_name()}(is_deleted)
        WHERE is_deleted = FALSE;

        CREATE INDEX IF NOT EXISTS idx_{cls.table_name()}_created_by
        ON {cls.full_table_name()}(created_by);

        CREATE INDEX IF NOT EXISTS idx_{cls.table_name()}_updated_by
        ON {cls.full_table_name()}(updated_by);

        CREATE INDEX IF NOT EXISTS idx_{cls.table_name()}_metadata
        ON {cls.full_table_name()} USING GIN(metadata);

        CREATE INDEX IF NOT EXISTS idx_{cls.table_name()}_created_at
        ON {cls.full_table_name()}(created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_{cls.table_name()}_updated_at
        ON {cls.full_table_name()}(updated_at DESC);
        """
