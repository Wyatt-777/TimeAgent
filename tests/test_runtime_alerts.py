from config.settings import Settings, StorageSettings
from core.event import Event, EventType, Priority
from core.lifecycle import Runtime


def test_runtime_routes_alert_events_to_alert_store(tmp_path) -> None:
    runtime = Runtime(
        Settings(storage=StorageSettings(sqlite_path=str(tmp_path / "agent.db"))),
        sensors=(),
    )
    runtime.notification_manager.adapter._backend = lambda _: None

    runtime._handle_alert(
        Event(
            type=EventType.TEST_FAILED_REPEATEDLY,
            source="test_failure_tracker",
            priority=Priority.IMPORTANT,
            data={"project_path": "D:/project", "test_group": "unit", "consecutive_failures": 3},
        )
    )

    pending = runtime.alert_inbox.pending()
    assert len(pending) == 1
    assert pending[0].status.value == "NOTIFIED"
    assert runtime.investigation_coordinator.pending(pending[0].id) is not None
    runtime.shutdown()
