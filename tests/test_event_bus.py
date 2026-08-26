import threading

import pytest

from core.event import Event, EventType
from core.event_bus import EventBus


def test_publish_and_consume() -> None:
    bus = EventBus()
    event = Event(type=EventType.AGENT_STARTED, source="test")

    bus.publish(event)

    assert bus.consume(timeout=0.1) is event


def test_consume_returns_none_after_timeout() -> None:
    bus = EventBus()

    assert bus.consume(timeout=0.01) is None


def test_shutdown_wakes_blocked_consumer_and_rejects_new_events() -> None:
    bus = EventBus()
    result: list[Event | None] = []

    consumer = threading.Thread(target=lambda: result.append(bus.consume(timeout=1)))
    consumer.start()
    bus.shutdown()
    consumer.join(timeout=1)

    assert result == [None]
    assert bus.is_shutdown
    with pytest.raises(RuntimeError, match="shut down"):
        bus.publish(Event(type=EventType.AGENT_STOPPED, source="test"))


def test_shutdown_is_idempotent() -> None:
    bus = EventBus()

    bus.shutdown()
    bus.shutdown()

    assert bus.is_shutdown
