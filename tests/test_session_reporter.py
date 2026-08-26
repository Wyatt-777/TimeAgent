from datetime import datetime, timedelta, timezone

from core.event import Event, EventType
from workspace.git import GitDiffFile, GitDiffStat, GitStatus
from workspace.session_reporter import SessionCompletionReporter
from workspace.tests import TestRunResult, TestRunStatus


def finished_event(project_path: str) -> Event:
    started = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
    ended = started + timedelta(minutes=18, seconds=23)
    return Event(
        id="evt_session_finished",
        type=EventType.CODING_SESSION_FINISHED,
        source="coding_agent_monitor",
        data={
            "session_id": "session_1",
            "agent_name": "codex.exe",
            "pid": 42,
            "started_at": started.isoformat(),
            "ended_at": ended.isoformat(),
            "project_path": project_path,
        },
    )


def test_reporter_combines_read_only_git_and_test_facts(monkeypatch, tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    class FakeGitInspector:
        def __init__(self, workspace, **kwargs):
            self.workspace = workspace

        def status(self):
            return GitStatus(branch="main", unstaged=("src/main.py",))

        def diff_stat(self):
            return GitDiffStat((GitDiffFile("src/main.py", 12, 4),))

    class FakeTestRunner:
        def __init__(self, workspace, **kwargs):
            self.workspace = workspace

        def run(self):
            return TestRunResult(TestRunStatus.PASSED, 0, 2.5, passed=34)

    monkeypatch.setattr("workspace.session_reporter.GitInspector", FakeGitInspector)
    monkeypatch.setattr("workspace.session_reporter.TestRunner", FakeTestRunner)

    report = SessionCompletionReporter([project]).report(finished_event(str(project)))

    assert report.errors == ()
    assert report.summary.session_id == "session_1"
    assert report.summary.duration_seconds == 1103
    assert report.summary.files_changed == 1
    assert report.summary.additions == 12
    assert report.summary.deletions == 4
    assert report.summary.test_status == "passed"
    assert report.summary.tests_passed == 34
    assert "Coding Agent Session Finished" in report.summary.to_text()


def test_reporter_returns_partial_summary_when_project_is_unresolved(tmp_path) -> None:
    report = SessionCompletionReporter([tmp_path / "allowed"]).report(
        finished_event(str(tmp_path / "outside"))
    )

    assert report.summary.project_path == str((tmp_path / "outside").resolve())
    assert report.summary.test_status == "not_run"
    assert report.errors == ("project path is unresolved or outside configured workspaces",)
