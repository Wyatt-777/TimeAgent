import io
import json
from datetime import datetime, timezone

from alerts import AlertInbox, AlertStore
from core.event import Event, EventType
from core.event_store import EventStore
from core.session_store import SessionStore
from integrations.mcp.observer_mcp.server import ObserverMcpServer
from integrations.codex.session_merge import SessionMerger
from sensors.coding_agent_monitor import CodingAgentSession
from workspace.git import GitStatus
from workspace.resolver import Workspace


class FakeGitInspector:
    def status(self):
        return GitStatus(branch="main")


def make_server(tmp_path):
    database = tmp_path / "agent.db"
    event_store = EventStore(database)
    alert_store = AlertStore(database)
    session = CodingAgentSession(
        session_id="session_1",
        agent_name="codex.exe",
        pid=1,
        started_at=datetime.now(timezone.utc),
        project_path="D:/project",
    )
    server = ObserverMcpServer(
        event_store=event_store,
        alert_inbox=AlertInbox(alert_store),
        active_sessions=lambda: (session,),
        git_inspector=FakeGitInspector(),
    )
    return server, event_store, alert_store


def test_mcp_initialize_and_tool_list_are_read_only(tmp_path) -> None:
    server, event_store, alert_store = make_server(tmp_path)
    try:
        initialized = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

        assert initialized["result"]["capabilities"]["tools"] == {"listChanged": False}
        names = {tool["name"] for tool in listed["result"]["tools"]}
        assert names == {
            "observer_get_status",
            "observer_get_recent_events",
            "observer_get_pending_alerts",
            "observer_get_active_session",
            "observer_get_git_status",
        }
        assert all(tool["annotations"]["readOnlyHint"] for tool in listed["result"]["tools"])
    finally:
        alert_store.close()
        event_store.close()


def test_mcp_tool_calls_return_structured_read_only_data(tmp_path) -> None:
    server, event_store, alert_store = make_server(tmp_path)
    try:
        event_store.insert(Event(type=EventType.FILE_MODIFIED, source="test"))
        response = server.handle({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "observer_get_status", "arguments": {}},
        })
        recent = server.handle({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "observer_get_recent_events", "arguments": {"limit": 1}},
        })

        assert response["result"]["structuredContent"]["event_count"] == 1
        assert response["result"]["structuredContent"]["active_session_count"] == 1
        assert recent["result"]["structuredContent"]["events"][0]["type"] == "FILE_MODIFIED"
    finally:
        alert_store.close()
        event_store.close()


def test_mcp_stdio_round_trip_and_invalid_tool(tmp_path) -> None:
    server, event_store, alert_store = make_server(tmp_path)
    try:
        stdin = io.StringIO(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "bad", "arguments": {}}}) + "\n"
        )
        stdout = io.StringIO()
        server.serve_stdio(stdin, stdout)
        responses = [json.loads(line) for line in stdout.getvalue().splitlines()]

        assert responses[0]["result"] == {}
        assert responses[1]["result"]["isError"] is True
    finally:
        alert_store.close()
        event_store.close()


def test_mcp_reads_persisted_active_sessions(tmp_path) -> None:
    database = tmp_path / "agent.db"
    session = CodingAgentSession(
        session_id="session_persisted",
        agent_name="codex.exe",
        pid=99,
        started_at=datetime.now(timezone.utc),
        project_path="D:/project",
    )
    event_store = EventStore(database)
    alert_store = AlertStore(database)
    session_store = SessionStore(database)
    try:
        session_store.upsert_active(session)
        server = ObserverMcpServer(
            event_store=event_store,
            alert_inbox=AlertInbox(alert_store),
            active_sessions=session_store.list_active,
        )

        response = server.handle({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "observer_get_active_session", "arguments": {}},
        })

        assert response["result"]["structuredContent"]["sessions"] == [{
            "session_id": "session_persisted",
            "agent_name": "codex.exe",
            "pid": 99,
            "started_at": session.started_at.isoformat(),
            "project_path": "D:/project",
        }]
    finally:
        session_store.close()
        alert_store.close()
        event_store.close()


def test_mcp_merges_matching_process_and_hook_sessions(tmp_path) -> None:
    database = tmp_path / "agent.db"
    started_at = datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc)
    process = CodingAgentSession(
        session_id="process_session",
        agent_name="codex.exe",
        pid=99,
        started_at=started_at,
        project_path=str(tmp_path / "project"),
    )
    event_store = EventStore(database)
    alert_store = AlertStore(database)
    event_store.insert(
        Event(
            id="hook_start",
            type=EventType.CODEX_SESSION_STARTED,
            source="codex_hook_adapter",
            timestamp=started_at,
            data={"session_id": "thread_1", "cwd": str(tmp_path / "project"), "hook_event_name": "SessionStart"},
        )
    )
    try:
        server = ObserverMcpServer(
            event_store=event_store,
            alert_inbox=AlertInbox(alert_store),
            active_sessions=lambda: (process,),
            session_merger=SessionMerger(),
        )
        response = server.handle({
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "observer_get_active_session", "arguments": {}},
        })

        sessions = response["result"]["structuredContent"]["sessions"]
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "process_session"
        assert sessions[0]["codex_session_id"] == "thread_1"
        assert sessions[0]["sources"] == ["process_monitor", "codex_hook_adapter"]
    finally:
        alert_store.close()
        event_store.close()
