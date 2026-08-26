"""SQLite persistence for normalized runtime events."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

from .event import Event, EventType, Priority
from .migrations import DEFAULT_MIGRATIONS, MigrationRunner


class EventStore:
    """Persist and query events in a local SQLite database."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._connection = sqlite3.connect(
            self.database_path,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._migrations = MigrationRunner(DEFAULT_MIGRATIONS)
            self._migrations.apply(self._connection)

    @property
    def schema_version(self) -> int:
        """Return the applied schema version for diagnostics and tests."""
        with self._lock:
            return self._migrations.current_version(self._connection)

    def insert(self, event: Event) -> None:
        """Insert one event, preserving its canonical JSON representation."""
        if not isinstance(event, Event):
            raise TypeError("EventStore accepts Event instances only")
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO events (id, type, source, timestamp, priority, data, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.type.value,
                    event.source,
                    event.timestamp.isoformat(),
                    int(event.priority),
                    _json_dumps(event.data),
                    _json_dumps(event.metadata),
                ),
            )

    def insert_if_absent(self, event: Event) -> bool:
        """Insert an event unless its id already exists; return whether it was new."""
        if not isinstance(event, Event):
            raise TypeError("EventStore accepts Event instances only")
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT OR IGNORE INTO events (id, type, source, timestamp, priority, data, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.type.value,
                    event.source,
                    event.timestamp.isoformat(),
                    int(event.priority),
                    _json_dumps(event.data),
                    _json_dumps(event.metadata),
                ),
            )
        return cursor.rowcount == 1

    def query(
        self,
        *,
        limit: int = 100,
        event_type: EventType | str | None = None,
        source: str | None = None,
        min_priority: Priority | int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Event]:
        """Return newest matching events, ordered from oldest to newest."""
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        clauses: list[str] = []
        parameters: list[Any] = []
        if event_type is not None:
            clauses.append("type = ?")
            parameters.append(EventType(event_type).value)
        if source is not None:
            clauses.append("source = ?")
            parameters.append(source)
        if min_priority is not None:
            clauses.append("priority >= ?")
            parameters.append(int(Priority(min_priority)))
        if since is not None:
            clauses.append("timestamp >= ?")
            parameters.append(_timestamp(since))
        if until is not None:
            clauses.append("timestamp <= ?")
            parameters.append(_timestamp(until))

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT id, type, source, timestamp, priority, data, metadata
            FROM events
            {where}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        parameters.append(limit)
        with self._lock:
            rows = self._connection.execute(sql, parameters).fetchall()
        return [self._row_to_event(row) for row in reversed(rows)]

    def count(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS count FROM events").fetchone()
        return int(row["count"])

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> Event:
        return Event(
            id=row["id"],
            type=row["type"],
            source=row["source"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            priority=row["priority"],
            data=_json_loads(row["data"]),
            metadata=_json_loads(row["metadata"]),
        )


def _json_dumps(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str) -> dict[str, Any]:
    import json

    result = json.loads(value)
    if not isinstance(result, dict):
        raise ValueError("Stored event JSON must be an object")
    return result


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Query timestamps must be timezone-aware")
    return value.isoformat()
