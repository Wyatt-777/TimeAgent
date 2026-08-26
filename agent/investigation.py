"""Models and bounded context packages for read-only investigations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from core.event import Event


class InvestigationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True)
class InvestigationTask:
    """A single bounded investigation request tied to one trigger event."""

    trigger_event_id: str
    project_path: str
    reason: str
    test_group: str = "default"
    task_id: str = field(default_factory=lambda: f"investigation_{uuid4().hex}")
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: InvestigationStatus = InvestigationStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        for name in ("task_id", "trigger_event_id", "project_path", "reason", "test_group"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        for name in ("started_at", "completed_at"):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")

    def start(self, *, at: datetime | None = None) -> "InvestigationTask":
        if self.status is not InvestigationStatus.PENDING:
            raise ValueError("only pending investigations can start")
        timestamp = at or datetime.now(timezone.utc)
        _validate_timestamp(timestamp)
        return replace(self, status=InvestigationStatus.RUNNING, started_at=timestamp, error=None)

    def complete(self, *, at: datetime | None = None) -> "InvestigationTask":
        return self._finish(InvestigationStatus.COMPLETED, at=at)

    def fail(self, error: str, *, at: datetime | None = None) -> "InvestigationTask":
        if not isinstance(error, str) or not error.strip():
            raise ValueError("error must be a non-empty string")
        return self._finish(InvestigationStatus.FAILED, at=at, error=error)

    def timeout(self, *, at: datetime | None = None) -> "InvestigationTask":
        return self._finish(InvestigationStatus.TIMED_OUT, at=at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "trigger_event_id": self.trigger_event_id,
            "project_path": self.project_path,
            "reason": self.reason,
            "test_group": self.test_group,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }

    def _finish(
        self,
        status: InvestigationStatus,
        *,
        at: datetime | None,
        error: str | None = None,
    ) -> "InvestigationTask":
        if self.status is not InvestigationStatus.RUNNING:
            raise ValueError("only running investigations can finish")
        timestamp = at or datetime.now(timezone.utc)
        _validate_timestamp(timestamp)
        return replace(self, status=status, completed_at=timestamp, error=error)


@dataclass(frozen=True, slots=True)
class InvestigationContextPackage:
    """Bounded, JSON-serializable facts supplied to a read-only investigator."""

    task: InvestigationTask
    trigger_event: Event
    recent_events: tuple[Event, ...] = ()
    project_state: dict[str, Any] = field(default_factory=dict)
    git_status: dict[str, Any] = field(default_factory=dict)
    diff_stat: dict[str, Any] = field(default_factory=dict)
    test_result: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.task, InvestigationTask):
            raise TypeError("task must be an InvestigationTask")
        if not isinstance(self.trigger_event, Event):
            raise TypeError("trigger_event must be an Event")
        if self.task.trigger_event_id != self.trigger_event.id:
            raise ValueError("task and trigger_event ids do not match")
        if len(self.recent_events) > 100:
            raise ValueError("recent_events must contain at most 100 events")

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task.to_dict(),
            "trigger_event": self.trigger_event.to_dict(),
            "recent_events": [event.to_dict() for event in self.recent_events],
            "project_state": self.project_state,
            "git_status": self.git_status,
            "diff_stat": self.diff_stat,
            "test_result": self.test_result,
        }

    def to_prompt(self) -> str:
        instructions = (
            "Perform a read-only investigation. Inspect the supplied facts and, if needed, "
            "read the explicitly selected workspace. Do not edit files, run destructive commands, "
            "commit, push, install packages, or send messages. Return a concise diagnosis and "
            "recommended next step as JSON or plain text."
        )
        return instructions + "\n\nCONTEXT:\n" + json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True
        )


def _validate_timestamp(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
