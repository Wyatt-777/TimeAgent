"""Runtime composition and graceful sensor/dispatcher lifecycle."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, Sequence

from config.settings import Settings

from .dispatcher import Dispatcher
from .event import Event, EventType, Priority
from .event_bus import EventBus
from .event_store import EventStore
from .rule_engine import RuleEngine
from .session_store import SessionStore


class Sensor(Protocol):
    def start(self) -> None: ...

    def stop(self, timeout: float | None = None) -> None: ...


class Runtime:
    """Compose v0.1 services and manage their startup/shutdown ordering."""

    def __init__(
        self,
        settings: Settings,
        *,
        sensors: Sequence[Sensor] | None = None,
        logger: logging.Logger | None = None,
        session_completion_reporter: object | None = None,
    ) -> None:
        settings.validate()
        from alerts import AlertInbox, AlertService, AlertStore
        from alerts.policy import NotificationPolicy
        from notifications import NotificationManager
        from agent.audit_log import AuditLog
        from agent.codex_launcher import CodexLauncher
        from agent.investigation_coordinator import InvestigationCoordinator
        from agent.investigation_limits import InvocationBudget, InvocationLimiter
        from agent.investigation_service import InvestigationService
        from workspace.session_reporter import SessionCompletionReporter

        self.settings = settings
        self.logger = logger or logging.getLogger("local_pc_agent")
        self.event_bus = EventBus()
        self.event_store = EventStore(settings.storage.sqlite_path)
        self.session_store = SessionStore(settings.storage.sqlite_path)
        self.alert_store = AlertStore(settings.storage.sqlite_path)
        self.alert_service = AlertService(
            self.alert_store,
            policy=NotificationPolicy(
                enabled=settings.notifications.enabled,
                minimum_priority=Priority(settings.notifications.minimum_priority),
                cooldown_seconds=settings.notifications.cooldown_seconds,
                dedup_window_seconds=settings.notifications.dedup_window_seconds,
            ),
        )
        self.alert_inbox = AlertInbox(self.alert_store)
        self.notification_manager = NotificationManager(self.alert_service)
        self.session_completion_reporter = session_completion_reporter or SessionCompletionReporter(
            settings.file_monitor.paths
        )
        self.last_session_report = None
        self.investigation_coordinator = InvestigationCoordinator(
            event_store=self.event_store,
            alert_store=self.alert_store,
            service=InvestigationService(
                launcher=CodexLauncher(
                    timeout_seconds=settings.codex.investigation.timeout_seconds,
                ),
                limiter=InvocationLimiter(
                    InvocationBudget(
                        max_invocations=settings.codex.investigation.max_invocations,
                        window_seconds=settings.codex.investigation.window_seconds,
                    )
                ),
                audit_log=AuditLog(Path(settings.storage.log_path) / "investigations.jsonl"),
            ),
            enabled=settings.codex.enabled and settings.codex.investigation.enabled,
        )
        self.rule_engine = RuleEngine(settings.process_monitor.important_processes)
        self.dispatcher = Dispatcher(
            self.event_bus,
            self.event_store,
            self.rule_engine,
            on_analyze=self._handle_analyze,
            on_alert=self._handle_alert,
        )
        if sensors is None:
            from sensors.coding_agent_monitor import CodingAgentMonitor
            from sensors.file_monitor import FileMonitor
            from sensors.process_monitor import ProcessMonitor
            from sensors.window_monitor import WindowMonitor
            from workspace.resolver import WorkspaceResolver

            sensors = (
                ProcessMonitor(self.event_bus, settings.process_monitor),
                CodingAgentMonitor(
                    self.event_bus,
                    settings.coding_agent_monitor,
                    workspace_resolver=WorkspaceResolver(settings.file_monitor.paths),
                    session_store=self.session_store,
                ),
                FileMonitor(self.event_bus, settings.file_monitor),
                WindowMonitor(self.event_bus, settings.window_monitor),
            )
        self.sensors = tuple(sensors)
        self._started = False
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._started:
                raise RuntimeError("Runtime is already running")
            self.logger.info("Starting Local PC Agent")
            started: list[Sensor] = []
            try:
                self.session_store.close_all_active(ended_at=datetime.now(timezone.utc))
                for sensor in self.sensors:
                    sensor.start()
                    started.append(sensor)
                self.dispatcher.start()
                self.event_bus.publish(Event(type=EventType.AGENT_STARTED, source="lifecycle"))
                self._started = True
            except Exception:
                for sensor in reversed(started):
                    sensor.stop(timeout=2)
                self.dispatcher.stop(timeout=2)
                self.alert_store.close()
                self.event_store.close()
                self.session_store.close()
                raise

    def shutdown(self, timeout: float | None = 5) -> None:
        with self._lock:
            if not self._started:
                self.alert_store.close()
                self.event_store.close()
                self.session_store.close()
                return
            self.logger.info("Stopping Local PC Agent")
            for sensor in reversed(self.sensors):
                sensor.stop(timeout=timeout)
            self.dispatcher.stop(timeout=timeout)
            self._drain_events()
            self.event_bus.publish(Event(type=EventType.AGENT_STOPPED, source="lifecycle"))
            self.dispatcher.dispatch_once(timeout=0)
            self.event_bus.shutdown()
            self.event_store.close()
            self.session_store.close()
            self.alert_store.close()
            self._started = False

    def _handle_alert(self, event: Event) -> None:
        result = self.alert_service.create_from_event(event)
        if result.created and result.alert is not None:
            self.investigation_coordinator.enqueue_alert(result.alert, event)
            delivery = self.notification_manager.deliver(result.alert)
            if not delivery.sent:
                self.logger.warning("Alert %s was not notified: %s", result.alert.id, delivery.reason)

    def _handle_analyze(self, event: Event) -> None:
        if (
            event.type is not EventType.CODING_SESSION_FINISHED
            or not self.settings.proactive_agent.enabled
            or event.type.value not in self.settings.proactive_agent.notify_on
        ):
            return
        try:
            report = self.session_completion_reporter.report(event)  # type: ignore[attr-defined]
        except Exception as exc:
            self.logger.warning("Session summary was not created: %s", exc)
            return
        self.last_session_report = report
        notification = self.notification_manager.deliver_message(
            title="Coding Agent session finished",
            message=report.summary.to_text()[:2_000],
        )
        if not notification.delivered:
            self.logger.warning("Session summary was not notified: %s", notification.error)

    def run_investigation(
        self,
        alert_id: str,
        *,
        approved: bool = False,
        context: object | None = None,
    ) -> object:
        """Run one queued investigation only after an explicit approval flag."""
        from agent.investigation_service import InvestigationRunStatus

        run = self.investigation_coordinator.run_for_alert(
            alert_id,
            approved=approved,
            context=context,  # type: ignore[arg-type]
        )
        if run.status is not InvestigationRunStatus.BLOCKED:
            alert = self.alert_store.get(alert_id)
            if alert is not None:
                delivery = self.notification_manager.deliver_follow_up(
                    alert,
                    title="Codex investigation result",
                    message=_investigation_message(run),
                )
                if not delivery.sent:
                    self.logger.warning(
                        "Investigation result for alert %s was not notified: %s",
                        alert_id,
                        delivery.reason,
                    )
        return run

    def _drain_events(self) -> None:
        while self.event_bus.qsize() > 0:
            if self.dispatcher.dispatch_once(timeout=0) is None:
                break

    @property
    def is_running(self) -> bool:
        return self._started


def configure_logging(settings: Settings) -> None:
    """Configure a console logger using the validated application level."""
    logging.basicConfig(
        level=getattr(logging, settings.agent.log_level),
        format="[%(asctime)s] %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )


def _investigation_message(run: object) -> str:
    """Build a bounded user-facing message from a structured investigation run."""
    result = getattr(run, "result", None)
    if result is not None:
        summary = str(result.summary).strip()
        root_cause = getattr(result, "root_cause", None)
        if isinstance(root_cause, str) and root_cause.strip():
            return f"{summary} Possible root cause: {root_cause.strip()}"[:500]
        return summary[:500]
    error = getattr(run, "error", None)
    status = getattr(getattr(run, "status", None), "value", "unknown")
    if isinstance(error, str) and error.strip():
        return f"Investigation {status}: {error.strip()}"[:500]
    return f"Investigation finished with status: {status}."
