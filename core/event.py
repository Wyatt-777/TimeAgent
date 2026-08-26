"""Canonical event model shared by all sensors and runtime services."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any, Mapping
from uuid import uuid4


class EventType(str, Enum):
    PROCESS_STARTED = "PROCESS_STARTED"
    PROCESS_STOPPED = "PROCESS_STOPPED"
    FILE_CREATED = "FILE_CREATED"
    FILE_MODIFIED = "FILE_MODIFIED"
    FILE_DELETED = "FILE_DELETED"
    FILE_MOVED = "FILE_MOVED"
    ACTIVE_WINDOW_CHANGED = "ACTIVE_WINDOW_CHANGED"
    SYSTEM_CPU_HIGH = "SYSTEM_CPU_HIGH"
    SYSTEM_MEMORY_HIGH = "SYSTEM_MEMORY_HIGH"
    SYSTEM_DISK_LOW = "SYSTEM_DISK_LOW"
    AGENT_STARTED = "AGENT_STARTED"
    AGENT_STOPPED = "AGENT_STOPPED"
    AGENT_ERROR = "AGENT_ERROR"
    CODING_SESSION_STARTED = "CODING_SESSION_STARTED"
    CODING_SESSION_FINISHED = "CODING_SESSION_FINISHED"
    TEST_FAILED = "TEST_FAILED"
    TEST_FAILED_REPEATEDLY = "TEST_FAILED_REPEATEDLY"


class Priority(IntEnum):
    DEBUG = 10
    NORMAL = 20
    IMPORTANT = 30
    CRITICAL = 40


@dataclass(slots=True)
class Event:
    """A normalized, JSON-serializable event from the local runtime."""

    type: EventType | str
    source: str
    priority: Priority | int = Priority.NORMAL
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"evt_{uuid4().hex}")
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        try:
            self.type = EventType(self.type)
        except ValueError as exc:
            raise ValueError(f"Unknown event type: {self.type}") from exc
        try:
            self.priority = Priority(self.priority)
        except ValueError as exc:
            raise ValueError(f"Unknown event priority: {self.priority}") from exc
        if not self.id.strip():
            raise ValueError("Event id must not be empty")
        if not self.source.strip():
            raise ValueError("Event source must not be empty")
        if self.timestamp.tzinfo is None:
            raise ValueError("Event timestamp must be timezone-aware")
        if not isinstance(self.data, dict) or not isinstance(self.metadata, dict):
            raise ValueError("Event data and metadata must be dictionaries")

    def to_dict(self) -> dict[str, Any]:
        """Return the stable storage/API representation of this event."""
        return {
            "id": self.id,
            "type": self.type.value,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "priority": int(self.priority),
            "data": self.data,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Serialize the event without losing non-ASCII user data."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Event":
        """Recreate an Event from its dictionary representation."""
        try:
            timestamp = value["timestamp"]
            if isinstance(timestamp, str) and timestamp.endswith("Z"):
                timestamp = timestamp[:-1] + "+00:00"
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)
            return cls(
                id=str(value["id"]),
                type=value["type"],
                source=str(value["source"]),
                timestamp=timestamp,
                priority=value["priority"],
                data=dict(value.get("data", {})),
                metadata=dict(value.get("metadata", {})),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid event representation") from exc

    @classmethod
    def from_json(cls, value: str) -> "Event":
        """Recreate an Event from JSON."""
        try:
            raw = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid event JSON") from exc
        if not isinstance(raw, Mapping):
            raise ValueError("Event JSON must contain an object")
        return cls.from_dict(raw)
