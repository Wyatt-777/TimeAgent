"""Low-cost event classification before persistence or later analysis."""

from __future__ import annotations

from enum import Enum
from typing import Iterable

from .event import Event, EventType, Priority


class RuleAction(str, Enum):
    IGNORE = "IGNORE"
    STORE = "STORE"
    ANALYZE = "ANALYZE"
    ALERT = "ALERT"


class RuleEngine:
    """Classify events without invoking an LLM or performing side effects."""

    def __init__(self, important_processes: Iterable[str] = ()) -> None:
        self.important_processes = {name.casefold() for name in important_processes}

    def classify(self, event: Event) -> RuleAction:
        if not isinstance(event, Event):
            raise TypeError("RuleEngine accepts Event instances only")
        if event.priority == Priority.DEBUG:
            return RuleAction.IGNORE
        if event.type is EventType.CODING_SESSION_FINISHED:
            return RuleAction.ANALYZE
        if event.type in {
            EventType.SYSTEM_CPU_HIGH,
            EventType.SYSTEM_MEMORY_HIGH,
            EventType.SYSTEM_DISK_LOW,
            EventType.AGENT_ERROR,
            EventType.TEST_FAILED_REPEATEDLY,
        }:
            return RuleAction.ALERT
        if event.type is EventType.PROCESS_STOPPED:
            process_name = str(event.data.get("name", "")).casefold()
            if process_name in self.important_processes:
                return RuleAction.ANALYZE
        return RuleAction.STORE
