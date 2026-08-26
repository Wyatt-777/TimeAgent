"""Typed alert records stored by the local agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from core.event import Priority


class AlertStatus(str, Enum):
    NEW = "NEW"
    NOTIFIED = "NOTIFIED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"


@dataclass(frozen=True, slots=True)
class Alert:
    event_id: str | None
    created_at: datetime
    priority: Priority
    title: str
    summary: str
    status: AlertStatus = AlertStatus.NEW
    dedup_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"alert_{uuid4().hex}")

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Alert id must not be empty")
        if self.created_at.tzinfo is None:
            raise ValueError("Alert created_at must be timezone-aware")
        if not isinstance(self.priority, Priority):
            raise TypeError("Alert priority must be a Priority")
        if not isinstance(self.status, AlertStatus):
            raise TypeError("Alert status must be an AlertStatus")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("Alert title must be a non-empty string")
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise ValueError("Alert summary must be a non-empty string")
        if not isinstance(self.metadata, dict):
            raise TypeError("Alert metadata must be a dictionary")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_id": self.event_id,
            "created_at": self.created_at.isoformat(),
            "priority": int(self.priority),
            "title": self.title,
            "summary": self.summary,
            "status": self.status.value,
            "dedup_key": self.dedup_key,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "Alert":
        try:
            created_at = payload["created_at"]
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            return cls(
                id=str(payload["id"]),
                event_id=payload.get("event_id"),
                created_at=created_at,
                priority=Priority(payload["priority"]),
                title=str(payload["title"]),
                summary=str(payload["summary"]),
                status=AlertStatus(payload.get("status", AlertStatus.NEW)),
                dedup_key=payload.get("dedup_key"),
                metadata=dict(payload.get("metadata", {})),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid alert representation") from exc
