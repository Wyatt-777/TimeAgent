"""Detect Coding Agent process sessions without depending on Codex internals."""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import Event as ThreadEvent
from typing import Iterable
from uuid import uuid4

import psutil

from config.settings import CodingAgentMonitorSettings
from core.event import Event, EventType, Priority
from core.event_bus import EventBus
from workspace.resolver import WorkspaceResolver


@dataclass(frozen=True, slots=True)
class CodingAgentProcess:
    pid: int
    name: str
    create_time: float | None
    cwd: str | None = None


@dataclass(frozen=True, slots=True)
class CodingAgentSession:
    session_id: str
    agent_name: str
    pid: int
    started_at: datetime
    project_path: str | None = None
    ended_at: datetime | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()


class CodingAgentMonitor:
    """Poll configured agent processes and publish session lifecycle events."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        settings: CodingAgentMonitorSettings | None = None,
        workspace_resolver: WorkspaceResolver | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.settings = settings or CodingAgentMonitorSettings()
        self.workspace_resolver = workspace_resolver
        self._known: dict[int, CodingAgentProcess] | None = None
        self._active: dict[int, CodingAgentSession] = {}
        self._stop_event = ThreadEvent()
        self._thread: threading.Thread | None = None

    def scan_once(self) -> list[Event]:
        current = self._snapshot()
        if self._known is None:
            self._known = current
            now = datetime.now(timezone.utc)
            self._active = {
                pid: self._new_session(process, started_at=now)
                for pid, process in current.items()
            }
            return []

        events: list[Event] = []
        previous = self._known
        now = datetime.now(timezone.utc)
        for pid in sorted(previous.keys() - current.keys()):
            session = self._active.pop(pid, None)
            if session is not None:
                events.append(self._session_event(EventType.CODING_SESSION_FINISHED, session, now))
        for pid in sorted(current.keys() - previous.keys()):
            session = self._new_session(current[pid], started_at=now)
            self._active[pid] = session
            events.append(self._session_event(EventType.CODING_SESSION_STARTED, session, now))
        for pid in sorted(previous.keys() & current.keys()):
            if _identity_changed(previous[pid], current[pid]):
                old_session = self._active.pop(pid, None)
                if old_session is not None:
                    events.append(self._session_event(EventType.CODING_SESSION_FINISHED, old_session, now))
                new_session = self._new_session(current[pid], started_at=now)
                self._active[pid] = new_session
                events.append(self._session_event(EventType.CODING_SESSION_STARTED, new_session, now))

        self._known = current
        self._publish(events)
        return events

    def active_sessions(self) -> tuple[CodingAgentSession, ...]:
        return tuple(self._active[pid] for pid in sorted(self._active))

    def start(self) -> None:
        if not self.settings.enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("CodingAgentMonitor is already running")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run, name="coding-agent-monitor", daemon=True)
        self._thread.start()

    def run(self) -> None:
        self.scan_once()
        while not self._stop_event.wait(self.settings.interval_seconds):
            self.scan_once()

    def stop(self, timeout: float | None = None) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _snapshot(self) -> dict[int, CodingAgentProcess]:
        names = {name.casefold() for name in self.settings.process_names}
        result: dict[int, CodingAgentProcess] = {}
        try:
            processes: Iterable[psutil.Process] = psutil.process_iter(["pid", "name", "create_time"])
            for process in processes:
                try:
                    info = process.info
                    name = str(info.get("name") or "<unknown>")
                    if name.casefold() not in names:
                        continue
                    pid = int(info["pid"])
                    create_time = info.get("create_time")
                    result[pid] = CodingAgentProcess(
                        pid=pid,
                        name=name,
                        create_time=float(create_time) if create_time is not None else None,
                        cwd=_process_cwd(process, info),
                    )
                except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError, TypeError, ValueError):
                    continue
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
            return result
        return result

    def _new_session(self, process: CodingAgentProcess, *, started_at: datetime) -> CodingAgentSession:
        project_path = None
        if self.workspace_resolver is not None:
            match = self.workspace_resolver.resolve(process.cwd)
            if match is not None:
                project_path = str(match.workspace.path)
        return CodingAgentSession(
            session_id=f"session_{uuid4().hex}",
            agent_name=process.name,
            pid=process.pid,
            started_at=started_at,
            project_path=project_path,
        )

    @staticmethod
    def _session_event(event_type: EventType, session: CodingAgentSession, timestamp: datetime) -> Event:
        ended_at = session.ended_at or timestamp
        data = {
            "session_id": session.session_id,
            "agent_name": session.agent_name,
            "pid": session.pid,
            "started_at": session.started_at.isoformat(),
        }
        if session.project_path is not None:
            data["project_path"] = session.project_path
        if event_type is EventType.CODING_SESSION_FINISHED:
            finished = replace(session, ended_at=ended_at)
            data.update(
                {
                    "ended_at": ended_at.isoformat(),
                    "duration_seconds": finished.duration_seconds,
                }
            )
        return Event(
            type=event_type,
            source="coding_agent_monitor",
            priority=Priority.IMPORTANT,
            data=data,
        )

    def _publish(self, events: Iterable[Event]) -> None:
        if self.event_bus is None:
            return
        for event in events:
            self.event_bus.publish(event)


def _identity_changed(previous: CodingAgentProcess, current: CodingAgentProcess) -> bool:
    if previous.name != current.name:
        return True
    return (
        previous.create_time is not None
        and current.create_time is not None
        and previous.create_time != current.create_time
    )


def _process_cwd(process: psutil.Process, info: dict[str, object]) -> str | None:
    cwd = info.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return cwd
    try:
        value = process.cwd()
    except (AttributeError, psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
        return None
    return value if isinstance(value, str) and value.strip() else None
