"""Build bounded, provider-neutral context for important events."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Mapping

from core.event import Event
from core.event_store import EventStore


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Structured context passed from the runtime to an Agent Brain."""

    trigger_event: Event
    recent_events: tuple[Event, ...] = ()
    project_state: dict[str, Any] = field(default_factory=dict)
    git_status: dict[str, Any] = field(default_factory=dict)
    agent_config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_event": self.trigger_event.to_dict(),
            "recent_events": [event.to_dict() for event in self.recent_events],
            "project_state": self.project_state,
            "git_status": self.git_status,
            "agent_config": self.agent_config,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


class ContextBuilder:
    """Query a bounded event window and attach optional project context."""

    def __init__(self, event_store: EventStore, *, recent_minutes: int = 30, limit: int = 100) -> None:
        if recent_minutes <= 0:
            raise ValueError("recent_minutes must be greater than zero")
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        self.event_store = event_store
        self.recent_minutes = recent_minutes
        self.limit = limit

    def build(
        self,
        trigger_event: Event,
        *,
        project_state: Mapping[str, Any] | None = None,
        git_status: Mapping[str, Any] | None = None,
        agent_config: Mapping[str, Any] | None = None,
    ) -> AgentContext:
        if not isinstance(trigger_event, Event):
            raise TypeError("trigger_event must be an Event")
        since = trigger_event.timestamp - timedelta(minutes=self.recent_minutes)
        recent = self.event_store.query(
            limit=self.limit,
            since=since,
            until=trigger_event.timestamp,
        )
        if all(event.id != trigger_event.id for event in recent):
            recent.append(trigger_event)
            recent.sort(key=lambda event: event.timestamp)
            recent = recent[-self.limit :]
        return AgentContext(
            trigger_event=trigger_event,
            recent_events=tuple(recent),
            project_state=dict(project_state or {}),
            git_status=dict(git_status or {}),
            agent_config=dict(agent_config or {}),
        )
