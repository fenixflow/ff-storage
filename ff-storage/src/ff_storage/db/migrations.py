"""
Simple SQL file-based migration system.
Provides version tracking and execution of SQL migration files.
"""

import hashlib
import logging
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime, timezone


class MigrationManager:
    """
    Manages SQL file-based database migrations.

    Migrations are SQL files named with version prefixes (e.g., 001_initial_schema.sql).
    The manager tracks which migrations have been applied and runs pending ones in order.
    """

    def __init__(self, db_connection, migrations_path: str):
        """
        Initialize the migration manager.

        :param db_connection: Database connection instance (Postgres, PostgresPool, etc.)
        :param migrations_path: Path to directory containing migration SQL files.
        """
        self.db = db_connection
        self.migrations_path = Path(migrations_path)
        self.logger = logging.getLogger(__name__)

        if not self.migrations_path.exists():
            self.migrations_path.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Created migrations directory: {self.migrations_path}")

    def init_migrations_table(self) -> None:
        """
        Create the schema_migrations table if it doesn't exist.

        This table tracks which migrations have been applied.
        """
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            checksum VARCHAR(64),
            execution_time_ms INTEGER,
            success BOOLEAN DEFAULT TRUE,
            error_message TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_migrations_applied_at
        ON schema_migrations(applied_at DESC);
        """

        try:
            self.db.execute(create_table_sql)
            self.logger.info("Migrations table initialized")
        except Exception as e:
            self.logger.error(f"Failed to create migrations table: {e}")
            raise

    def get_applied_migrations(self) -> List[str]:
        """
        Get list of migrations that have already been applied.

        :return: List of version strings that have been applied successfully.
        """
        # First check if migrations table exists
        try:
            # Try to create the table if it doesn't exist
            self.init_migrations_table()
        except Exception as e:
            self.logger.debug(f"Could not ensure migrations table exists: {e}")

        query = """
        SELECT version
        FROM schema_migrations
        WHERE success = TRUE
        ORDER BY version
        """

        try:
            results = self.db.read_query(query)
            return [row[0] for row in results]
        except Exception as e:
            self.logger.debug(f"Could not read migrations table: {e}")
            # Table might not exist yet
            return []

    def get_pending_migrations(self) -> List[Tuple[str, Path]]:
        """
        Get list of migrations that haven't been applied yet.

        :return: List of tuples (version, filepath) for pending migrations.
        """
        applied = set(self.get_applied_migrations())
        pending = []

        # Find all SQL files in migrations directory
        migration_files = sorted(self.migrations_path.glob("*.sql"))

        for filepath in migration_files:
            # Extract version from filename (e.g., "001_initial_schema.sql" -> "001")
            version = filepath.stem.split("_")[0]

            # Skip if already applied
            if version not in applied:
                pending.append((version, filepath))

        return pending

    def calculate_checksum(self, filepath: Path) -> str:
        """
        Calculate SHA256 checksum of a migration file.

        :param filepath: Path to the migration file.
        :return: Hexadecimal checksum string.
        """
        with open(filepath, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def apply_migration(self, version: str, filepath: Path) -> None:
        """
        Apply a single migration file.

        :param version: Version identifier for the migration.
        :param filepath: Path to the SQL file to execute.
        :raises RuntimeError: If migration fails.
        """
        self.logger.info(f"Applying migration {version}: {filepath.name}")

        start_time = datetime.now(timezone.utc)
        checksum = self.calculate_checksum(filepath)
        error_message = None
        success = True

        try:
            # Read migration file
            with open(filepath, "r") as f:
                sql_content = f.read()

            # Split by semicolons but be careful with strings/comments
            # For now, execute the entire file as one statement
            # More sophisticated parsing can be added if needed
            statements = self._split_sql_statements(sql_content)

            # Execute each statement
            for statement in statements:
                if statement.strip():
                    self.db.execute(statement)

            self.logger.info(f"Successfully applied migration {version}")

        except Exception as e:
            error_message = str(e)
            success = False
            self.logger.error(f"Failed to apply migration {version}: {e}")

            # Try to rollback if possible
            if hasattr(self.db, "rollback"):
                self.db.rollback()

            raise RuntimeError(f"Migration {version} failed: {e}")

        finally:
            # Record migration attempt
            execution_time_ms = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

            record_sql = """
            INSERT INTO schema_migrations (
                version, checksum, execution_time_ms, success, error_message
            ) VALUES (%(version)s, %(checksum)s, %(time)s, %(success)s, %(error)s)
            ON CONFLICT (version) DO UPDATE SET
                applied_at = NOW(),
                checksum = EXCLUDED.checksum,
                execution_time_ms = EXCLUDED.execution_time_ms,
                success = EXCLUDED.success,
                error_message = EXCLUDED.error_message
            """

            try:
                self.db.execute(
                    record_sql,
                    {
                        "version": version,
                        "checksum": checksum,
                        "time": execution_time_ms,
                        "success": success,
                        "error": error_message,
                    },
                )
            except Exception as e:
                self.logger.error(f"Failed to record migration status: {e}")

    def _split_sql_statements(self, sql_content: str) -> List[str]:
        """
        Split SQL content into individual statements.

        Simple implementation that splits on semicolons.
        Can be enhanced to handle strings and comments properly.

        :param sql_content: The SQL file content.
        :return: List of SQL statements.
        """
        # Simple split for now - can be enhanced
        statements = []
        current = []

        for line in sql_content.split("\n"):
            # Skip comments
            if line.strip().startswith("--"):
                continue

            current.append(line)

            # Check if line ends with semicolon
            if line.rstrip().endswith(";"):
                statements.append("\n".join(current))
                current = []

        # Add any remaining content
        if current:
            statements.append("\n".join(current))

        return statements

    def migrate(self, target_version: Optional[str] = None) -> int:
        """
        Run all pending migrations up to target version.

        :param target_version: Optional version to migrate to. If None, runs all pending.
        :return: Number of migrations applied.
        """
        # Ensure migrations table exists
        self.init_migrations_table()

        # Get pending migrations
        pending = self.get_pending_migrations()

        if not pending:
            self.logger.info("No pending migrations")
            return 0

        # Filter by target version if specified
        if target_version:
            pending = [(v, f) for v, f in pending if v <= target_version]

        self.logger.info(f"Found {len(pending)} pending migrations")

        applied_count = 0
        for version, filepath in pending:
            try:
                self.apply_migration(version, filepath)
                applied_count += 1
            except RuntimeError as e:
                self.logger.error(f"Migration failed, stopping: {e}")
                break

        self.logger.info(f"Applied {applied_count} migrations")
        return applied_count

    def rollback(self, version: str) -> None:
        """
        Rollback to a specific version.

        Looks for down migration files (e.g., 001_down.sql) and executes them
        in reverse order to reach the target version.

        :param version: Version to rollback to.
        :raises NotImplementedError: Rollback not yet implemented.
        """
        # This would look for down migration files and execute them
        # Implementation depends on migration file naming convention
        raise NotImplementedError("Rollback functionality not yet implemented")

    def status(self) -> dict:
        """
        Get current migration status.

        :return: Dictionary with migration status information.
        """
        applied = self.get_applied_migrations()
        pending = self.get_pending_migrations()

        return {
            "applied_count": len(applied),
            "pending_count": len(pending),
            "latest_applied": applied[-1] if applied else None,
            "next_pending": pending[0][0] if pending else None,
            "applied_versions": applied,
            "pending_versions": [v for v, _ in pending],
        }

    def create_migration(self, name: str, content: str = "") -> Path:
        """
        Create a new migration file with the next version number.

        :param name: Descriptive name for the migration.
        :param content: Optional SQL content for the migration.
        :return: Path to the created migration file.
        """
        # Find next version number
        existing_files = list(self.migrations_path.glob("*.sql"))
        if existing_files:
            versions = []
            for f in existing_files:
                try:
                    version_str = f.stem.split("_")[0]
                    versions.append(int(version_str))
                except (IndexError, ValueError):
                    continue
            next_version = max(versions) + 1 if versions else 1
        else:
            next_version = 1

        # Format version with leading zeros
        version_str = f"{next_version:03d}"

        # Create filename
        safe_name = name.lower().replace(" ", "_").replace("-", "_")
        filename = f"{version_str}_{safe_name}.sql"
        filepath = self.migrations_path / filename

        # Write content
        if not content:
            content = f"-- Migration: {name}\n-- Version: {version_str}\n-- Date: {datetime.now(timezone.utc).isoformat()}\n\n"

        with open(filepath, "w") as f:
            f.write(content)

        self.logger.info(f"Created migration: {filepath}")
        return filepath
