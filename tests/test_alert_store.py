from datetime import datetime, timezone

import pytest

from alerts.model import Alert, AlertStatus
from alerts.store import AlertStore
from core.event import Priority


def make_alert(alert_id: str = "alert_1", *, priority: Priority = Priority.IMPORTANT) -> Alert:
    return Alert(
        id=alert_id,
        event_id="evt_1",
        created_at=datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc),
        priority=priority,
        title="Repeated test failures",
        summary="Tests failed three times.",
        dedup_key="tests:D:/project",
        metadata={"project_path": "D:/project"},
    )


def test_alert_store_persists_queries_and_status_changes(tmp_path) -> None:
    database = tmp_path / "alerts.db"
    with AlertStore(database) as store:
        alert = make_alert()
        store.insert(alert)

        assert store.schema_version == 2
        assert store.get(alert.id) == alert
        assert store.list(status=AlertStatus.NEW) == [alert]
        updated = store.update_status(alert.id, AlertStatus.ACKNOWLEDGED)

    assert updated.status is AlertStatus.ACKNOWLEDGED
    with AlertStore(database) as reopened:
        assert reopened.list(status=AlertStatus.ACKNOWLEDGED)[0].id == alert.id


def test_alert_store_filters_priority_and_rejects_unknown_ids(tmp_path) -> None:
    with AlertStore(tmp_path / "alerts.db") as store:
        store.insert(make_alert("low", priority=Priority.NORMAL))
        store.insert(make_alert("high", priority=Priority.CRITICAL))

        assert [alert.id for alert in store.list(min_priority=Priority.IMPORTANT)] == ["high"]
        with pytest.raises(KeyError):
            store.update_status("missing", AlertStatus.IGNORED)


def test_alert_model_round_trips_unicode() -> None:
    alert = make_alert()
    restored = Alert.from_mapping(alert.to_dict())

    assert restored == alert
