import pytest

from agent.provider import LLMProvider, LLMRequest, LLMResponse, MockProvider


def test_mock_provider_implements_provider_contract() -> None:
    provider = MockProvider(default_response='{"importance":"low"}')

    assert isinstance(provider, LLMProvider)


def test_mock_provider_returns_deterministic_responses_and_records_request() -> None:
    provider = MockProvider(responses=["first", LLMResponse(text="second", model="mock-v2")])
    first_request = LLMRequest(prompt="event one", system_prompt="system")
    second_request = LLMRequest(prompt="event two")

    first = provider.complete(first_request)
    second = provider.complete(second_request)

    assert first.text == "first"
    assert first.model == "mock"
    assert second.text == "second"
    assert second.model == "mock-v2"
    assert provider.requests == [first_request, second_request]


def test_mock_provider_uses_default_response_after_scripted_responses() -> None:
    provider = MockProvider(responses=["only once"], default_response="fallback")

    provider.complete(LLMRequest(prompt="one"))
    fallback = provider.complete(LLMRequest(prompt="two"))

    assert fallback.text == "fallback"


def test_mock_provider_validates_request_and_timeout() -> None:
    provider = MockProvider()

    with pytest.raises(TypeError):
        provider.complete("not a request")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timeout_seconds"):
        provider.complete(LLMRequest(prompt="test"), timeout_seconds=0)
