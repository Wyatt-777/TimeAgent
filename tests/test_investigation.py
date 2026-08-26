import subprocess
from datetime import datetime, timezone

import pytest

from agent.codex_launcher import CodexLauncher, LaunchStatus, ReadOnlySandboxPolicy, SandboxPolicyError
from agent.investigation import InvestigationContextPackage, InvestigationStatus, InvestigationTask
from core.event import Event, EventType


def _task_and_context(tmp_path):
    event = Event(id="evt_failure", type=EventType.TEST_FAILED_REPEATEDLY, source="test_failure_tracker")
    task = InvestigationTask(
        trigger_event_id=event.id,
        project_path=str(tmp_path),
        reason="repeated test failure",
        test_group="unit",
    )
    context = InvestigationContextPackage(
        task=task,
        trigger_event=event,
        project_state={"path": str(tmp_path)},
        git_status={"clean": False},
        diff_stat={"files": [{"path": "main.py"}]},
        test_result={"status": "failed", "failed": 3},
    )
    return task, context


def test_investigation_task_has_explicit_state_transitions(tmp_path) -> None:
    task, _ = _task_and_context(tmp_path)
    started_at = datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc)

    running = task.start(at=started_at)
    finished = running.complete(at=started_at)

    assert task.status is InvestigationStatus.PENDING
    assert running.status is InvestigationStatus.RUNNING
    assert finished.status is InvestigationStatus.COMPLETED
    assert finished.to_dict()["trigger_event_id"] == "evt_failure"
    with pytest.raises(ValueError, match="only pending"):
        finished.start()


def test_context_package_is_bounded_and_read_only() -> None:
    task = InvestigationTask(trigger_event_id="evt_1", project_path="D:/project", reason="failure")
    event = Event(id="evt_1", type=EventType.TEST_FAILED, source="test")
    package = InvestigationContextPackage(task=task, trigger_event=event)

    prompt = package.to_prompt()

    assert "read-only" in prompt
    assert "Do not edit files" in prompt
    for forbidden in ("commit", "push", "install packages", "send messages"):
        assert forbidden in prompt
    assert package.to_dict()["task"]["status"] == "pending"


def test_read_only_policy_rejects_dangerous_flags() -> None:
    policy = ReadOnlySandboxPolicy()

    with pytest.raises(SandboxPolicyError, match="bypass"):
        policy.validate(("codex", "exec", "--dangerously-bypass-approvals-and-sandbox"))
    with pytest.raises(SandboxPolicyError, match="read-only"):
        policy.validate(("codex", "exec", "--sandbox"))


def test_codex_launcher_builds_read_only_ephemeral_command(tmp_path) -> None:
    task, context = _task_and_context(tmp_path)
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout='{"type":"completed"}\n', stderr="")

    result = CodexLauncher(runner=runner).launch(task, context)

    assert result.status is LaunchStatus.COMPLETED
    command, kwargs = calls[0]
    assert command[:4] == ("codex", "exec", "--sandbox", "read-only")
    assert "--ask-for-approval" in command
    assert "never" in command
    assert "--ephemeral" in command
    assert kwargs["cwd"] == tmp_path.resolve()
    assert "Do not edit files" in command[-1]


def test_codex_launcher_converts_timeout_to_bounded_result(tmp_path) -> None:
    task, context = _task_and_context(tmp_path)

    def runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="partial")

    result = CodexLauncher(runner=runner, timeout_seconds=1).launch(task, context)

    assert result.status is LaunchStatus.TIMED_OUT
    assert result.returncode is None
    assert result.stdout == "partial"
