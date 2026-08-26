import pytest

from agent.approval import ApprovalPolicy, ApprovalStatus
from agent.decision import DecisionImportance, StructuredDecision


def decision(action: str | None, *, requires_approval: bool = False) -> StructuredDecision:
    return StructuredDecision(
        importance=DecisionImportance.HIGH,
        summary="test decision",
        next_action=action,
        requires_approval=requires_approval,
    )


def test_read_only_action_is_allowed() -> None:
    result = ApprovalPolicy().evaluate(decision("git_status"))

    assert result.status is ApprovalStatus.ALLOWED
    assert result.can_execute is True


def test_explicit_approval_flag_overrides_allowlist() -> None:
    result = ApprovalPolicy().evaluate(decision("run_tests", requires_approval=True))

    assert result.status is ApprovalStatus.REQUIRES_APPROVAL
    assert result.can_execute is False


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
def test_side_effecting_action_requires_approval(action: str) -> None:
    result = ApprovalPolicy().evaluate(decision(action))

    assert result.status is ApprovalStatus.REQUIRES_APPROVAL
    assert result.can_execute is False


def test_high_risk_action_cannot_be_added_to_auto_allowlist() -> None:
    result = ApprovalPolicy(auto_allowed={"push"}).evaluate(decision("push"))

    assert result.status is ApprovalStatus.REQUIRES_APPROVAL
    assert result.can_execute is False


def test_unknown_action_is_denied_by_default() -> None:
    result = ApprovalPolicy().evaluate(decision("run_arbitrary_command"))

    assert result.status is ApprovalStatus.DENIED
    assert result.can_execute is False


def test_missing_or_empty_action_never_executes() -> None:
    no_action = ApprovalPolicy().evaluate(decision(None))
    empty_action = ApprovalPolicy().evaluate(decision("   "))

    assert no_action.status is ApprovalStatus.NO_ACTION
    assert empty_action.status is ApprovalStatus.DENIED
