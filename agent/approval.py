"""Approval policy for actions proposed by the optional agent layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from .decision import StructuredDecision


class ApprovalStatus(str, Enum):
    NO_ACTION = "no_action"
    ALLOWED = "allowed"
    REQUIRES_APPROVAL = "requires_approval"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    """The policy result; only ``ALLOWED`` may proceed to an executor."""

    action: str | None
    status: ApprovalStatus
    reason: str

    @property
    def can_execute(self) -> bool:
        return self.status is ApprovalStatus.ALLOWED

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "status": self.status.value,
            "reason": self.reason,
            "can_execute": self.can_execute,
        }


class ApprovalPolicy:
    """Conservative action gate for unattended operation.

    Actions are symbolic names, never shell commands. Only the explicit
    read-only allowlist can run without a user approval flow.
    """

    DEFAULT_AUTO_ALLOWED = frozenset(
        {
            "read_file",
            "git_status",
            "git_diff",
            "run_tests",
            "summarize",
            "inspect_events",
        }
    )
    DEFAULT_APPROVAL_REQUIRED = frozenset(
        {
            "delete_file",
            "modify_file",
            "commit",
            "push",
            "install_package",
            "send_message",
            "kill_process",
            "modify_system",
        }
    )

    def __init__(
        self,
        *,
        auto_allowed: Iterable[str] | None = None,
        approval_required: Iterable[str] | None = None,
    ) -> None:
        self.auto_allowed = frozenset(auto_allowed or self.DEFAULT_AUTO_ALLOWED)
        self.approval_required = frozenset(
            approval_required or self.DEFAULT_APPROVAL_REQUIRED
        )

    def evaluate(self, decision: StructuredDecision) -> ApprovalResult:
        if not isinstance(decision, StructuredDecision):
            raise TypeError("decision must be a StructuredDecision")

        if decision.next_action is None:
            return ApprovalResult(None, ApprovalStatus.NO_ACTION, "decision has no next action")

        action = decision.next_action.strip()
        if not action:
            return ApprovalResult(action, ApprovalStatus.DENIED, "empty actions are denied")
        if decision.requires_approval:
            return ApprovalResult(action, ApprovalStatus.REQUIRES_APPROVAL, "decision requests approval")
        if action in self.auto_allowed:
            return ApprovalResult(action, ApprovalStatus.ALLOWED, "action is on the read-only allowlist")
        if action in self.approval_required:
            return ApprovalResult(action, ApprovalStatus.REQUIRES_APPROVAL, "action requires explicit user approval")
        return ApprovalResult(action, ApprovalStatus.DENIED, "unknown actions are denied by default")
