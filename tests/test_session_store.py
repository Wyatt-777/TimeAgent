from datetime import datetime, timezone

from core.session_store import SessionStore
from sensors.coding_agent_monitor import CodingAgentSession


def test_session_store_persists_active_sessions_for_another_process(tmp_path) -> None:
    database = tmp_path / "agent.db"
    started_at = datetime(2026, 8, 27, 1, 2, tzinfo=timezone.utc)
    session = CodingAgentSession(
        session_id="session_1",
        agent_name="codex.exe",
        pid=123,
        started_at=started_at,
        project_path="D:/trackTime/local-pc-agent",
    )

    with SessionStore(database) as writer:
        writer.upsert_active(session)

    with SessionStore(database) as reader:
        assert reader.schema_version == 3
        assert reader.list_active() == [session]

        ended_at = datetime(2026, 8, 27, 1, 3, tzinfo=timezone.utc)
        reader.mark_finished(session, ended_at=ended_at)
        assert reader.list_active() == []


def test_session_store_closes_stale_active_rows(tmp_path) -> None:
    database = tmp_path / "agent.db"
    session = CodingAgentSession(
        session_id="session_stale",
        agent_name="claude.exe",
        pid=456,
        started_at=datetime.now(timezone.utc),
    )
    with SessionStore(database) as store:
        store.upsert_active(session)
        closed = store.close_all_active(ended_at=datetime.now(timezone.utc))

        assert closed == 1
        assert store.list_active() == []
