"""Active foreground-window title monitoring for Windows."""

from __future__ import annotations

import threading
from threading import Event as ThreadEvent

import win32gui

from config.settings import WindowMonitorSettings
from core.event import Event, EventType, Priority
from core.event_bus import EventBus


class WindowMonitor:
    """Poll the foreground window and emit only title changes."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        settings: WindowMonitorSettings | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.settings = settings or WindowMonitorSettings()
        self._last_title: str | None = None
        self._stop_event = ThreadEvent()
        self._thread: threading.Thread | None = None

    def scan_once(self) -> Event | None:
        """Read the foreground title and emit an event only when it changes."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
        except (OSError, RuntimeError):
            return None
        if title == self._last_title:
            return None
        self._last_title = title
        event = Event(
            type=EventType.ACTIVE_WINDOW_CHANGED,
            source="window_monitor",
            priority=Priority.NORMAL,
            data={"title": title},
        )
        if self.event_bus is not None:
            self.event_bus.publish(event)
        return event

    def start(self) -> None:
        if not self.settings.enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("WindowMonitor is already running")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run, name="window-monitor", daemon=True)
        self._thread.start()

    def run(self) -> None:
        self.scan_once()
        while not self._stop_event.wait(self.settings.interval_seconds):
            self.scan_once()

    def stop(self, timeout: float | None = None) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
