"""STDIO bootstrap for ``python -m integrations.mcp.observer_mcp``."""

from __future__ import annotations

import argparse
from pathlib import Path

from alerts import AlertInbox, AlertStore
from core.event_store import EventStore
from core.session_store import SessionStore
from integrations.codex.session_merge import SessionMerger
from integrations.mcp.observer_mcp.server import ObserverMcpServer
from workspace.git import GitInspector
from workspace.resolver import WorkspaceResolver


def main() -> int:
    parser = argparse.ArgumentParser(description="Local PC Agent Observer MCP server")
    parser.add_argument("--database", required=True, help="Path to the Local PC Agent SQLite database")
    parser.add_argument("--workspace", required=True, help="Explicitly configured workspace root")
    args = parser.parse_args()

    event_store = EventStore(args.database)
    session_store = SessionStore(args.database)
    alert_store = AlertStore(args.database)
    resolver = WorkspaceResolver([Path(args.workspace)])
    match = resolver.resolve(args.workspace)
    if match is None:
        raise SystemExit("workspace could not be resolved")
    try:
        server = ObserverMcpServer(
            event_store=event_store,
            alert_inbox=AlertInbox(alert_store),
            active_sessions=session_store.list_active,
            git_inspector=GitInspector(match.workspace),
            session_merger=SessionMerger(),
        )
        server.serve_stdio()
    finally:
        alert_store.close()
        session_store.close()
        event_store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
