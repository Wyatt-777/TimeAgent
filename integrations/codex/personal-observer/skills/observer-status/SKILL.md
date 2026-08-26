---
name: observer-status
description: Use when the user asks for the current Local PC Agent status, recent local events, pending alerts, active Coding Agent sessions, or read-only Git state.
---

# Observer Status

Use the `local_pc_agent_observer` MCP tools to report the current local
observer state. This workflow is strictly read-only.

## Workflow

1. Call `observer_get_status` first.
2. If the user asks about activity, call `observer_get_recent_events` with a
   bounded `limit` no greater than 20.
3. If the user asks about alerts, call `observer_get_pending_alerts` with a
   bounded `limit` no greater than 20.
4. If the user asks about Coding Agent work, call
   `observer_get_active_session`.
5. If the user asks about repository changes, call
   `observer_get_git_status`.

Report the returned facts briefly, including when there are no active sessions
or pending alerts. Do not infer that an empty result means the observer is
broken. Never modify files, run arbitrary commands, commit, push, install
packages, send messages, or enable automatic investigation from this workflow.
