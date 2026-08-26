import sqlite3
from datetime import datetime, timezone

import pytest

from core.event import Event, EventType, Priority
from core.event_store import EventStore


def test_store_initializes_inserts_and_queries_unicode_events(tmp_path) -> None:
    database = tmp_path / "nested" / "agent.db"
    first = Event(
        id="evt_first",
        type=EventType.FILE_MODIFIED,
        source="file_monitor",
        timestamp=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
        data={"path": "D:/项目/main.py", "说明": "修改"},
    )
    second = Event(
        id="evt_second",
        type=EventType.PROCESS_STOPPED,
        source="process_monitor",
        timestamp=datetime(2026, 8, 25, 12, 1, tzinfo=timezone.utc),
        priority=Priority.IMPORTANT,
        data={"name": "Code.exe"},
    )

    with EventStore(database) as store:
        store.insert(first)
        store.insert(second)

        assert store.count() == 2
        assert store.query(event_type=EventType.FILE_MODIFIED) == [first]
        assert store.query(min_priority=Priority.IMPORTANT) == [second]
        assert store.query(source="process_monitor") == [second]
        assert store.query(since=first.timestamp, until=first.timestamp) == [first]

    assert database.exists()


def test_store_creates_expected_indexes(tmp_path) -> None:
    with EventStore(tmp_path / "agent.db") as store:
        assert store.schema_version == 1
        rows = store._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_events_%'"
        ).fetchall()

    assert {row[0] for row in rows} == {
        "idx_events_timestamp",
        "idx_events_type",
        "idx_events_source",
        "idx_events_priority",
    }


def test_existing_database_is_migrated_without_losing_events(tmp_path) -> None:
    database = tmp_path / "legacy.db"
    first = Event(type=EventType.AGENT_STARTED, source="legacy")
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE events (
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
        connection.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                first.id,
                first.type.value,
                first.source,
                first.timestamp.isoformat(),
                int(first.priority),
                "{}",
                "{}",
            ),
        )

    with EventStore(database) as store:
        assert store.schema_version == 1
        assert store.count() == 1
        assert store.query()[0].id == first.id


def test_store_rejects_invalid_queries_and_duplicate_ids(tmp_path) -> None:
    event = Event(type=EventType.AGENT_STARTED, source="test")
    with EventStore(tmp_path / "agent.db") as store:
        store.insert(event)
        with pytest.raises(sqlite3.IntegrityError):
            store.insert(event)
        with pytest.raises(ValueError, match="limit"):
            store.query(limit=0)
        with pytest.raises(ValueError, match="timezone-aware"):
            store.query(since=datetime.now())
