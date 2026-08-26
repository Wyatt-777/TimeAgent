from config.settings import NotificationSettings, Settings, StorageSettings
from config.settings import CodexInvestigationSettings, CodexSettings, ProactiveAgentSettings
from agent.investigation import InvestigationContextPackage
from agent.investigation_service import InvestigationApproval, InvestigationApprovalMode, InvestigationService
from core.event import Event, EventType, Priority
from core.lifecycle import Runtime
from agent.codex_launcher import CodexLauncher
from sensors.file_monitor import FileMonitor
from watchdog.events import FileModifiedEvent
from workspace.session_reporter import SessionCompletionReport
from workspace.summary import CodingSessionSummary


def test_runtime_routes_alert_events_to_alert_store(tmp_path) -> None:
    runtime = Runtime(
        Settings(storage=StorageSettings(sqlite_path=str(tmp_path / "agent.db"))),
        sensors=(),
    )
    runtime.notification_manager.adapter._backend = lambda _: None

    runtime._handle_alert(
        Event(
            type=EventType.TEST_FAILED_REPEATEDLY,
            source="test_failure_tracker",
            priority=Priority.IMPORTANT,
            data={"project_path": "D:/project", "test_group": "unit", "consecutive_failures": 3},
        )
    )

    pending = runtime.alert_inbox.pending()
    assert len(pending) == 1
    assert pending[0].status.value == "NOTIFIED"
    assert runtime.investigation_coordinator.pending(pending[0].id) is not None
    runtime.shutdown()


def test_runtime_sends_investigation_follow_up_notification(tmp_path) -> None:
    runtime = Runtime(
        Settings(storage=StorageSettings(sqlite_path=str(tmp_path / "agent.db"))),
        sensors=(),
    )
    received = []
    runtime.notification_manager.adapter._backend = received.append
    event = Event(
        id="evt_repeat",
        type=EventType.TEST_FAILED_REPEATEDLY,
        source="test_failure_tracker",
        priority=Priority.IMPORTANT,
        data={"project_path": str(tmp_path), "test_group": "unit", "consecutive_failures": 3},
    )
    runtime._handle_alert(event)
    alert = runtime.alert_inbox.pending()[0]
    pending = runtime.investigation_coordinator.pending(alert.id)
    assert pending is not None

    def runner(command, **kwargs):
        import subprocess

        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"outcome":"root_cause_found","summary":"fixture mismatch","root_cause":"bad fixture"}',
            stderr="",
        )

    runtime.investigation_coordinator.service = InvestigationService(
        launcher=CodexLauncher(runner=runner),
        approval=InvestigationApproval(InvestigationApprovalMode.MANUAL),
    )
    context = InvestigationContextPackage(task=pending.task, trigger_event=pending.trigger_event)
    run = runtime.run_investigation(alert.id, approved=True, context=context)

    assert run.status.value == "completed"
    assert received[-1].title == "Codex investigation result"
    assert "bad fixture" in received[-1].message
    runtime.shutdown()


def test_runtime_does_not_notify_for_1000_file_modifications(tmp_path) -> None:
    runtime = Runtime(
        Settings(storage=StorageSettings(sqlite_path=str(tmp_path / "agent.db"))),
        sensors=(),
    )
    received = []
    runtime.notification_manager.adapter._backend = received.append
    monitor = FileMonitor(event_bus=runtime.event_bus, debounce_seconds=0.05)
    path = str(tmp_path / "main.py")

    for _ in range(1000):
        monitor.handle_event(FileModifiedEvent(path), EventType.FILE_MODIFIED)
    events = monitor.flush_pending(force=True)

    assert len(events) == 1
    assert events[0].data["count"] == 1000
    runtime.dispatcher.dispatch_once(timeout=0)
    assert received == []
    runtime.shutdown()


def test_runtime_reports_and_notifies_when_coding_session_finishes(tmp_path) -> None:
    summary = CodingSessionSummary(
        session_id="session_1",
        agent_name="codex.exe",
        project_path=str(tmp_path),
        duration_seconds=30,
        branch="main",
        files_changed=2,
        additions=10,
        deletions=3,
        test_status="passed",
        tests_passed=12,
    )

    class FakeReporter:
        def report(self, event):
            return SessionCompletionReport(summary)

    runtime = Runtime(
        Settings(storage=StorageSettings(sqlite_path=str(tmp_path / "agent.db"))),
        sensors=(),
        session_completion_reporter=FakeReporter(),
    )
    received = []
    runtime.notification_manager.adapter._backend = received.append
    event = Event(
        type=EventType.CODING_SESSION_FINISHED,
        source="coding_agent_monitor",
        data={
            "session_id": "session_1",
            "agent_name": "codex.exe",
            "pid": 42,
            "started_at": "2026-08-27T10:00:00+00:00",
            "ended_at": "2026-08-27T10:00:30+00:00",
            "project_path": str(tmp_path),
        },
    )

    runtime.event_bus.publish(event)
    result = runtime.dispatcher.dispatch_once(timeout=0)

    assert result is not None
    assert result.action.value == "ANALYZE"
    assert runtime.last_session_report.summary.files_changed == 2
    assert len(received) == 1
    assert received[0].title == "Coding Agent session finished"
    assert "12 passed" in received[0].message
    runtime.shutdown()


def test_runtime_honors_disabled_notification_and_investigation_settings(tmp_path) -> None:
    runtime = Runtime(
        Settings(
            storage=StorageSettings(sqlite_path=str(tmp_path / "agent.db")),
            notifications=NotificationSettings(enabled=False),
            codex=CodexSettings(investigation=CodexInvestigationSettings(enabled=False)),
        ),
        sensors=(),
    )
    received = []
    runtime.notification_manager.adapter._backend = received.append
    runtime._handle_alert(
        Event(
            type=EventType.TEST_FAILED_REPEATEDLY,
            source="test_failure_tracker",
            priority=Priority.IMPORTANT,
            data={"project_path": str(tmp_path), "test_group": "unit", "consecutive_failures": 3},
        )
    )

    alert = runtime.alert_inbox.pending()[0]
    assert received == []
    assert runtime.investigation_coordinator.pending(alert.id) is None
    runtime.shutdown()
