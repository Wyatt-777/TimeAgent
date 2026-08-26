from datetime import datetime, timezone

from alerts.inbox import AlertInbox
from alerts.model import Alert, AlertStatus
from alerts.store import AlertStore
from core.event import Priority


def alert(alert_id: str, status: AlertStatus = AlertStatus.NEW) -> Alert:
    return Alert(
        id=alert_id,
        event_id=None,
        created_at=datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc),
        priority=Priority.IMPORTANT,
        title="Attention",
        summary="Something needs review.",
        status=status,
    )


def test_inbox_lists_pending_and_transitions_status(tmp_path) -> None:
    with AlertStore(tmp_path / "alerts.db") as store:
        store.insert(alert("pending"))
        store.insert(alert("resolved", AlertStatus.RESOLVED))
        inbox = AlertInbox(store)

        assert [item.id for item in inbox.pending()] == ["pending"]
        assert inbox.acknowledge("pending").status is AlertStatus.ACKNOWLEDGED
        assert inbox.investigate("pending").status is AlertStatus.INVESTIGATING
        assert inbox.resolve("pending").status is AlertStatus.RESOLVED
        assert inbox.pending() == []
