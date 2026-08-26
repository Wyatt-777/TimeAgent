"""Policy-protected execution of explicitly registered local actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping

from .approval import ApprovalPolicy, ApprovalResult, ApprovalStatus
from .decision import StructuredDecision


ActionHandler = Callable[[Mapping[str, Any]], Any]


class ExecutionStatus(str, Enum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    NOT_REGISTERED = "not_registered"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ActionExecutionResult:
    action: str | None
    execution_status: ExecutionStatus
    approval: ApprovalResult
    value: Any = None
    error: str | None = None

    @property
    def completed(self) -> bool:
        return self.execution_status is ExecutionStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "execution_status": self.execution_status.value,
            "approval": self.approval.to_dict(),
            "value": self.value,
            "error": self.error,
            "completed": self.completed,
        }


class ActionExecutor:
    """Run only handlers explicitly registered by the host application.

    This class intentionally has no shell, subprocess, filesystem mutation or
    network primitive. A future integration must register a narrow handler and
    still pass through ``ApprovalPolicy``.
    """

    def __init__(
        self,
        *,
        policy: ApprovalPolicy | None = None,
        handlers: Mapping[str, ActionHandler] | None = None,
    ) -> None:
        self.policy = policy or ApprovalPolicy()
        self._handlers: dict[str, ActionHandler] = {}
        for action, handler in (handlers or {}).items():
            self.register(action, handler)

    def register(self, action: str, handler: ActionHandler) -> None:
        if not isinstance(action, str) or not action.strip():
            raise ValueError("action must be a non-empty string")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._handlers[action.strip()] = handler

    def execute(
        self,
        decision: StructuredDecision,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> ActionExecutionResult:
        approval = self.policy.evaluate(decision)
        if approval.status is not ApprovalStatus.ALLOWED:
            return ActionExecutionResult(
                action=approval.action,
                execution_status=ExecutionStatus.BLOCKED,
                approval=approval,
            )

        handler = self._handlers.get(approval.action or "")
        if handler is None:
            return ActionExecutionResult(
                action=approval.action,
                execution_status=ExecutionStatus.NOT_REGISTERED,
                approval=approval,
                error="action has no registered handler",
            )

        try:
            value = handler(dict(context or {}))
        except Exception as exc:  # handler failures must not crash the runtime
            return ActionExecutionResult(
                action=approval.action,
                execution_status=ExecutionStatus.FAILED,
                approval=approval,
                error=f"{type(exc).__name__}: {exc}",
            )
        return ActionExecutionResult(
            action=approval.action,
            execution_status=ExecutionStatus.COMPLETED,
            approval=approval,
            value=value,
        )
