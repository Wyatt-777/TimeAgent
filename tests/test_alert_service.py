from datetime import datetime, time, timedelta, timezone

from alerts.policy import Cooldown, NotificationPolicy
from alerts.service import AlertService
from alerts.store import AlertStore
from core.event import Event, EventType, Priority


def repeated_event(event_id: str = "evt_1") -> Event:
    return Event(
        id=event_id,
        type=EventType.TEST_FAILED_REPEATEDLY,
        source="test_failure_tracker",
        priority=Priority.IMPORTANT,
        data={"project_path": "D:/project", "test_group": "unit", "consecutive_failures": 3},
    )


def test_alert_service_creates_and_deduplicates_alerts(tmp_path) -> None:
    now = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    with AlertStore(tmp_path / "alerts.db") as store:
        service = AlertService(store)
        first = service.create_from_event(repeated_event(), now=now)
        duplicate = service.create_from_event(repeated_event("evt_2"), now=now + timedelta(seconds=30))

        assert first.created is True
        assert duplicate.created is False
        assert duplicate.reason == "duplicate_within_window"
        assert store.list() == [first.alert]


def test_alert_service_allows_new_alert_after_dedup_window(tmp_path) -> None:
    now = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    with AlertStore(tmp_path / "alerts.db") as store:
        service = AlertService(store)
        service.create_from_event(repeated_event(), now=now)
        result = service.create_from_event(repeated_event("evt_2"), now=now + timedelta(minutes=11))

        assert result.created is True


def test_policy_quiet_hours_and_critical_bypass() -> None:
    policy = NotificationPolicy(
        quiet_hours_enabled=True,
        quiet_hours_start=time(22, 0),
        quiet_hours_end=time(7, 0),
    )
    now = datetime(2026, 8, 26, 23, 0, tzinfo=timezone.utc)
    alert = repeated_event().to_dict()
    from alerts.model import Alert

    normal = Alert.from_mapping({**alert, "id": "a1", "created_at": now.isoformat(), "priority": int(Priority.IMPORTANT), "title": "x", "summary": "x"})
    critical = Alert.from_mapping({**normal.to_dict(), "id": "a2", "priority": int(Priority.CRITICAL)})

    assert policy.should_notify(normal, now=now) is False
    assert policy.should_notify(critical, now=now) is True


def test_cooldown_blocks_until_interval() -> None:
    cooldown = Cooldown(seconds=60)
    now = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)

    assert cooldown.available("key", now=now) is True
    cooldown.mark_sent("key", now=now)
    assert cooldown.available("key", now=now + timedelta(seconds=30)) is False
    assert cooldown.available("key", now=now + timedelta(seconds=60)) is True
