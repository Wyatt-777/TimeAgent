---
name: investigate-event
description: Use when the user asks what a Local PC Agent event or alert means, what caused a recent change, or whether the repository is affected.
---

# Investigate Event

Provide a read-only, evidence-based explanation of a recent Local PC Agent
event or pending alert. This workflow is for investigation and reporting only.

## Workflow

1. Call `observer_get_status` to confirm the Observer database is available.
2. Call `observer_get_recent_events` with a bounded `limit` no greater than 20.
3. Call `observer_get_pending_alerts` when the question involves alerts.
4. Call `observer_get_git_status` when the question involves repository impact.
5. Correlate timestamps, event type, source, priority, alert state, and Git
   state. Clearly label conclusions that are inferences.

Do not claim a root cause without supporting evidence. If the available
read-only context is insufficient, say what evidence is missing. Never modify files,
run arbitrary commands, run tests, commit, push, install packages, send messages,
or enable automatic investigation.
