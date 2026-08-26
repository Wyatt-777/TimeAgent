"""Small, explicit SQLite migration runner for the local runtime."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence


class MigrationError(RuntimeError):
    """Raised when the database schema cannot be migrated safely."""


MigrationApply = Callable[[sqlite3.Connection], None]


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    apply: MigrationApply


class MigrationRunner:
    """Apply each migration once, in ascending version order."""

    def __init__(self, migrations: Sequence[Migration]) -> None:
        self.migrations = tuple(sorted(migrations, key=lambda item: item.version))
        self._validate()

    def apply(self, connection: sqlite3.Connection) -> int:
        """Apply pending migrations and return the resulting schema version."""
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {
            int(row[0])
            for row in connection.execute("SELECT version FROM schema_migrations")
        }
        with connection:
            for migration in self.migrations:
                if migration.version in applied:
                    continue
                try:
                    migration.apply(connection)
                    connection.execute(
                        """
                        INSERT INTO schema_migrations (version, name, applied_at)
                        VALUES (?, ?, ?)
                        """,
                        (
                            migration.version,
                            migration.name,
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                except sqlite3.DatabaseError as exc:
                    raise MigrationError(
                        f"migration {migration.version} ({migration.name}) failed"
                    ) from exc
        return self.current_version(connection)

    def current_version(self, connection: sqlite3.Connection) -> int:
        row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return int(row[0] or 0)

    def _validate(self) -> None:
        versions = [migration.version for migration in self.migrations]
        if any(version <= 0 for version in versions):
            raise MigrationError("migration versions must be positive")
        if len(set(versions)) != len(versions):
            raise MigrationError("migration versions must be unique")
        if any(not migration.name.strip() for migration in self.migrations):
            raise MigrationError("migration names must not be empty")


def _create_events_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            source TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            priority INTEGER NOT NULL,
            data TEXT NOT NULL,
            metadata TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_source ON events(source)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_priority ON events(priority)")


DEFAULT_MIGRATIONS = (
    Migration(1, "create_events_schema", _create_events_schema),
)
