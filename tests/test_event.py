from datetime import datetime, timezone

import pytest

from core.event import Event, EventType, Priority


def test_event_defaults_and_json_round_trip() -> None:
    event = Event(
        type=EventType.FILE_MODIFIED,
        source="file_monitor",
        data={"path": "D:/项目/main.py", "count": 2},
    )

    restored = Event.from_json(event.to_json())

    assert event.id.startswith("evt_")
    assert event.timestamp.tzinfo is not None
    assert event.priority == Priority.NORMAL
    assert restored.to_dict() == event.to_dict()


def test_event_serializes_priority_and_timestamp() -> None:
    event = Event(
        id="evt_test",
        type="PROCESS_STARTED",
        source="process_monitor",
        timestamp=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
        priority=Priority.IMPORTANT,
        data={"pid": 123},
    )

    payload = event.to_dict()

    assert payload["type"] == "PROCESS_STARTED"
    assert payload["priority"] == 30
    assert payload["timestamp"] == "2026-08-25T12:00:00+00:00"


def test_event_rejects_unknown_type_and_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="Unknown event type"):
        Event(type="UNKNOWN", source="test")

    with pytest.raises(ValueError, match="timezone-aware"):
        Event(
            type=EventType.AGENT_STARTED,
            source="lifecycle",
            timestamp=datetime(2026, 8, 25, 12, 0),
        )
