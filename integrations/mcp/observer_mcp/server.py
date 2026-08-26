"""Minimal line-oriented MCP server exposing Local PC Agent read-only data."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterable, Mapping
from typing import Any, TextIO

from alerts.inbox import AlertInbox
from core.event import EventType
from core.event_store import EventStore
from sensors.coding_agent_monitor import CodingAgentSession
from workspace.git import GitInspector


class ObserverMcpError(RuntimeError):
    """Raised for invalid Observer MCP requests."""


class ObserverMcpServer:
    """Handle MCP initialize, tool listing, and read-only tool calls."""

    PROTOCOL_VERSION = "2024-11-05"
    INSTRUCTIONS = (
        "This Observer server is strictly read-only. It exposes local event, alert, "
        "Coding Agent session, and Git status context. It never modifies files, runs "
        "commands, commits, pushes, installs packages, or sends external messages."
    )

    def __init__(
        self,
        *,
        event_store: EventStore,
        alert_inbox: AlertInbox,
        active_sessions: Callable[[], Iterable[CodingAgentSession]] | None = None,
        git_inspector: GitInspector | None = None,
    ) -> None:
        self.event_store = event_store
        self.alert_inbox = alert_inbox
        self.active_sessions = active_sessions or (lambda: ())
        self.git_inspector = git_inspector

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        method = request.get("method")
        if not isinstance(method, str):
            return self._error(request_id, -32600, "method is required")
        if method == "notifications/initialized":
            return None
        if method == "initialize":
            return self._result(
                request_id,
                {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "local-pc-agent-observer", "version": "0.1.0"},
                    "instructions": self.INSTRUCTIONS,
                },
            )
        if method == "ping":
            return self._result(request_id, {})
        if method == "tools/list":
            return self._result(request_id, {"tools": self.tool_definitions()})
        if method == "tools/call":
            params = request.get("params")
            if not isinstance(params, Mapping):
                return self._error(request_id, -32602, "params must be an object")
            return self._call_tool(request_id, params)
        return self._error(request_id, -32601, f"method not found: {method}")

    @classmethod
    def tool_definitions(cls) -> list[dict[str, Any]]:
        read_only = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
        return [
            {
                "name": "observer_get_status",
                "description": "Get Observer runtime counts and schema version.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                "annotations": read_only,
            },
            {
                "name": "observer_get_recent_events",
                "description": "Get recent normalized local events.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                    "additionalProperties": False,
                },
                "annotations": read_only,
            },
            {
                "name": "observer_get_pending_alerts",
                "description": "Get unresolved alerts from the local Alert Inbox.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                    "additionalProperties": False,
                },
                "annotations": read_only,
            },
            {
                "name": "observer_get_active_session",
                "description": "Get currently observed Coding Agent sessions.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                "annotations": read_only,
            },
            {
                "name": "observer_get_git_status",
                "description": "Get read-only Git status for the explicitly configured workspace.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                "annotations": read_only,
            },
        ]

    def serve_stdio(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
        """Serve one JSON-RPC message per line; logs never go to stdout."""
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
                response = self.handle(request)
                if response is not None:
                    stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
                    stdout.flush()
            except (json.JSONDecodeError, TypeError) as exc:
                response = self._error(None, -32700, f"invalid JSON-RPC request: {exc}")
                stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
                stdout.flush()

    def _call_tool(self, request_id: Any, params: Mapping[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, Mapping):
            return self._error(request_id, -32602, "tool name and object arguments are required")
        try:
            result = self._tool_result(name, arguments)
        except (KeyError, TypeError, ValueError, ObserverMcpError) as exc:
            return self._result(
                request_id,
                {"content": [{"type": "text", "text": str(exc)}], "isError": True},
            )
        return self._result(
            request_id,
            {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, sort_keys=True)}],
                "structuredContent": result,
                "isError": False,
            },
        )

    def _tool_result(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        limit = _limit(arguments.get("limit", 20))
        if name == "observer_get_status":
            return {
                "status": "ok",
                "schema_version": self.event_store.schema_version,
                "event_count": self.event_store.count(),
                "pending_alert_count": len(self.alert_inbox.pending(limit=limit)),
                "active_session_count": len(tuple(self.active_sessions())),
            }
        if name == "observer_get_recent_events":
            return {"events": [event.to_dict() for event in self.event_store.query(limit=limit)]}
        if name == "observer_get_pending_alerts":
            return {"alerts": [alert.to_dict() for alert in self.alert_inbox.pending(limit=limit)]}
        if name == "observer_get_active_session":
            return {
                "sessions": [
                    {
                        "session_id": session.session_id,
                        "agent_name": session.agent_name,
                        "pid": session.pid,
                        "started_at": session.started_at.isoformat(),
                        "project_path": session.project_path,
                    }
                    for session in self.active_sessions()
                ]
            }
        if name == "observer_get_git_status":
            if self.git_inspector is None:
                return {"available": False, "reason": "no explicitly configured workspace"}
            return {"available": True, **self.git_inspector.status().to_dict()}
        raise ObserverMcpError(f"unknown tool: {name}")

    @staticmethod
    def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _limit(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    return value
