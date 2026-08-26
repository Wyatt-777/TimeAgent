import importlib.util
import io
import json
import sqlite3
import sys
from pathlib import Path


HOOK_ENTRY = (
    Path(__file__).parents[1]
    / "integrations"
    / "codex"
    / "personal-observer"
    / "hooks"
    / "hook_entry.py"
)


def _load_hook_entry():
    spec = importlib.util.spec_from_file_location("personal_observer_hook_entry", HOOK_ENTRY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_installed_hook_entry_writes_session_events_without_project_imports(monkeypatch, tmp_path) -> None:
    module = _load_hook_entry()
    monkeypatch.setenv("LOCAL_PC_AGENT_ROOT", str(Path(__file__).parents[1]))
    monkeypatch.setenv("LOCAL_PC_AGENT_DATABASE", str(tmp_path / "agent.db"))

    for payload in (
        {"hook_event_name": "SessionStart", "session_id": "thr_1", "cwd": "D:/project", "source": "startup"},
        {"hook_event_name": "SessionEnd", "session_id": "thr_1", "cwd": "D:/project", "reason": "other"},
    ):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        assert module.main() == 0

    with sqlite3.connect(tmp_path / "agent.db") as connection:
        assert [row[0] for row in connection.execute("SELECT type FROM events ORDER BY timestamp")] == [
            "CODEX_SESSION_STARTED",
            "CODEX_SESSION_FINISHED",
        ]


def test_hook_entry_failure_is_non_blocking(monkeypatch, tmp_path) -> None:
    module = _load_hook_entry()
    monkeypatch.setenv("LOCAL_PC_AGENT_ROOT", str(Path(__file__).parents[1]))
    monkeypatch.setenv("LOCAL_PC_AGENT_DATABASE", str(tmp_path / "agent.db"))
    monkeypatch.setattr(sys, "stdin", io.StringIO("not-json"))

    assert module.main() == 0
    assert not (tmp_path / "agent.db").exists()
