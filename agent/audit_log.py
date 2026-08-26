"""Append-only audit records for agent decisions and action attempts."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .approval import ApprovalResult
from .decision import StructuredDecision


class AuditLogError(RuntimeError):
    """Raised when an audit record cannot be persisted or decoded."""


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """A privacy-conscious record of one agent decision attempt."""

    record_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    actor: str = "agent"
    trigger: str = "agent_decision"
    action: str | None = None
    approval_status: str = "unknown"
    execution_status: str = "not_started"
    summary: str = ""
    approvals: tuple[str, ...] = ()
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
            "actor": self.actor,
            "trigger": self.trigger,
            "action": self.action,
            "approval_status": self.approval_status,
            "execution_status": self.execution_status,
            "summary": self.summary,
            "approvals": list(self.approvals),
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AuditRecord":
        try:
            timestamp = datetime.fromisoformat(str(payload["timestamp"]))
            approvals = tuple(str(item) for item in payload.get("approvals", []))
            return cls(
                record_id=str(payload["record_id"]),
                timestamp=timestamp,
                actor=str(payload["actor"]),
                trigger=str(payload["trigger"]),
                action=payload.get("action"),
                approval_status=str(payload["approval_status"]),
                execution_status=str(payload["execution_status"]),
                summary=str(payload.get("summary", "")),
                approvals=approvals,
                error=payload.get("error"),
                metadata=dict(payload.get("metadata", {})),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AuditLogError("invalid audit record") from exc


class AuditLog:
    """Keep records in memory and optionally append them to a JSONL file."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._records: list[AuditRecord] = []
        self._lock = threading.Lock()
        if self.path is not None and self.path.exists():
            self._load()

    def append(self, record: AuditRecord) -> AuditRecord:
        if not isinstance(record, AuditRecord):
            raise TypeError("record must be an AuditRecord")
        line = json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True)
        with self._lock:
            if self.path is not None:
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    with self.path.open("a", encoding="utf-8") as handle:
                        handle.write(line + "\n")
                except OSError as exc:
                    raise AuditLogError(f"unable to append audit record: {self.path}") from exc
            self._records.append(record)
        return record

    def record_execution(
        self,
        *,
        decision: StructuredDecision,
        approval: ApprovalResult,
        execution_status: str,
        trigger: str = "agent_decision",
        actor: str = "agent",
        error: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> AuditRecord:
        if not isinstance(decision, StructuredDecision):
            raise TypeError("decision must be a StructuredDecision")
        if not isinstance(approval, ApprovalResult):
            raise TypeError("approval must be an ApprovalResult")
        return self.append(
            AuditRecord(
                actor=actor,
                trigger=trigger,
                action=approval.action,
                approval_status=approval.status.value,
                execution_status=str(execution_status),
                summary=decision.summary,
                approvals=("required",) if decision.requires_approval else (),
                error=error,
                metadata=dict(metadata or {}),
            )
        )

    def record_investigation(
        self,
        *,
        task: Any,
        status: str,
        result: Any = None,
        error: str | None = None,
    ) -> AuditRecord:
        """Record investigation lifecycle without persisting raw model output."""
        if not hasattr(task, "task_id") or not hasattr(task, "trigger_event_id"):
            raise TypeError("task must be an InvestigationTask-like object")
        metadata: dict[str, Any] = {
            "task_id": task.task_id,
            "trigger_event_id": task.trigger_event_id,
            "project_path": task.project_path,
            "reason": task.reason,
        }
        if result is not None and hasattr(result, "to_dict"):
            metadata["result"] = result.to_dict()
        summary = result.summary if result is not None and hasattr(result, "summary") else task.reason
        return self.append(
            AuditRecord(
                actor="codex_investigation",
                trigger="investigation",
                action="codex_investigation",
                approval_status="allowed" if status == "completed" else "not_started",
                execution_status=status,
                summary=summary,
                error=error,
                metadata=metadata,
            )
        )

    def records(self, *, limit: int | None = None) -> tuple[AuditRecord, ...]:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than zero")
        with self._lock:
            values = tuple(self._records)
        return values if limit is None else values[-limit:]

    def _load(self) -> None:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines() if self.path else []
            self._records = [AuditRecord.from_dict(json.loads(line)) for line in lines if line.strip()]
        except (OSError, json.JSONDecodeError, AuditLogError) as exc:
            raise AuditLogError(f"unable to read audit log: {self.path}") from exc
