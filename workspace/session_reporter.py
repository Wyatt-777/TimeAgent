"""Build bounded, read-only reports for completed Coding Agent sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from core.event import Event, EventType
from sensors.coding_agent_monitor import CodingAgentSession

from .git import GitDiffStat, GitInspector, GitStatus
from .resolver import WorkspaceResolver
from .summary import CodingSessionSummary, SessionSummaryBuilder
from .tests import TestRunResult, TestRunner


@dataclass(frozen=True, slots=True)
class SessionCompletionReport:
    summary: CodingSessionSummary
    errors: tuple[str, ...] = ()


class SessionCompletionReporter:
    """Collect safe workspace facts after a session-finished event."""

    def __init__(
        self,
        workspace_roots: Iterable[str | Path],
        *,
        git_timeout_seconds: float = 10.0,
        test_timeout_seconds: float = 300.0,
    ) -> None:
        self.resolver = WorkspaceResolver(workspace_roots)
        self.git_timeout_seconds = git_timeout_seconds
        self.test_timeout_seconds = test_timeout_seconds
        self.summary_builder = SessionSummaryBuilder()

    def report(self, event: Event) -> SessionCompletionReport:
        if not isinstance(event, Event):
            raise TypeError("event must be an Event")
        if event.type is not EventType.CODING_SESSION_FINISHED:
            raise ValueError("event must be CODING_SESSION_FINISHED")

        session = _session_from_event(event)
        git_status: GitStatus | None = None
        diff_stat: GitDiffStat | None = None
        test_result: TestRunResult | None = None
        errors: list[str] = []
        match = self.resolver.resolve(session.project_path)
        if match is None:
            errors.append("project path is unresolved or outside configured workspaces")
        else:
            inspector = GitInspector(match.workspace, timeout_seconds=self.git_timeout_seconds)
            try:
                git_status = inspector.status()
            except Exception as exc:
                errors.append(f"git status unavailable: {exc}")
            try:
                diff_stat = inspector.diff_stat()
            except Exception as exc:
                errors.append(f"git diff unavailable: {exc}")
            try:
                test_result = TestRunner(
                    match.workspace,
                    timeout_seconds=self.test_timeout_seconds,
                ).run()
            except Exception as exc:
                errors.append(f"tests unavailable: {exc}")

        summary = self.summary_builder.build(
            session,
            git_status=git_status,
            diff_stat=diff_stat,
            test_result=test_result,
        )
        return SessionCompletionReport(summary=summary, errors=tuple(errors))


def _session_from_event(event: Event) -> CodingAgentSession:
    data = event.data
    try:
        started_at = datetime.fromisoformat(str(data["started_at"]))
        ended_at = datetime.fromisoformat(str(data.get("ended_at") or event.timestamp.isoformat()))
        return CodingAgentSession(
            session_id=str(data["session_id"]),
            agent_name=str(data["agent_name"]),
            pid=int(data["pid"]),
            started_at=started_at,
            ended_at=ended_at,
            project_path=str(data["project_path"]) if data.get("project_path") else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid coding session finished event") from exc
