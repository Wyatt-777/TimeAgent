"""Provider-neutral interface for the optional v0.2 LLM layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol, runtime_checkable


class ProviderError(RuntimeError):
    """Base error for provider failures."""


class ProviderTimeout(ProviderError):
    """Raised when a provider exceeds its configured timeout."""


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """Provider-neutral request envelope."""

    prompt: str
    system_prompt: str = ""
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Provider-neutral response envelope."""

    text: str
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal contract implemented by real and mock LLM providers."""

    def complete(self, request: LLMRequest, *, timeout_seconds: float = 30.0) -> LLMResponse:
        """Return a response or raise a ProviderError."""
        ...


class MockProvider:
    """Deterministic provider for unit and integration tests."""

    def __init__(
        self,
        responses: Iterable[LLMResponse | str] = (),
        *,
        default_response: LLMResponse | str = "{}",
    ) -> None:
        self._responses = list(responses)
        self.default_response = _response(default_response)
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest, *, timeout_seconds: float = 30.0) -> LLMResponse:
        if not isinstance(request, LLMRequest):
            raise TypeError("MockProvider accepts LLMRequest instances only")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self.requests.append(request)
        if self._responses:
            return _response(self._responses.pop(0))
        return self.default_response


def _response(value: LLMResponse | str) -> LLMResponse:
    if isinstance(value, LLMResponse):
        return value
    if isinstance(value, str):
        return LLMResponse(text=value, model="mock")
    raise TypeError("Mock responses must be strings or LLMResponse instances")
