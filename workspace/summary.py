"""Deterministic, read-only summaries for completed Coding Agent sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .git import GitDiffStat, GitStatus
from .tests import TestRunResult

if TYPE_CHECKING:
    from sensors.coding_agent_monitor import CodingAgentSession


@dataclass(frozen=True, slots=True)
class CodingSessionSummary:
    session_id: str
    agent_name: str
    project_path: str | None
    duration_seconds: float | None
    branch: str | None = None
    working_tree_clean: bool | None = None
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0
    test_status: str = "not_run"
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    test_errors: int = 0
    attention: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "project_path": self.project_path,
            "duration_seconds": self.duration_seconds,
            "branch": self.branch,
            "working_tree_clean": self.working_tree_clean,
            "files_changed": self.files_changed,
            "additions": self.additions,
            "deletions": self.deletions,
            "test_status": self.test_status,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "tests_skipped": self.tests_skipped,
            "test_errors": self.test_errors,
            "attention": list(self.attention),
        }

    def to_text(self) -> str:
        duration = "unknown" if self.duration_seconds is None else f"{self.duration_seconds:.1f}s"
        lines = [
            "Coding Agent Session Finished",
            f"Agent: {self.agent_name}",
            f"Session: {self.session_id}",
            f"Project: {self.project_path or 'unresolved'}",
            f"Duration: {duration}",
            f"Git: {self.branch or 'unknown'} ({self.files_changed} files, +{self.additions}/-{self.deletions})",
            f"Tests: {self.test_status} ({self.tests_passed} passed / {self.tests_failed} failed / {self.tests_skipped} skipped)",
        ]
        if self.attention:
            lines.append("Attention:")
            lines.extend(f"- {item}" for item in self.attention)
        return "\n".join(lines)


class SessionSummaryBuilder:
    """Combine already-collected read-only facts without side effects."""

    def build(
        self,
        session: CodingAgentSession,
        *,
        git_status: GitStatus | None = None,
        diff_stat: GitDiffStat | None = None,
        test_result: TestRunResult | None = None,
    ) -> CodingSessionSummary:
        from sensors.coding_agent_monitor import CodingAgentSession

        if not isinstance(session, CodingAgentSession):
            raise TypeError("session must be a CodingAgentSession")
        attention: list[str] = []
        if git_status is not None and not git_status.clean:
            attention.append("working tree has uncommitted changes")
        if test_result is not None and not test_result.successful:
            attention.append(f"tests finished with status: {test_result.status.value}")
        return CodingSessionSummary(
            session_id=session.session_id,
            agent_name=session.agent_name,
            project_path=session.project_path,
            duration_seconds=session.duration_seconds,
            branch=git_status.branch if git_status is not None else None,
            working_tree_clean=git_status.clean if git_status is not None else None,
            files_changed=len(diff_stat.files) if diff_stat is not None else 0,
            additions=diff_stat.additions if diff_stat is not None else 0,
            deletions=diff_stat.deletions if diff_stat is not None else 0,
            test_status=test_result.status.value if test_result is not None else "not_run",
            tests_passed=test_result.passed if test_result is not None else 0,
            tests_failed=test_result.failed if test_result is not None else 0,
            tests_skipped=test_result.skipped if test_result is not None else 0,
            test_errors=test_result.errors if test_result is not None else 0,
            attention=tuple(attention),
        )
