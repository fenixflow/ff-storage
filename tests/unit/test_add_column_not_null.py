"""
Unit tests for ADD COLUMN NOT NULL handling.

Tests the v3.2.0 fix for NOT NULL column handling:
- ADD_COLUMN NOT NULL without DEFAULT generates safe multi-step SQL
- ALTER nullable→NOT NULL without DEFAULT raises clear error
- ALTER nullable→NOT NULL with DEFAULT auto-backfills
"""

import pytest
from ff_storage.db.schema_sync.base import SchemaDifferBase
from ff_storage.db.schema_sync.models import ColumnDefinition, ColumnType, TableDefinition
from ff_storage.db.schema_sync.postgres import PostgresMigrationGenerator


class TestAddColumnNotNull:
    """Test ADD_COLUMN generation for NOT NULL columns."""

    def test_add_not_null_without_default_generates_multistep_sql(self):
        """ADD NOT NULL without DEFAULT should generate safe 2-step SQL."""
        generator = PostgresMigrationGenerator()

        column = ColumnDefinition(
            name="new_field",
            column_type=ColumnType.STRING,
            nullable=False,  # NOT NULL
            default=None,  # No DEFAULT
            native_type="VARCHAR(255)",
        )

        sql = generator.generate_add_column("test_table", "public", column)

        # Should generate two-step SQL
        assert "ADD COLUMN IF NOT EXISTS" in sql
        assert "NULL;" in sql  # Step 1: Add as nullable
        assert "ALTER COLUMN" in sql  # Step 2: Set NOT NULL
        assert "SET NOT NULL" in sql

        # Verify it's truly two statements
        assert sql.count(";") == 2

    def test_add_not_null_with_default_generates_standard_sql(self):
        """ADD NOT NULL with DEFAULT should generate standard single-step SQL."""
        generator = PostgresMigrationGenerator()

        column = ColumnDefinition(
            name="status",
            column_type=ColumnType.STRING,
            nullable=False,  # NOT NULL
            default="'pending'",  # Has DEFAULT
            native_type="VARCHAR(50)",
        )

        sql = generator.generate_add_column("test_table", "public", column)

        # Should generate single-step SQL
        assert "ADD COLUMN IF NOT EXISTS" in sql
        assert "NOT NULL" in sql
        assert "DEFAULT 'pending'" in sql

        # Should only have one statement
        assert sql.count(";") == 1

    def test_add_nullable_column_generates_standard_sql(self):
        """ADD nullable column should generate standard SQL."""
        generator = PostgresMigrationGenerator()

        column = ColumnDefinition(
            name="optional_field",
            column_type=ColumnType.STRING,
            nullable=True,  # Nullable
            default=None,
            native_type="VARCHAR(255)",
        )

        sql = generator.generate_add_column("test_table", "public", column)

        # Should generate simple SQL
        assert "ADD COLUMN IF NOT EXISTS" in sql
        assert "VARCHAR(255)" in sql

        # Should only have one statement
        assert sql.count(";") == 1


class TestAlterColumnNullable:
    """Test ALTER_COLUMN detection for nullable changes."""

    def test_alter_nullable_to_not_null_without_default_raises_error(self):
        """Changing nullable→NOT NULL without DEFAULT should raise clear error."""
        differ = SchemaDifferBase()

        # Current state: nullable column
        current = TableDefinition(
            name="test_table",
            schema="public",
            columns=[
                ColumnDefinition(
                    name="existing_field",
                    column_type=ColumnType.STRING,
                    nullable=True,  # Currently nullable
                    default=None,
                    native_type="VARCHAR(255)",
                )
            ],
        )

        # Desired state: NOT NULL without DEFAULT
        desired = TableDefinition(
            name="test_table",
            schema="public",
            columns=[
                ColumnDefinition(
                    name="existing_field",
                    column_type=ColumnType.STRING,
                    nullable=False,  # Make NOT NULL
                    default=None,  # No DEFAULT!
                    native_type="VARCHAR(255)",
                )
            ],
        )

        # Should raise ValueError with helpful message
        with pytest.raises(ValueError) as exc_info:
            differ.compute_changes(desired, current)

        error_msg = str(exc_info.value)
        assert "Cannot alter column" in error_msg
        assert "nullable to NOT NULL" in error_msg
        assert "without DEFAULT value" in error_msg
        assert "Options:" in error_msg  # Shows resolution options

    def test_alter_nullable_to_not_null_with_default_generates_backfill(self):
        """Changing nullable→NOT NULL with DEFAULT should generate backfill SQL."""
        generator = PostgresMigrationGenerator()

        column = ColumnDefinition(
            name="existing_field",
            column_type=ColumnType.STRING,
            nullable=False,  # Make NOT NULL
            default="'default_value'",  # Has DEFAULT
            native_type="VARCHAR(255)",
        )

        sql = generator.generate_alter_column("test_table", "public", column)

        # Should contain UPDATE backfill statement
        assert "UPDATE" in sql
        assert "SET" in sql
        assert "WHERE" in sql
        assert "IS NULL" in sql

        # Should contain SET NOT NULL
        assert "SET NOT NULL" in sql

    def test_alter_not_null_to_nullable_generates_drop_constraint(self):
        """Changing NOT NULL→nullable should generate DROP NOT NULL."""
        generator = PostgresMigrationGenerator()

        column = ColumnDefinition(
            name="existing_field",
            column_type=ColumnType.STRING,
            nullable=True,  # Make nullable
            default=None,
            native_type="VARCHAR(255)",
        )

        sql = generator.generate_alter_column("test_table", "public", column)

        # Should contain DROP NOT NULL
        assert "DROP NOT NULL" in sql


class TestChangeTypeDestructiveness:
    """Test is_destructive flag for different scenarios."""

    def test_add_column_not_null_is_non_destructive(self):
        """ADD_COLUMN NOT NULL without DEFAULT should be marked non-destructive."""
        differ = SchemaDifferBase()

        # Current state: table without column
        current = TableDefinition(
            name="test_table",
            schema="public",
            columns=[],
        )

        # Desired state: add NOT NULL column
        desired = TableDefinition(
            name="test_table",
            schema="public",
            columns=[
                ColumnDefinition(
                    name="new_field",
                    column_type=ColumnType.STRING,
                    nullable=False,  # NOT NULL
                    default=None,  # No DEFAULT
                    native_type="VARCHAR(255)",
                )
            ],
        )

        changes = differ.compute_changes(desired, current)

        # Should have ADD_COLUMN change
        assert len(changes) == 1
        assert changes[0].change_type.value == "add_column"

        # Should be non-destructive
        assert changes[0].is_destructive is False

    def test_alter_nullable_to_not_null_with_default_is_destructive(self):
        """ALTER nullable→NOT NULL with DEFAULT should be marked destructive."""
        differ = SchemaDifferBase()

        # Current state: nullable column
        current = TableDefinition(
            name="test_table",
            schema="public",
            columns=[
                ColumnDefinition(
                    name="existing_field",
                    column_type=ColumnType.STRING,
                    nullable=True,  # Currently nullable
                    default=None,
                    native_type="VARCHAR(255)",
                )
            ],
        )

        # Desired state: NOT NULL with DEFAULT
        desired = TableDefinition(
            name="test_table",
            schema="public",
            columns=[
                ColumnDefinition(
                    name="existing_field",
                    column_type=ColumnType.STRING,
                    nullable=False,  # Make NOT NULL
                    default="'value'",  # With DEFAULT
                    native_type="VARCHAR(255)",
                )
            ],
        )

        changes = differ.compute_changes(desired, current)

        # Should have ALTER_COLUMN change
        assert len(changes) == 1
        assert changes[0].change_type.value == "alter_column_type"

        # Should be destructive (backfills data)
        assert changes[0].is_destructive is True

        # Description should mention backfill
        assert "will backfill with DEFAULT" in changes[0].description


class TestSQLQuoting:
    """Test that SQL identifiers are properly quoted."""

    def test_add_column_quotes_identifiers(self):
        """Verify column and table names are quoted (handles reserved keywords)."""
        generator = PostgresMigrationGenerator()

        column = ColumnDefinition(
            name="user",  # Reserved keyword
            column_type=ColumnType.STRING,
            nullable=False,
            default=None,
            native_type="VARCHAR(255)",
        )

        sql = generator.generate_add_column("order", "public", column)

        # Should quote table and column names
        assert '"public"."order"' in sql
        assert '"user"' in sql

    def test_alter_column_quotes_identifiers(self):
        """Verify UPDATE statement quotes identifiers."""
        generator = PostgresMigrationGenerator()

        column = ColumnDefinition(
            name="limit",  # Reserved keyword
            column_type=ColumnType.INTEGER,
            nullable=False,
            default="100",
            native_type="INTEGER",
        )

        sql = generator.generate_alter_column("select", "public", column)

        # Should quote table and column names in UPDATE
        assert '"public"."select"' in sql
        assert '"limit"' in sql
        assert "WHERE" in sql
        assert "IS NULL" in sql


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
