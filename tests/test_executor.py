import pytest

from agent.approval import ApprovalStatus
from agent.decision import DecisionImportance, StructuredDecision
from agent.executor import ActionExecutor, ExecutionStatus


def decision(action: str, *, requires_approval: bool = False) -> StructuredDecision:
    return StructuredDecision(
        importance=DecisionImportance.HIGH,
        summary="test decision",
        next_action=action,
        requires_approval=requires_approval,
    )


def test_registered_read_only_handler_executes_with_a_copy_of_context() -> None:
    received: list[dict[str, object]] = []

    def handler(context: dict[str, object]) -> str:
        received.append(context)
        return "clean"

    executor = ActionExecutor(handlers={"git_status": handler})
    source = {"project_path": "D:/project"}
    result = executor.execute(decision("git_status"), context=source)

    assert result.execution_status is ExecutionStatus.COMPLETED
    assert result.completed is True
    assert result.value == "clean"
    assert received == [source]
    assert received[0] is not source


def test_unregistered_allowlisted_action_is_not_executed() -> None:
    result = ActionExecutor().execute(decision("git_diff"))

    assert result.execution_status is ExecutionStatus.NOT_REGISTERED
    assert result.completed is False
    assert result.error == "action has no registered handler"


@pytest.mark.parametrize(
    "action",
    [
        "delete_file",
        "commit",
        "push",
        "install_package",
        "send_message",
        "kill_process",
        "modify_system",
    ],
)
def test_side_effecting_action_is_blocked_before_handler_invocation(action: str) -> None:
    calls: list[str] = []
    executor = ActionExecutor(handlers={action: lambda _: calls.append("called")})

    result = executor.execute(decision(action))

    assert result.execution_status is ExecutionStatus.BLOCKED
    assert result.approval.status is ApprovalStatus.REQUIRES_APPROVAL
    assert calls == []


def test_handler_failure_is_returned_without_crashing_runtime() -> None:
    def handler(_: dict[str, object]) -> None:
        raise RuntimeError("read failed")

    result = ActionExecutor(handlers={"read_file": handler}).execute(decision("read_file"))

    assert result.execution_status is ExecutionStatus.FAILED
    assert result.completed is False
    assert result.error == "RuntimeError: read failed"
