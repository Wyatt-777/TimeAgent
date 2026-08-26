---
name: coding-session-review
description: Use when the user asks for a read-only review of current or recent Coding Agent work, including session state, activity, alerts, and repository changes.
---

# Coding Session Review

Summarize Coding Agent activity using only the Local PC Agent Observer's
read-only context.

## Workflow

1. Call `observer_get_active_session` to identify currently observed sessions.
2. Call `observer_get_recent_events` with a bounded `limit` no greater than 20.
3. Call `observer_get_pending_alerts` with a bounded `limit` no greater than 20.
4. Call `observer_get_git_status` to report staged, unstaged, untracked, or
   conflicted files.
5. Separate observed facts from interpretation, and explicitly report empty
   session or alert results.

The current Observer exposes active sessions, recent events, alerts, and Git
status; do not invent unavailable session summaries or completion details.
Never modify files, run arbitrary commands, run tests, commit, push, install packages,
send messages, or enable automatic investigation.
