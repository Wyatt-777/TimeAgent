"""Configured-directory file monitoring with ignore rules and debounce."""

from __future__ import annotations

import fnmatch
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event as ThreadEvent

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from config.settings import FileMonitorSettings
from core.event import Event, EventType, Priority
from core.event_bus import EventBus


@dataclass(slots=True)
class _PendingChange:
    event_type: EventType
    path: str
    first_seen: float
    last_seen: float
    count: int = 1
    destination: str | None = None

    def to_event(self) -> Event:
        data = {
            "path": self.path,
            "count": self.count,
            "duration_seconds": round(max(0.0, self.last_seen - self.first_seen), 3),
        }
        if self.destination is not None:
            data["destination"] = self.destination
        return Event(
            type=self.event_type,
            source="file_monitor",
            priority=Priority.NORMAL,
            data=data,
            timestamp=datetime.now(timezone.utc),
        )


class _FileEventHandler(FileSystemEventHandler):
    def __init__(self, monitor: "FileMonitor") -> None:
        super().__init__()
        self.monitor = monitor

    def on_created(self, event: FileSystemEvent) -> None:
        self.monitor.handle_event(event, EventType.FILE_CREATED)

    def on_modified(self, event: FileSystemEvent) -> None:
        self.monitor.handle_event(event, EventType.FILE_MODIFIED)

    def on_deleted(self, event: FileSystemEvent) -> None:
        self.monitor.handle_event(event, EventType.FILE_DELETED)

    def on_moved(self, event: FileSystemEvent) -> None:
        self.monitor.handle_event(event, EventType.FILE_MOVED)


class FileMonitor:
    """Observe only configured directories and emit debounced file events."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        settings: FileMonitorSettings | None = None,
        debounce_seconds: float = 0.75,
    ) -> None:
        if debounce_seconds < 0:
            raise ValueError("debounce_seconds cannot be negative")
        self.event_bus = event_bus
        self.settings = settings or FileMonitorSettings()
        self.debounce_seconds = debounce_seconds
        self._pending: dict[tuple[EventType, str, str | None], _PendingChange] = {}
        self._pending_lock = threading.Lock()
        self._stop_event = ThreadEvent()
        self._observer: Observer | None = None
        self._flush_thread: threading.Thread | None = None
        self._handler = _FileEventHandler(self)

    def handle_event(self, event: FileSystemEvent, event_type: EventType) -> None:
        """Accept a watchdog event and add it to the debounce buffer."""
        if event.is_directory:
            return
        path = str(Path(event.src_path))
        destination = str(Path(event.dest_path)) if event_type is EventType.FILE_MOVED else None
        if self.is_ignored(path) or (destination is not None and self.is_ignored(destination)):
            return
        now = time.monotonic()
        key = (event_type, path, destination)
        with self._pending_lock:
            pending = self._pending.get(key)
            if pending is None:
                self._pending[key] = _PendingChange(
                    event_type=event_type,
                    path=path,
                    first_seen=now,
                    last_seen=now,
                    destination=destination,
                )
            else:
                pending.last_seen = now
                pending.count += 1

    def flush_pending(self, force: bool = False) -> list[Event]:
        """Flush changes whose debounce window has elapsed."""
        now = time.monotonic()
        ready: list[_PendingChange] = []
        with self._pending_lock:
            for key, pending in list(self._pending.items()):
                if force or now - pending.last_seen >= self.debounce_seconds:
                    ready.append(self._pending.pop(key))
        events = [pending.to_event() for pending in ready]
        self._publish(events)
        return events

    def is_ignored(self, path: str) -> bool:
        """Match configured directory names and filename glob patterns."""
        candidate = Path(path)
        parts = {part.casefold() for part in candidate.parts}
        filename = candidate.name.casefold()
        for pattern in self.settings.ignore:
            normalized = pattern.casefold()
            if normalized in parts or fnmatch.fnmatchcase(filename, normalized):
                return True
        return False

    def start(self) -> None:
        if not self.settings.enabled:
            return
        if self._observer is not None:
            raise RuntimeError("FileMonitor is already running")
        observer = Observer()
        scheduled = False
        for configured_path in self.settings.paths:
            path = Path(configured_path)
            if not path.is_dir():
                continue
            observer.schedule(self._handler, str(path), recursive=self.settings.recursive)
            scheduled = True
        self._stop_event.clear()
        if scheduled:
            observer.start()
            self._observer = observer
            self._flush_thread = threading.Thread(
                target=self._flush_loop,
                name="file-monitor-flush",
                daemon=True,
            )
            self._flush_thread.start()
        else:
            observer.stop()

    def stop(self, timeout: float | None = None) -> None:
        self._stop_event.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=timeout)
            self._observer = None
        if self._flush_thread is not None:
            self._flush_thread.join(timeout=timeout)
            self._flush_thread = None
        self.flush_pending(force=True)

    def _flush_loop(self) -> None:
        interval = max(0.05, min(0.5, self.debounce_seconds / 2 or 0.05))
        while not self._stop_event.wait(interval):
            self.flush_pending()

    def _publish(self, events: list[Event]) -> None:
        if self.event_bus is None:
            return
        for event in events:
            self.event_bus.publish(event)
