"""Connect repeated-failure alerts to manually approved investigations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from alerts.model import Alert, AlertStatus
from alerts.store import AlertStore
from core.event import Event, EventType
from core.event_store import EventStore

from .context_builder import ContextBuilder
from .investigation import InvestigationContextPackage, InvestigationTask
from .investigation_service import InvestigationRun, InvestigationService


@dataclass(frozen=True, slots=True)
class PendingInvestigation:
    alert_id: str
    task: InvestigationTask
    trigger_event: Event


class InvestigationCoordinator:
    """Create pending tasks from alerts and run them only after explicit approval."""

    def __init__(
        self,
        *,
        event_store: EventStore,
        alert_store: AlertStore,
        service: InvestigationService,
        context_builder: ContextBuilder | None = None,
        enabled: bool = True,
    ) -> None:
        self.event_store = event_store
        self.alert_store = alert_store
        self.service = service
        self.context_builder = context_builder or ContextBuilder(event_store)
        self.enabled = enabled
        self._pending: dict[str, PendingInvestigation] = {}

    def enqueue_alert(self, alert: Alert, event: Event) -> InvestigationTask | None:
        if not isinstance(alert, Alert) or not isinstance(event, Event):
            raise TypeError("alert and event are required")
        if not self.enabled:
            return None
        if event.type is not EventType.TEST_FAILED_REPEATEDLY:
            return None
        project_path = event.data.get("project_path")
        if not isinstance(project_path, str) or not project_path.strip():
            return None
        existing = self._pending.get(alert.id)
        if existing is not None:
            return existing.task
        task = InvestigationTask(
            trigger_event_id=event.id,
            project_path=project_path,
            reason=alert.summary,
            test_group=str(event.data.get("test_group") or "default"),
        )
        self._pending[alert.id] = PendingInvestigation(alert.id, task, event)
        self.alert_store.update_metadata(
            alert.id,
            {"investigation_task_id": task.task_id, "investigation_status": task.status.value},
        )
        return task

    def pending(self, alert_id: str) -> PendingInvestigation | None:
        return self._pending.get(alert_id)

    def run_for_alert(
        self,
        alert_id: str,
        *,
        approved: bool = False,
        context: InvestigationContextPackage | None = None,
    ) -> InvestigationRun:
        pending = self._pending.get(alert_id)
        if pending is None:
            raise KeyError(f"No pending investigation for alert: {alert_id}")
        if approved:
            self.service.approval.approve(pending.task.task_id)
            self.alert_store.update_status(alert_id, AlertStatus.INVESTIGATING)
        if context is None:
            base = self.context_builder.build(pending.trigger_event)
            context = InvestigationContextPackage(
                task=pending.task,
                trigger_event=pending.trigger_event,
                recent_events=base.recent_events,
                project_state=base.project_state,
                git_status=base.git_status,
                test_result=base.agent_config,
            )
        run = self.service.run(pending.task, context)
        self.alert_store.update_metadata(
            alert_id,
            {
                "investigation_status": run.status.value,
                "investigation_result": run.result.to_dict() if run.result is not None else None,
                "investigation_error": run.error,
            },
        )
        return run
