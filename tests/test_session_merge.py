from datetime import datetime, timedelta, timezone

from core.event import Event, EventType
from integrations.codex.session_merge import SessionMerger
from sensors.coding_agent_monitor import CodingAgentSession


def _process(started_at, project_path="D:/project"):
    return CodingAgentSession(
        session_id="process_1",
        agent_name="codex.exe",
        pid=7,
        started_at=started_at,
        project_path=project_path,
    )


def _hook(event_type, timestamp, session_id="thread_1", cwd="D:/project"):
    return Event(
        type=event_type,
        source="codex_hook_adapter",
        timestamp=timestamp,
        data={"session_id": session_id, "cwd": cwd, "hook_event_name": "SessionStart"},
    )


def test_merger_keeps_one_logical_session_for_matching_sources() -> None:
    started_at = datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc)

    sessions = SessionMerger().merge(
        (_process(started_at),),
        (_hook(EventType.CODEX_SESSION_STARTED, started_at + timedelta(seconds=2)),),
    )

    assert len(sessions) == 1
    assert sessions[0].session_id == "process_1"
    assert sessions[0].codex_session_id == "thread_1"
    assert sessions[0].sources == ("process_monitor", "codex_hook_adapter")


def test_merger_preserves_unmatched_hook_and_process_sessions() -> None:
    started_at = datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc)

    sessions = SessionMerger(match_window_seconds=10).merge(
        (_process(started_at, project_path="D:/other"),),
        (_hook(EventType.CODEX_SESSION_STARTED, started_at + timedelta(seconds=30), cwd="D:/project"),),
    )

    assert {session.session_id for session in sessions} == {"codex:thread_1", "process_1"}
    assert all(len(session.sources) == 1 for session in sessions)


def test_merger_drops_hook_sessions_that_have_finished() -> None:
    started_at = datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc)

    sessions = SessionMerger().merge(
        (),
        (
            _hook(EventType.CODEX_SESSION_STARTED, started_at),
            _hook(EventType.CODEX_SESSION_FINISHED, started_at + timedelta(seconds=5)),
        ),
    )

    assert sessions == ()
