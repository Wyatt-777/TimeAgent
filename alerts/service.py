"""Create Alert Inbox records from important normalized events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from core.event import Event, Priority

from .model import Alert
from .policy import Cooldown, ImportanceEngine, NotificationPolicy, event_dedup_key
from .store import AlertStore


@dataclass(frozen=True, slots=True)
class AlertCreationResult:
    alert: Alert | None
    created: bool
    reason: str


class AlertService:
    """Apply importance and deduplication before writing an alert."""

    def __init__(
        self,
        store: AlertStore,
        *,
        importance: ImportanceEngine | None = None,
        policy: NotificationPolicy | None = None,
        cooldown: Cooldown | None = None,
    ) -> None:
        self.store = store
        self.importance = importance or ImportanceEngine()
        self.policy = policy or NotificationPolicy()
        self.cooldown = cooldown or Cooldown(self.policy.cooldown_seconds)

    def create_from_event(
        self,
        event: Event,
        *,
        now: datetime | None = None,
    ) -> AlertCreationResult:
        if not isinstance(event, Event):
            raise TypeError("event must be an Event")
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        priority = self.importance.classify(event)
        if priority < self.policy.minimum_priority:
            return AlertCreationResult(None, False, "below_minimum_priority")

        dedup_key = event_dedup_key(event)
        existing = self.store.find_recent(
            dedup_key,
            since=now - timedelta(seconds=self.policy.dedup_window_seconds),
        )
        if existing is not None:
            return AlertCreationResult(existing, False, "duplicate_within_window")

        alert = Alert(
            event_id=event.id,
            created_at=now,
            priority=priority,
            title=_title(event),
            summary=_summary(event),
            dedup_key=dedup_key,
            metadata={"source": event.source, "event_type": event.type.value},
        )
        self.store.insert(alert)
        return AlertCreationResult(alert, True, "created")

    def should_notify(self, alert: Alert, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return self.policy.should_notify(alert, now=now) and self.cooldown.available(
            alert.dedup_key or alert.id,
            now=now,
        )

    def mark_notified(self, alert: Alert, *, now: datetime | None = None) -> Alert:
        now = now or datetime.now(timezone.utc)
        key = alert.dedup_key or alert.id
        self.cooldown.mark_sent(key, now=now)
        return self.store.update_status(alert.id, "NOTIFIED")


def _title(event: Event) -> str:
    titles = {
        "TEST_FAILED_REPEATEDLY": "Repeated test failures",
        "SYSTEM_CPU_HIGH": "High CPU usage",
        "SYSTEM_MEMORY_HIGH": "High memory usage",
        "SYSTEM_DISK_LOW": "Low disk space",
        "AGENT_ERROR": "Local Agent error",
    }
    return titles.get(event.type.value, event.type.value.replace("_", " ").title())


def _summary(event: Event) -> str:
    summary = event.data.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary
    if event.type.value == "TEST_FAILED_REPEATEDLY":
        count = event.data.get("consecutive_failures", "multiple")
        return f"Tests have failed {count} times within the configured window."
    return f"{event.type.value} reported by {event.source}."
