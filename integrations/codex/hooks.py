"""Codex lifecycle capability detection and safe event adaptation."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from core.event import Event, EventType, Priority
from core.event_bus import EventBus
from core.event_store import EventStore


SUPPORTED_HOOK_EVENTS = (
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "UserPromptSubmit",
    "SubagentStop",
    "Stop",
    "SessionStart",
    "SubagentStart",
    "SessionEnd",
)

_EVENT_TYPES = {
    "SessionStart": EventType.CODEX_SESSION_STARTED,
    "SessionEnd": EventType.CODEX_SESSION_FINISHED,
    "UserPromptSubmit": EventType.CODEX_TURN_STARTED,
    "Stop": EventType.CODEX_TURN_FINISHED,
    "PreToolUse": EventType.CODEX_TOOL_ACTIVITY,
    "PermissionRequest": EventType.CODEX_TOOL_ACTIVITY,
    "PostToolUse": EventType.CODEX_TOOL_ACTIVITY,
    "PreCompact": EventType.CODEX_COMPACTION,
    "PostCompact": EventType.CODEX_COMPACTION,
    "SubagentStart": EventType.CODEX_SUBAGENT_ACTIVITY,
    "SubagentStop": EventType.CODEX_SUBAGENT_ACTIVITY,
}

_SAFE_FIELDS = (
    "session_id",
    "cwd",
    "hook_event_name",
    "source",
    "reason",
    "turn_id",
    "tool_name",
    "tool_use_id",
    "agent_id",
    "agent_type",
    "model",
    "permission_mode",
)


@dataclass(frozen=True, slots=True)
class HookCapabilityReport:
    """The locally detected Hook capability, without assuming hook delivery."""

    available: bool
    codex_version: str | None
    supported_events: tuple[str, ...] = SUPPORTED_HOOK_EVENTS
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "codex_version": self.codex_version,
            "supported_events": list(self.supported_events) if self.available else [],
            "reason": self.reason,
        }


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def detect_hook_capabilities(
    codex_command: str = "codex",
    *,
    runner: CommandRunner | None = None,
) -> HookCapabilityReport:
    """Detect whether the installed Codex exposes enabled lifecycle Hooks."""
    run = runner or _run_command
    version = _read_version(run, codex_command)
    try:
        result = run((codex_command, "features", "list"))
    except (OSError, subprocess.SubprocessError) as exc:
        return HookCapabilityReport(
            False,
            version,
            supported_events=(),
            reason=f"unable to inspect Codex features: {exc}",
        )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        return HookCapabilityReport(
            False,
            version,
            supported_events=(),
            reason=f"Codex feature inspection failed: {detail}",
        )
    state = _parse_hooks_feature(result.stdout)
    if state is None:
        return HookCapabilityReport(
            False,
            version,
            supported_events=(),
            reason="Codex feature list did not report hooks",
        )
    if not state:
        return HookCapabilityReport(
            False,
            version,
            supported_events=(),
            reason="Codex hooks feature is disabled",
        )
    return HookCapabilityReport(True, version)


class HookAdapterError(ValueError):
    """Raised when a Hook payload cannot be safely normalized."""


class HookAdapter:
    """Convert Codex Hook stdin payloads into normalized local Events."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        *,
        event_store: EventStore | None = None,
        enabled: bool = True,
    ) -> None:
        self.event_bus = event_bus
        self.event_store = event_store
        self.enabled = enabled

    def adapt(self, payload: Mapping[str, Any]) -> Event | None:
        """Normalize one payload, or return None when Hooks are disabled."""
        if not self.enabled:
            return None
        if not isinstance(payload, Mapping):
            raise HookAdapterError("Hook payload must be an object")
        hook_name = payload.get("hook_event_name")
        if not isinstance(hook_name, str) or hook_name not in _EVENT_TYPES:
            raise HookAdapterError(f"unsupported or missing hook_event_name: {hook_name!r}")
        data = {name: payload[name] for name in _SAFE_FIELDS if name in payload}
        data["hook_event_name"] = hook_name
        priority = (
            Priority.IMPORTANT
            if hook_name in {"SessionStart", "SessionEnd"}
            else Priority.NORMAL
        )
        dedup_key = _dedup_key(payload, hook_name)
        event_kwargs = {"id": _event_id(dedup_key)} if dedup_key is not None else {}
        return Event(
            **event_kwargs,
            type=_EVENT_TYPES[hook_name],
            source="codex_hook_adapter",
            priority=priority,
            data=data,
            metadata={
                "adapter": "codex_hook_adapter",
                **({"dedup_key": dedup_key} if dedup_key is not None else {}),
            },
            timestamp=datetime.now(timezone.utc),
        )

    def handle(self, payload: Mapping[str, Any]) -> Event | None:
        """Adapt and publish one payload; malformed Hooks never affect the Runtime."""
        event = self.adapt(payload)
        if event is not None and self.event_store is not None:
            self.event_store.insert_if_absent(event)
        if event is not None and self.event_bus is not None:
            self.event_bus.publish(event)
        return event


def _run_command(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def _read_version(run: CommandRunner, codex_command: str) -> str | None:
    try:
        result = run((codex_command, "--version"))
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    line = (result.stdout or result.stderr).strip().splitlines()
    return line[0].strip() if line and line[0].strip() else None


def _parse_hooks_feature(output: str) -> bool | None:
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].casefold() == "hooks":
            return parts[-1].casefold() == "true"
    return None


def _dedup_key(payload: Mapping[str, Any], hook_name: str) -> str | None:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return None
    if hook_name in {"SessionStart", "SessionEnd"}:
        return f"codex:{session_id}:{hook_name}"
    field = "tool_use_id" if hook_name in {"PreToolUse", "PermissionRequest", "PostToolUse"} else "turn_id"
    value = payload.get(field)
    if isinstance(value, str) and value.strip():
        return f"codex:{session_id}:{hook_name}:{value}"
    return None


def _event_id(dedup_key: str | None) -> str | None:
    return f"evt_{dedup_key.replace(':', '_')}" if dedup_key is not None else None
