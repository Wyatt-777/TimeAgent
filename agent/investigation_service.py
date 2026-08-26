"""Manual, read-only investigation orchestration with audit coverage."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .audit_log import AuditLog
from .codex_launcher import CodexLauncher, LaunchResult, LaunchStatus
from .investigation import InvestigationContextPackage, InvestigationStatus, InvestigationTask
from .investigation_limits import InvestigationLimitExceeded, InvocationLimiter
from .investigation_result import InvestigationParseError, InvestigationResult, parse_investigation_result


class InvestigationApprovalMode(str, Enum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"


class InvestigationRunStatus(str, Enum):
    BLOCKED = "blocked"
    LIMITED = "limited"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True)
class InvestigationRun:
    status: InvestigationRunStatus
    task: InvestigationTask
    launch: LaunchResult | None = None
    result: InvestigationResult | None = None
    error: str | None = None


class InvestigationApproval:
    """Default-deny gate for unattended Investigation launches."""

    def __init__(self, mode: InvestigationApprovalMode = InvestigationApprovalMode.MANUAL) -> None:
        self.mode = mode
        self._approved: set[str] = set()

    def approve(self, task_id: str) -> None:
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id must be a non-empty string")
        self._approved.add(task_id)

    def authorize(self, task_id: str) -> bool:
        if self.mode is InvestigationApprovalMode.AUTOMATIC:
            return True
        return task_id in self._approved

    def consume(self, task_id: str) -> None:
        self._approved.discard(task_id)


class InvestigationService:
    """Run one explicitly requested investigation and record its outcome."""

    def __init__(
        self,
        *,
        launcher: CodexLauncher,
        approval: InvestigationApproval | None = None,
        limiter: InvocationLimiter | None = None,
        audit_log: AuditLog | None = None,
    ) -> None:
        self.launcher = launcher
        self.approval = approval or InvestigationApproval()
        self.limiter = limiter or InvocationLimiter()
        self.audit_log = audit_log

    def run(self, task: InvestigationTask, context: InvestigationContextPackage) -> InvestigationRun:
        if not self.approval.authorize(task.task_id):
            run = InvestigationRun(InvestigationRunStatus.BLOCKED, task, error="manual approval is required")
            self._audit(run)
            return run
        self.approval.consume(task.task_id)
        try:
            self.limiter.acquire()
        except InvestigationLimitExceeded as exc:
            run = InvestigationRun(InvestigationRunStatus.LIMITED, task, error=str(exc))
            self._audit(run)
            return run

        running = task.start()
        try:
            launch = self.launcher.launch(running, context)
        except Exception as exc:
            failed = running.fail(f"{type(exc).__name__}: {exc}")
            run = InvestigationRun(InvestigationRunStatus.FAILED, failed, error=failed.error)
            self._audit(run)
            return run
        if launch.status is LaunchStatus.TIMED_OUT:
            run = InvestigationRun(InvestigationRunStatus.TIMED_OUT, running.timeout(), launch=launch)
        elif not launch.successful:
            failed = running.fail(launch.stderr or f"Codex exited with code {launch.returncode}")
            run = InvestigationRun(InvestigationRunStatus.FAILED, failed, launch=launch, error=failed.error)
        else:
            try:
                parsed = parse_investigation_result(launch.stdout)
            except InvestigationParseError as exc:
                failed = running.fail(str(exc))
                run = InvestigationRun(InvestigationRunStatus.FAILED, failed, launch=launch, error=failed.error)
            else:
                run = InvestigationRun(
                    InvestigationRunStatus.COMPLETED,
                    running.complete(),
                    launch=launch,
                    result=parsed,
                )
        self._audit(run)
        return run

    def _audit(self, run: InvestigationRun) -> None:
        if self.audit_log is None:
            return
        self.audit_log.record_investigation(
            task=run.task,
            status=run.status.value,
            result=run.result,
            error=run.error,
        )
