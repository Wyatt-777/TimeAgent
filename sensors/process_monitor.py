"""Process start/stop detection using psutil."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from threading import Event as ThreadEvent
from typing import Iterable

import psutil

from config.settings import ProcessMonitorSettings
from core.event import Event, EventType, Priority
from core.event_bus import EventBus


@dataclass(frozen=True, slots=True)
class ProcessInfo:
    pid: int
    name: str
    create_time: float | None


class ProcessMonitor:
    """Poll the process table and publish normalized lifecycle events."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        settings: ProcessMonitorSettings | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.settings = settings or ProcessMonitorSettings()
        self._known: dict[int, ProcessInfo] | None = None
        self._stop_event = ThreadEvent()
        self._thread: threading.Thread | None = None

    def scan_once(self) -> list[Event]:
        """Compare the current process table with the previous snapshot."""
        current = self._snapshot()
        if self._known is None:
            self._known = current
            return []

        events: list[Event] = []
        previous = self._known
        for pid in sorted(previous.keys() - current.keys()):
            events.append(self._event(EventType.PROCESS_STOPPED, previous[pid]))
        for pid in sorted(current.keys() - previous.keys()):
            events.append(self._event(EventType.PROCESS_STARTED, current[pid]))
        for pid in sorted(previous.keys() & current.keys()):
            if _identity_changed(previous[pid], current[pid]):
                events.append(self._event(EventType.PROCESS_STOPPED, previous[pid]))
                events.append(self._event(EventType.PROCESS_STARTED, current[pid]))

        self._known = current
        self._publish(events)
        return events

    def start(self) -> None:
        if not self.settings.enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("ProcessMonitor is already running")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run, name="process-monitor", daemon=True)
        self._thread.start()

    def run(self) -> None:
        self.scan_once()
        while not self._stop_event.wait(self.settings.interval_seconds):
            self.scan_once()

    def stop(self, timeout: float | None = None) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _snapshot(self) -> dict[int, ProcessInfo]:
        result: dict[int, ProcessInfo] = {}
        try:
            processes: Iterable[psutil.Process] = psutil.process_iter(
                ["pid", "name"]
            )
            for process in processes:
                try:
                    info = process.info
                    pid = int(info["pid"])
                    name = str(info.get("name") or "<unknown>")
                    # Keep the general process scan lightweight. PID/name are
                    # sufficient for lifecycle detection; the Coding Agent
                    # monitor retains create_time for the few matched agents.
                    create_time = info.get("create_time")
                    result[pid] = ProcessInfo(
                        pid=pid,
                        name=name,
                        create_time=float(create_time) if create_time is not None else None,
                    )
                except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError, TypeError, ValueError):
                    continue
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
            return result
        return result

    def _event(self, event_type: EventType, process: ProcessInfo) -> Event:
        important = process.name.casefold() in {
            name.casefold() for name in self.settings.important_processes
        }
        return Event(
            type=event_type,
            source="process_monitor",
            priority=Priority.IMPORTANT if important else Priority.NORMAL,
            data={
                "pid": process.pid,
                "name": process.name,
                "create_time": process.create_time,
            },
        )

    def _publish(self, events: Iterable[Event]) -> None:
        if self.event_bus is None:
            return
        for event in events:
            self.event_bus.publish(event)


def _identity_changed(previous: ProcessInfo, current: ProcessInfo) -> bool:
    if previous.name != current.name:
        return True
    return (
        previous.create_time is not None
        and current.create_time is not None
        and previous.create_time != current.create_time
    )
