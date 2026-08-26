"""Strict, bounded parsing for Codex investigation responses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class InvestigationParseError(ValueError):
    """Raised when an investigation response is not in the accepted shape."""


class InvestigationOutcome(str, Enum):
    ROOT_CAUSE_FOUND = "root_cause_found"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class InvestigationResult:
    outcome: InvestigationOutcome
    summary: str
    root_cause: str | None = None
    evidence: tuple[str, ...] = ()
    recommended_actions: tuple[str, ...] = ()
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise ValueError("summary must be a non-empty string")
        for name in ("evidence", "recommended_actions"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or not all(isinstance(item, str) and item.strip() for item in values):
                raise ValueError(f"{name} must contain non-empty strings")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "summary": self.summary,
            "root_cause": self.root_cause,
            "evidence": list(self.evidence),
            "recommended_actions": list(self.recommended_actions),
            "confidence": self.confidence,
        }


def parse_investigation_result(response: str) -> InvestigationResult:
    """Parse one JSON result or the final JSON object from Codex JSONL output."""
    if not isinstance(response, str) or not response.strip():
        raise InvestigationParseError("investigation response must be non-empty text")
    payload = _load_payload(response)
    if isinstance(payload.get("result"), Mapping):
        payload = payload["result"]
    try:
        outcome = InvestigationOutcome(payload["outcome"])
        summary = payload["summary"]
        root_cause = payload.get("root_cause")
        evidence = tuple(payload.get("evidence", ()))
        actions = tuple(payload.get("recommended_actions", ()))
        confidence = payload.get("confidence")
        return InvestigationResult(
            outcome=outcome,
            summary=summary,
            root_cause=root_cause,
            evidence=evidence,
            recommended_actions=actions,
            confidence=confidence,
        )
    except KeyError as exc:
        raise InvestigationParseError(f"missing investigation field: {exc.args[0]}") from exc
    except (TypeError, ValueError) as exc:
        raise InvestigationParseError(str(exc)) from exc


def _load_payload(response: str) -> dict[str, Any]:
    cleaned = response.strip()
    candidates = [cleaned]
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            candidates.append("\n".join(lines[1:-1]).strip())
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            return dict(value)
    for line in reversed(cleaned.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping) and ("outcome" in value or isinstance(value.get("result"), Mapping)):
            return dict(value)
    raise InvestigationParseError("response does not contain a JSON investigation result")
