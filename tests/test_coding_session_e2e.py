from datetime import datetime, timedelta, timezone

import psutil

from config.settings import CodingAgentMonitorSettings
from core.event import EventType
from core.failure_tracker import TestFailureTracker
from core.rule_engine import RuleAction, RuleEngine
from sensors.coding_agent_monitor import CodingAgentMonitor, CodingAgentSession
from workspace.git import GitDiffFile, GitDiffStat, GitStatus
from workspace.resolver import WorkspaceResolver
from workspace.summary import SessionSummaryBuilder
from workspace.tests import TestRunResult, TestRunStatus


class FakeProcess:
    def __init__(self, info, cwd):
        self.info = info
        self._cwd = cwd

    def cwd(self):
        return self._cwd


def test_coding_session_to_summary_and_repeated_failure_alert(monkeypatch, tmp_path) -> None:
    project = tmp_path / "project"
    process = FakeProcess(
        {"pid": 42, "name": "codex.exe", "create_time": 1.0},
        str(project / "src"),
    )
    snapshots = [[], [process], []]
    monkeypatch.setattr(
        "sensors.coding_agent_monitor.psutil.process_iter",
        lambda _attrs: snapshots.pop(0),
    )
    monitor = CodingAgentMonitor(
        settings=CodingAgentMonitorSettings(process_names=("codex.exe",)),
        workspace_resolver=WorkspaceResolver([project]),
    )

    assert monitor.scan_once() == []
    started = monitor.scan_once()[0]
    finished = monitor.scan_once()[0]
    assert started.type is EventType.CODING_SESSION_STARTED
    assert finished.type is EventType.CODING_SESSION_FINISHED
    assert started.data["project_path"] == str(project.resolve())
    assert finished.data["session_id"] == started.data["session_id"]

    start = datetime.fromisoformat(started.data["started_at"])
    end = datetime.fromisoformat(finished.data["ended_at"])
    session = CodingAgentSession(
        session_id=started.data["session_id"],
        agent_name=started.data["agent_name"],
        pid=started.data["pid"],
        started_at=start,
        ended_at=end,
        project_path=started.data["project_path"],
    )
    summary = SessionSummaryBuilder().build(
        session,
        git_status=GitStatus(branch="main", unstaged=("src/main.py",)),
        diff_stat=GitDiffStat((GitDiffFile("src/main.py", 5, 2),)),
        test_result=TestRunResult(TestRunStatus.FAILED, 1, 1.5, failed=1),
    )
    assert summary.files_changed == 1
    assert "tests finished with status: failed" in summary.attention

    tracker = TestFailureTracker()
    now = datetime.now(timezone.utc)
    tracker.record(summary_test := TestRunResult(TestRunStatus.FAILED, 1, 1.0, failed=1), project_path=summary.project_path, timestamp=now)
    tracker.record(summary_test, project_path=summary.project_path, timestamp=now + timedelta(minutes=1))
    alerts = tracker.record(summary_test, project_path=summary.project_path, timestamp=now + timedelta(minutes=2))

    repeated = next(event for event in alerts if event.type is EventType.TEST_FAILED_REPEATEDLY)
    assert RuleEngine().classify(repeated) is RuleAction.ALERT
