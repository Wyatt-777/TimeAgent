# Observer MCP

Local PC Agent provides a read-only STDIO MCP server for Codex. It exposes:

- `observer_get_status`
- `observer_get_recent_events`
- `observer_get_pending_alerts`
- `observer_get_active_session`
- `observer_get_git_status`

The server requires both the SQLite database and workspace root explicitly. It
does not modify files, run arbitrary commands, commit, push, install packages,
or send external messages.

Example project-scoped Codex configuration:

```toml
[mcp_servers.local_pc_agent_observer]
command = "D:/trackTime/local-pc-agent/.venv/Scripts/python.exe"
args = [
  "-m", "integrations.mcp.observer_mcp",
  "--database", "D:/trackTime/local-pc-agent/data/agent.db",
  "--workspace", "D:/trackTime/local-pc-agent",
]
cwd = "D:/trackTime/local-pc-agent"
startup_timeout_sec = 10
tool_timeout_sec = 60
enabled_tools = [
  "observer_get_status",
  "observer_get_recent_events",
  "observer_get_pending_alerts",
  "observer_get_active_session",
  "observer_get_git_status",
]
default_tools_approval_mode = "writes"
```

After configuring the server, restart the Codex client and inspect the active
MCP servers from its MCP view.
