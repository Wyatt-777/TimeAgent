from datetime import datetime, timedelta, timezone

from alerts.model import Alert, AlertStatus
from alerts.service import AlertService
from alerts.store import AlertStore
from core.event import Event, EventType, Priority
from notifications.manager import NotificationManager
from notifications.windows import NotificationRequest, WindowsNotificationAdapter


def event(event_id: str = "evt_1") -> Event:
    return Event(
        id=event_id,
        type=EventType.TEST_FAILED_REPEATEDLY,
        source="test_failure_tracker",
        priority=Priority.IMPORTANT,
        data={"project_path": "D:/project", "test_group": "unit", "consecutive_failures": 3},
    )


def test_windows_adapter_supports_injected_backend() -> None:
    received = []
    adapter = WindowsNotificationAdapter(backend=received.append)

    result = adapter.send(NotificationRequest("Title", "Message"))

    assert result.delivered is True
    assert result.backend == "custom"
    assert received == [NotificationRequest("Title", "Message")]


def test_notification_failure_keeps_alert_new(tmp_path) -> None:
    with AlertStore(tmp_path / "alerts.db") as store:
        service = AlertService(store)
        created = service.create_from_event(event())
        manager = NotificationManager(
            service,
            adapter=WindowsNotificationAdapter(backend=lambda _: (_ for _ in ()).throw(RuntimeError("offline"))),
        )

        result = manager.deliver(created.alert)

        assert result.sent is False
        assert result.reason == "notification_failed"
        assert store.get(created.alert.id).status is AlertStatus.NEW


def test_successful_notification_marks_alert_notified(tmp_path) -> None:
    now = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    with AlertStore(tmp_path / "alerts.db") as store:
        service = AlertService(store)
        created = service.create_from_event(event(), now=now)
        manager = NotificationManager(service, adapter=WindowsNotificationAdapter(backend=lambda _: None))

        result = manager.deliver(created.alert, now=now)

        assert result.sent is True
        assert store.get(created.alert.id).status is AlertStatus.NOTIFIED
        assert manager.deliver(created.alert, now=now + timedelta(seconds=1)).sent is False


def test_follow_up_notification_bypasses_cooldown_and_preserves_status(tmp_path) -> None:
    now = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    received = []
    with AlertStore(tmp_path / "alerts.db") as store:
        service = AlertService(store)
        created = service.create_from_event(event(), now=now)
        manager = NotificationManager(
            service,
            adapter=WindowsNotificationAdapter(backend=received.append),
        )
        manager.deliver(created.alert, now=now)
        investigating = store.update_status(created.alert.id, AlertStatus.INVESTIGATING)

        result = manager.deliver_follow_up(
            investigating,
            title="Investigation complete",
            message="A likely root cause was found.",
        )

        assert result.sent is True
        assert received[-1] == NotificationRequest(
            "Investigation complete",
            "A likely root cause was found.",
        )
        assert store.get(created.alert.id).status is AlertStatus.INVESTIGATING
