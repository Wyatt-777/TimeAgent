"""Dispatch queued events through rules and persistence."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from threading import Event as ThreadEvent
from typing import Callable

from .event import Event
from .event_bus import EventBus
from .event_store import EventStore
from .rule_engine import RuleAction, RuleEngine


@dataclass(frozen=True, slots=True)
class DispatchResult:
    event: Event
    action: RuleAction
    stored: bool


class Dispatcher:
    """Consume events, classify them, persist relevant events and notify hooks."""

    def __init__(
        self,
        event_bus: EventBus,
        event_store: EventStore,
        rule_engine: RuleEngine,
        *,
        on_analyze: Callable[[Event], None] | None = None,
        on_alert: Callable[[Event], None] | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.event_store = event_store
        self.rule_engine = rule_engine
        self.on_analyze = on_analyze
        self.on_alert = on_alert
        self._stop_event = ThreadEvent()
        self._thread: threading.Thread | None = None

    def dispatch_once(self, timeout: float | None = None) -> DispatchResult | None:
        event = self.event_bus.consume(timeout=timeout)
        if event is None:
            return None
        action = self.rule_engine.classify(event)
        stored = action is not RuleAction.IGNORE
        if stored:
            self.event_store.insert(event)
        if action is RuleAction.ANALYZE and self.on_analyze is not None:
            self.on_analyze(event)
        elif action is RuleAction.ALERT and self.on_alert is not None:
            self.on_alert(event)
        return DispatchResult(event=event, action=action, stored=stored)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("Dispatcher is already running")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run, name="event-dispatcher", daemon=True)
        self._thread.start()

    def run(self) -> None:
        while not self._stop_event.is_set():
            self.dispatch_once(timeout=0.2)

    def stop(self, timeout: float | None = None) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
