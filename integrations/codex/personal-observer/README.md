# Personal Observer Codex Plugin

Personal Observer is a local, read-only Codex plugin for the Local PC Agent.
It connects the existing `local_pc_agent_observer` MCP server with focused
workflows for status, event investigation, and Coding Agent session review.

## Included components

- `observer-status`: current counts and health
- `investigate-event`: recent events, alerts, and repository context
- `coding-session-review`: active sessions, activity, alerts, and Git state
- `commands/observer-status.md`: status entry point
- `commands/recent-events.md`: recent event entry point
- `commands/investigate-latest.md`: latest-context investigation entry point

The plugin does not own Runtime state. The MCP server reads the explicitly
configured Local PC Agent SQLite database and workspace. All tools and
workflows are read-only: they do not edit files, run arbitrary commands, run
tests, commit, push, install packages, send messages, or enable automatic
investigation.

The current `.mcp.json` is configured for the local Windows checkout at
`D:/trackTime/local-pc-agent`. A clean-machine packaging and installation test
is intentionally deferred to C308-C309.
