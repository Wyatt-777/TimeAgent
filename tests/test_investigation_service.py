import subprocess
from datetime import datetime, timezone

import pytest

from agent.audit_log import AuditLog
from agent.codex_launcher import CodexLauncher
from agent.investigation import InvestigationContextPackage, InvestigationTask
from agent.investigation_limits import InvestigationLimitExceeded, InvocationBudget, InvocationLimiter
from agent.investigation_result import InvestigationOutcome, InvestigationParseError, parse_investigation_result
from agent.investigation_service import (
    InvestigationApproval,
    InvestigationApprovalMode,
    InvestigationRunStatus,
    InvestigationService,
)
from core.event import Event, EventType


def _task_context(tmp_path):
    event = Event(id="evt_repeat", type=EventType.TEST_FAILED_REPEATEDLY, source="test_failure_tracker")
    task = InvestigationTask(
        trigger_event_id=event.id,
        project_path=str(tmp_path),
        reason="repeated pytest failure",
    )
    return task, InvestigationContextPackage(task=task, trigger_event=event)


def test_parser_accepts_jsonl_final_result() -> None:
    response = '{"type":"started"}\n{"outcome":"root_cause_found","summary":"bad fixture","root_cause":"fixture mismatch","evidence":["pytest output"],"recommended_actions":["fix fixture"],"confidence":0.9}'

    result = parse_investigation_result(response)

    assert result.outcome is InvestigationOutcome.ROOT_CAUSE_FOUND
    assert result.root_cause == "fixture mismatch"
    assert result.confidence == 0.9


def test_parser_rejects_unstructured_response() -> None:
    with pytest.raises(InvestigationParseError):
        parse_investigation_result("The tests look suspicious.")


def test_invocation_limiter_enforces_bounded_budget() -> None:
    limiter = InvocationLimiter(InvocationBudget(max_invocations=1, window_seconds=60))
    now = datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc)

    limiter.acquire(now=now)
    assert limiter.remaining(now=now) == 0
    with pytest.raises(InvestigationLimitExceeded):
        limiter.acquire(now=now)


def test_manual_approval_blocks_without_launching(tmp_path) -> None:
    task, context = _task_context(tmp_path)
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    service = InvestigationService(
        launcher=CodexLauncher(runner=runner),
        approval=InvestigationApproval(InvestigationApprovalMode.MANUAL),
    )

    run = service.run(task, context)

    assert run.status is InvestigationRunStatus.BLOCKED
    assert calls == []


def test_repeated_failure_investigation_e2e_is_read_only_and_audited(tmp_path) -> None:
    task, context = _task_context(tmp_path)
    approval = InvestigationApproval(InvestigationApprovalMode.MANUAL)
    approval.approve(task.task_id)
    audit = AuditLog()

    def runner(command, **kwargs):
        assert "--sandbox" in command and command[command.index("--sandbox") + 1] == "read-only"
        assert "--ask-for-approval" in command and command[command.index("--ask-for-approval") + 1] == "never"
        assert "--ephemeral" in command
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"outcome":"root_cause_found","summary":"Repeated failure is caused by a fixture mismatch.","root_cause":"fixture mismatch","evidence":["pytest failure output"],"recommended_actions":["update fixture"],"confidence":0.8}',
            stderr="",
        )

    service = InvestigationService(
        launcher=CodexLauncher(runner=runner),
        approval=approval,
        audit_log=audit,
    )
    run = service.run(task, context)

    assert run.status is InvestigationRunStatus.COMPLETED
    assert run.task.status.value == "completed"
    assert run.result is not None
    assert run.result.outcome is InvestigationOutcome.ROOT_CAUSE_FOUND
    assert audit.records()[0].actor == "codex_investigation"
    assert audit.records()[0].metadata["task_id"] == task.task_id
    assert "raw" not in audit.records()[0].metadata


def test_missing_codex_is_converted_to_audited_failure(tmp_path) -> None:
    task, context = _task_context(tmp_path)
    approval = InvestigationApproval(InvestigationApprovalMode.MANUAL)
    approval.approve(task.task_id)
    audit = AuditLog()

    run = InvestigationService(
        launcher=CodexLauncher(codex_command=str(tmp_path / "missing-codex")),
        approval=approval,
        audit_log=audit,
    ).run(task, context)

    assert run.status is InvestigationRunStatus.FAILED
    assert run.launch is not None
    assert run.launch.status.value == "error"
    assert audit.records()[0].execution_status == "failed"


def test_unexpected_launcher_error_is_converted_to_audited_failure(tmp_path) -> None:
    task, context = _task_context(tmp_path)
    approval = InvestigationApproval(InvestigationApprovalMode.MANUAL)
    approval.approve(task.task_id)
    audit = AuditLog()

    class BrokenLauncher:
        def launch(self, _task, _context):
            raise RuntimeError("MCP startup failed")

    run = InvestigationService(
        launcher=BrokenLauncher(),  # type: ignore[arg-type]
        approval=approval,
        audit_log=audit,
    ).run(task, context)

    assert run.status is InvestigationRunStatus.FAILED
    assert run.launch is None
    assert "MCP startup failed" in (run.error or "")
    assert audit.records()[0].error == run.error


def test_timeout_is_audited_without_raising(tmp_path) -> None:
    task, context = _task_context(tmp_path)
    approval = InvestigationApproval(InvestigationApprovalMode.MANUAL)
    approval.approve(task.task_id)
    audit = AuditLog()

    def runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="partial")

    run = InvestigationService(
        launcher=CodexLauncher(runner=runner, timeout_seconds=1),
        approval=approval,
        audit_log=audit,
    ).run(task, context)

    assert run.status is InvestigationRunStatus.TIMED_OUT
    assert audit.records()[0].execution_status == "timed_out"


def test_invalid_json_and_nonzero_exit_are_safe_failures(tmp_path) -> None:
    for returncode, stdout, stderr in ((0, "not json", ""), (2, "", "mcp startup failed")):
        task, context = _task_context(tmp_path)
        approval = InvestigationApproval(InvestigationApprovalMode.MANUAL)
        approval.approve(task.task_id)

        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)

        run = InvestigationService(
            launcher=CodexLauncher(runner=runner),
            approval=approval,
        ).run(task, context)

        assert run.status is InvestigationRunStatus.FAILED
        assert run.task.status.value == "failed"


def test_invocation_limit_blocks_second_launch_and_preserves_service(tmp_path) -> None:
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"outcome":"inconclusive","summary":"not enough evidence"}',
            stderr="",
        )

    service = InvestigationService(
        launcher=CodexLauncher(runner=runner),
        approval=InvestigationApproval(InvestigationApprovalMode.MANUAL),
        limiter=InvocationLimiter(InvocationBudget(max_invocations=1, window_seconds=60)),
    )
    first_task, first_context = _task_context(tmp_path)
    second_task, second_context = _task_context(tmp_path)
    service.approval.approve(first_task.task_id)
    service.approval.approve(second_task.task_id)

    first = service.run(first_task, first_context)
    second = service.run(second_task, second_context)

    assert first.status is InvestigationRunStatus.COMPLETED
    assert second.status is InvestigationRunStatus.LIMITED
    assert len(calls) == 1
