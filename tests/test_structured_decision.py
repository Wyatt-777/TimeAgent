import pytest

from agent.decision import (
    DecisionImportance,
    DecisionParseError,
    StructuredDecision,
    parse_decision,
)
from agent.provider import LLMResponse


def test_parse_valid_decision_and_round_trip() -> None:
    decision = parse_decision(
        LLMResponse(
            text='{"importance":"high","summary":"Tests are failing","next_action":"inspect_git","requires_approval":false}'
        )
    )

    assert decision == StructuredDecision(
        importance=DecisionImportance.HIGH,
        summary="Tests are failing",
        next_action="inspect_git",
        requires_approval=False,
    )
    assert '"importance": "high"' in decision.to_json()


def test_parse_accepts_json_markdown_fence_and_defaults_optional_fields() -> None:
    decision = parse_decision('```json\n{"importance":"low","summary":"No action needed"}\n```')

    assert decision.importance is DecisionImportance.LOW
    assert decision.next_action is None
    assert decision.requires_approval is False


def test_invalid_response_can_use_safe_fallback() -> None:
    fallback = StructuredDecision(
        importance=DecisionImportance.LOW,
        summary="Provider response was invalid",
    )

    assert parse_decision("not json", fallback=fallback) is fallback


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        '{"importance":"urgent","summary":"unknown importance"}',
        '{"importance":"high","summary":123}',
        '{"importance":"high","summary":"bad approval","requires_approval":"yes"}',
    ],
)
def test_invalid_decision_is_rejected_without_fallback(payload: str) -> None:
    with pytest.raises(DecisionParseError):
        parse_decision(payload)
