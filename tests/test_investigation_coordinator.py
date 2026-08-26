import subprocess

from alerts import AlertInbox, AlertService, AlertStore
from agent.audit_log import AuditLog
from agent.codex_launcher import CodexLauncher
from agent.investigation_coordinator import InvestigationCoordinator
from agent.investigation_service import InvestigationApproval, InvestigationApprovalMode, InvestigationService
from core.event import Event, EventType, Priority
from core.event_store import EventStore


def test_repeated_failure_alert_creates_pending_investigation_without_launch(tmp_path) -> None:
    database = tmp_path / "agent.db"
    event_store = EventStore(database)
    alert_store = AlertStore(database)
    try:
        event = Event(
            id="evt_repeat",
            type=EventType.TEST_FAILED_REPEATEDLY,
            source="test_failure_tracker",
            priority=Priority.IMPORTANT,
            data={"project_path": str(tmp_path), "test_group": "unit", "consecutive_failures": 3},
        )
        alert = AlertService(alert_store).create_from_event(event).alert
        assert alert is not None
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

        coordinator = InvestigationCoordinator(
            event_store=event_store,
            alert_store=alert_store,
            service=InvestigationService(
                launcher=CodexLauncher(runner=runner),
                approval=InvestigationApproval(InvestigationApprovalMode.MANUAL),
                audit_log=AuditLog(),
            ),
        )
        task = coordinator.enqueue_alert(alert, event)

        assert task is not None
        assert coordinator.pending(alert.id) is not None
        assert calls == []
        assert alert_store.get(alert.id).metadata["investigation_status"] == "pending"
    finally:
        alert_store.close()
        event_store.close()


def test_coordinator_runs_only_after_approval_and_writes_result(tmp_path) -> None:
    database = tmp_path / "agent.db"
    event_store = EventStore(database)
    alert_store = AlertStore(database)
    try:
        event = Event(
            id="evt_repeat",
            type=EventType.TEST_FAILED_REPEATEDLY,
            source="test_failure_tracker",
            priority=Priority.IMPORTANT,
            data={"project_path": str(tmp_path), "test_group": "unit", "consecutive_failures": 3},
        )
        alert = AlertService(alert_store).create_from_event(event).alert
        assert alert is not None
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"outcome":"root_cause_found","summary":"fixture mismatch","root_cause":"bad fixture"}',
                stderr="",
            )

        coordinator = InvestigationCoordinator(
            event_store=event_store,
            alert_store=alert_store,
            service=InvestigationService(
                launcher=CodexLauncher(runner=runner),
                approval=InvestigationApproval(InvestigationApprovalMode.MANUAL),
                audit_log=AuditLog(),
            ),
        )
        coordinator.enqueue_alert(alert, event)
        blocked = coordinator.run_for_alert(alert.id)
        completed = coordinator.run_for_alert(alert.id, approved=True)

        assert blocked.status.value == "blocked"
        assert completed.status.value == "completed"
        assert len(calls) == 1
        stored = alert_store.get(alert.id)
        assert stored is not None
        assert stored.metadata["investigation_status"] == "completed"
        assert stored.metadata["investigation_result"]["root_cause"] == "bad fixture"
    finally:
        alert_store.close()
        event_store.close()
