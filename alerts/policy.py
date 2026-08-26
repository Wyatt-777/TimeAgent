"""Importance, notification policy, deduplication, and cooldown helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from threading import Lock

from core.event import Event, EventType, Priority

from .model import Alert


class ImportanceEngine:
    """Normalize event importance without using an LLM."""

    def classify(self, event: Event) -> Priority:
        if not isinstance(event, Event):
            raise TypeError("event must be an Event")
        if event.type is EventType.TEST_FAILED_REPEATEDLY:
            return max(Priority.IMPORTANT, event.priority)
        return Priority(event.priority)


@dataclass(frozen=True, slots=True)
class NotificationPolicy:
    enabled: bool = True
    minimum_priority: Priority = Priority.IMPORTANT
    cooldown_seconds: float = 300.0
    dedup_window_seconds: float = 600.0
    quiet_hours_enabled: bool = False
    quiet_hours_start: time = time(0, 30)
    quiet_hours_end: time = time(8, 30)

    def __post_init__(self) -> None:
        if not isinstance(self.minimum_priority, Priority):
            raise TypeError("minimum_priority must be a Priority")
        if self.cooldown_seconds < 0 or self.dedup_window_seconds < 0:
            raise ValueError("cooldown and dedup windows cannot be negative")

    def should_notify(self, alert: Alert, *, now: datetime) -> bool:
        if not self.enabled or alert.priority < self.minimum_priority:
            return False
        if alert.priority >= Priority.CRITICAL:
            return True
        if not self.quiet_hours_enabled:
            return True
        current = now.timetz().replace(tzinfo=None)
        if self.quiet_hours_start <= self.quiet_hours_end:
            return not self.quiet_hours_start <= current < self.quiet_hours_end
        return not (current >= self.quiet_hours_start or current < self.quiet_hours_end)


class Cooldown:
    """In-memory notification cooldown keyed by deduplication key."""

    def __init__(self, seconds: float = 300.0) -> None:
        if seconds < 0:
            raise ValueError("seconds cannot be negative")
        self.seconds = seconds
        self._last_sent: dict[str, datetime] = {}
        self._lock = Lock()

    def available(self, key: str, *, now: datetime) -> bool:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        with self._lock:
            previous = self._last_sent.get(key)
        return previous is None or now - previous >= timedelta(seconds=self.seconds)

    def mark_sent(self, key: str, *, now: datetime) -> None:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        with self._lock:
            self._last_sent[key] = now


def event_dedup_key(event: Event) -> str:
    """Build a stable key from event identity fields, without raw payloads."""
    if not isinstance(event, Event):
        raise TypeError("event must be an Event")
    project = event.data.get("project_path") or "<unresolved-project>"
    group = event.data.get("test_group") or event.source
    return f"{event.type.value}:{project}:{group}"
