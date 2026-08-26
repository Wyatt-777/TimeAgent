"""Best-effort Codex Hook entry point; Hook failures never block Codex."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


EVENT_TYPES = {
    "SessionStart": "CODEX_SESSION_STARTED",
    "SessionEnd": "CODEX_SESSION_FINISHED",
    "UserPromptSubmit": "CODEX_TURN_STARTED",
    "Stop": "CODEX_TURN_FINISHED",
    "PreToolUse": "CODEX_TOOL_ACTIVITY",
    "PermissionRequest": "CODEX_TOOL_ACTIVITY",
    "PostToolUse": "CODEX_TOOL_ACTIVITY",
    "PreCompact": "CODEX_COMPACTION",
    "PostCompact": "CODEX_COMPACTION",
    "SubagentStart": "CODEX_SUBAGENT_ACTIVITY",
    "SubagentStop": "CODEX_SUBAGENT_ACTIVITY",
}
SAFE_FIELDS = (
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


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Hook stdin must contain a JSON object")
        root = _find_project_root()
        if root is None:
            raise FileNotFoundError("Local PC Agent project root was not found")
        database = Path(os.environ.get("LOCAL_PC_AGENT_DATABASE", root / "data" / "agent.db"))
        _write_event(database, payload)
    except Exception as exc:  # pragma: no cover - exercised by Codex process boundary
        print(f"Local PC Agent Hook skipped: {exc}", file=sys.stderr)
    return 0


def _find_project_root() -> Path | None:
    configured = os.environ.get("LOCAL_PC_AGENT_ROOT")
    if configured:
        candidate = Path(configured).expanduser()
        if _looks_like_project(candidate):
            return candidate.resolve()
    for candidate in (Path.cwd(), *Path.cwd().parents):
        if _looks_like_project(candidate):
            return candidate.resolve()
    return None


def _looks_like_project(path: Path) -> bool:
    return (path / "core" / "event.py").is_file() and (path / "integrations" / "codex" / "hooks.py").is_file()


def _write_event(database: Path, payload: dict[str, object]) -> None:
    hook_name = payload.get("hook_event_name")
    if not isinstance(hook_name, str) or hook_name not in EVENT_TYPES:
        raise ValueError(f"unsupported or missing hook_event_name: {hook_name!r}")
    data = {name: payload[name] for name in SAFE_FIELDS if name in payload}
    data["hook_event_name"] = hook_name
    session_id = payload.get("session_id")
    dedup_key = None
    if isinstance(session_id, str) and session_id.strip():
        if hook_name in {"SessionStart", "SessionEnd"}:
            dedup_key = f"codex:{session_id}:{hook_name}"
        else:
            field = "tool_use_id" if hook_name in {"PreToolUse", "PermissionRequest", "PostToolUse"} else "turn_id"
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                dedup_key = f"codex:{session_id}:{hook_name}:{value}"
    event_id = f"evt_{dedup_key.replace(':', '_')}" if dedup_key else f"evt_{uuid4().hex}"
    metadata = {"adapter": "codex_hook_adapter"}
    if dedup_key:
        metadata["dedup_key"] = dedup_key
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                source TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                priority INTEGER NOT NULL,
                data TEXT NOT NULL,
                metadata TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_events_source ON events(source)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_events_priority ON events(priority)")
        connection.execute(
            """
            INSERT OR IGNORE INTO events (id, type, source, timestamp, priority, data, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                EVENT_TYPES[hook_name],
                "codex_hook_adapter",
                datetime.now(timezone.utc).isoformat(),
                30 if hook_name in {"SessionStart", "SessionEnd"} else 20,
                json.dumps(data, ensure_ascii=False, sort_keys=True),
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            ),
        )


if __name__ == "__main__":
    raise SystemExit(main())
