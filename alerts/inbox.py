"""Small Alert Inbox API for local UI and future read-only integrations."""

from __future__ import annotations

from .model import Alert, AlertStatus
from .store import AlertStore


class AlertInbox:
    def __init__(self, store: AlertStore) -> None:
        self.store = store

    def pending(self, *, limit: int = 100) -> list[Alert]:
        return self.store.list_pending(limit=limit)

    def get(self, alert_id: str) -> Alert | None:
        return self.store.get(alert_id)

    def acknowledge(self, alert_id: str) -> Alert:
        return self.store.update_status(alert_id, AlertStatus.ACKNOWLEDGED)

    def investigate(self, alert_id: str) -> Alert:
        return self.store.update_status(alert_id, AlertStatus.INVESTIGATING)

    def resolve(self, alert_id: str) -> Alert:
        return self.store.update_status(alert_id, AlertStatus.RESOLVED)

    def ignore(self, alert_id: str) -> Alert:
        return self.store.update_status(alert_id, AlertStatus.IGNORED)
