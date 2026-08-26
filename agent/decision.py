"""Validate and safely parse structured decisions from an LLM provider."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .provider import LLMResponse


class DecisionParseError(ValueError):
    """Raised when a provider response is not a valid structured decision."""


class DecisionImportance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class StructuredDecision:
    """The only decision shape accepted by the v0.2 agent layer."""

    importance: DecisionImportance
    summary: str
    next_action: str | None = None
    requires_approval: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.importance, DecisionImportance):
            raise TypeError("importance must be a DecisionImportance")
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise ValueError("summary must be a non-empty string")
        if self.next_action is not None and not isinstance(self.next_action, str):
            raise TypeError("next_action must be a string or null")
        if not isinstance(self.requires_approval, bool):
            raise TypeError("requires_approval must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "importance": self.importance.value,
            "summary": self.summary,
            "next_action": self.next_action,
            "requires_approval": self.requires_approval,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "StructuredDecision":
        if not isinstance(payload, Mapping):
            raise DecisionParseError("decision payload must be a JSON object")
        try:
            importance = DecisionImportance(payload["importance"])
            summary = payload["summary"]
            next_action = payload.get("next_action")
            requires_approval = payload.get("requires_approval", False)
            return cls(
                importance=importance,
                summary=summary,
                next_action=next_action,
                requires_approval=requires_approval,
            )
        except KeyError as exc:
            raise DecisionParseError(f"missing decision field: {exc.args[0]}") from exc
        except (TypeError, ValueError) as exc:
            raise DecisionParseError(str(exc)) from exc


def parse_decision(
    response: LLMResponse | str,
    *,
    fallback: StructuredDecision | None = None,
) -> StructuredDecision:
    """Parse a provider response, optionally returning a safe fallback.

    A fallback is deliberately opt-in so callers cannot silently mistake an
    invalid provider response for a valid decision.
    """

    text = response.text if isinstance(response, LLMResponse) else response
    if not isinstance(text, str):
        error = DecisionParseError("decision response must be text")
        if fallback is not None:
            return fallback
        raise error

    try:
        payload = json.loads(_remove_json_fence(text))
        return StructuredDecision.from_mapping(payload)
    except (json.JSONDecodeError, DecisionParseError) as exc:
        if fallback is not None:
            return fallback
        if isinstance(exc, DecisionParseError):
            raise
        raise DecisionParseError("decision response is not valid JSON") from exc


def _remove_json_fence(text: str) -> str:
    """Accept a single Markdown JSON fence without accepting extra prose."""

    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    lines = cleaned.splitlines()
    if len(lines) < 3 or lines[0].strip() not in {"```", "```json"} or lines[-1].strip() != "```":
        return cleaned
    return "\n".join(lines[1:-1]).strip()
