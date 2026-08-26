"""Runtime composition and graceful sensor/dispatcher lifecycle."""

from __future__ import annotations

import logging
import threading
from typing import Protocol, Sequence

from config.settings import Settings

from .dispatcher import Dispatcher
from .event import Event, EventType
from .event_bus import EventBus
from .event_store import EventStore
from .rule_engine import RuleEngine


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
    ) -> None:
        settings.validate()
        self.settings = settings
        self.logger = logger or logging.getLogger("local_pc_agent")
        self.event_bus = EventBus()
        self.event_store = EventStore(settings.storage.sqlite_path)
        self.rule_engine = RuleEngine(settings.process_monitor.important_processes)
        self.dispatcher = Dispatcher(self.event_bus, self.event_store, self.rule_engine)
        if sensors is None:
            from sensors.file_monitor import FileMonitor
            from sensors.process_monitor import ProcessMonitor
            from sensors.window_monitor import WindowMonitor

            sensors = (
                ProcessMonitor(self.event_bus, settings.process_monitor),
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
                self.event_store.close()
                raise

    def shutdown(self, timeout: float | None = 5) -> None:
        with self._lock:
            if not self._started:
                self.event_store.close()
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
            self._started = False

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
