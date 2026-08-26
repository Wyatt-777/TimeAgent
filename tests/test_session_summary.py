from datetime import datetime, timedelta, timezone

from sensors.coding_agent_monitor import CodingAgentSession
from workspace.git import GitDiffFile, GitDiffStat, GitStatus
from workspace.summary import SessionSummaryBuilder
from workspace.tests import TestRunResult, TestRunStatus


def test_summary_combines_session_git_and_test_facts() -> None:
    started = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    session = CodingAgentSession(
        session_id="session_1",
        agent_name="codex.exe",
        pid=12,
        started_at=started,
        ended_at=started + timedelta(seconds=90),
        project_path="D:/project",
    )
    summary = SessionSummaryBuilder().build(
        session,
        git_status=GitStatus(branch="main", unstaged=("main.py",)),
        diff_stat=GitDiffStat((GitDiffFile("main.py", 4, 2),)),
        test_result=TestRunResult(TestRunStatus.FAILED, 1, 2.0, passed=8, failed=1),
    )

    assert summary.duration_seconds == 90
    assert summary.files_changed == 1
    assert summary.additions == 4
    assert summary.deletions == 2
    assert summary.attention == (
        "working tree has uncommitted changes",
        "tests finished with status: failed",
    )
    assert "Tests: failed" in summary.to_text()


def test_summary_allows_partial_read_only_facts() -> None:
    session = CodingAgentSession(
        session_id="session_2",
        agent_name="claude.exe",
        pid=13,
        started_at=datetime.now(timezone.utc),
    )

    summary = SessionSummaryBuilder().build(session)

    assert summary.project_path is None
    assert summary.branch is None
    assert summary.test_status == "not_run"
    assert summary.attention == ()
