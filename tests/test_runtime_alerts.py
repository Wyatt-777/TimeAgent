from config.settings import Settings, StorageSettings
from agent.investigation import InvestigationContextPackage
from agent.investigation_service import InvestigationApproval, InvestigationApprovalMode, InvestigationService
from core.event import Event, EventType, Priority
from core.lifecycle import Runtime
from agent.codex_launcher import CodexLauncher


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
