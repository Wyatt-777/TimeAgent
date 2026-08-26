from datetime import datetime, timedelta, timezone

from agent.context_builder import ContextBuilder
from core.event import Event, EventType
from core.event_store import EventStore


def test_context_builder_collects_recent_events_and_optional_context(tmp_path) -> None:
    timestamp = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
    earlier = Event(
        id="evt_earlier",
        type=EventType.FILE_MODIFIED,
        source="file_monitor",
        timestamp=timestamp - timedelta(minutes=5),
        data={"path": "D:/项目/main.py"},
    )
    trigger = Event(
        id="evt_trigger",
        type=EventType.PROCESS_STOPPED,
        source="process_monitor",
        timestamp=timestamp,
        data={"name": "Code.exe"},
    )

    with EventStore(tmp_path / "agent.db") as store:
        store.insert(earlier)
        store.insert(trigger)
        context = ContextBuilder(store).build(
            trigger,
            project_state={"path": "D:/项目"},
            git_status={"modified": 1},
            agent_config={"mode": "read_only"},
        )

    assert [event.id for event in context.recent_events] == ["evt_earlier", "evt_trigger"]
    assert context.project_state["path"] == "D:/项目"
    assert context.git_status == {"modified": 1}
    assert "D:/项目" in context.to_json()


def test_context_builder_includes_unstored_trigger(tmp_path) -> None:
    trigger = Event(type=EventType.SYSTEM_DISK_LOW, source="system_monitor")

    with EventStore(tmp_path / "agent.db") as store:
        context = ContextBuilder(store).build(trigger)

    assert context.recent_events == (trigger,)


def test_context_builder_validates_limits(tmp_path) -> None:
    with EventStore(tmp_path / "agent.db") as store:
        try:
            ContextBuilder(store, recent_minutes=0)
        except ValueError as exc:
            assert "recent_minutes" in str(exc)
        else:
            raise AssertionError("Expected recent_minutes validation")
