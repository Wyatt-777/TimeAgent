import time

from core.dispatcher import Dispatcher
from core.event import Event, EventType, Priority
from core.event_bus import EventBus
from core.event_store import EventStore
from core.rule_engine import RuleAction, RuleEngine


def test_dispatcher_persists_stores_and_routes_actions(tmp_path) -> None:
    bus = EventBus()
    analyzed: list[Event] = []
    alerted: list[Event] = []
    with EventStore(tmp_path / "agent.db") as store:
        dispatcher = Dispatcher(
            bus,
            store,
            RuleEngine(important_processes=("Code.exe",)),
            on_analyze=analyzed.append,
            on_alert=alerted.append,
        )
        stored_event = Event(type=EventType.FILE_MODIFIED, source="file_monitor")
        analyze_event = Event(
            type=EventType.PROCESS_STOPPED,
            source="process_monitor",
            data={"name": "Code.exe"},
        )
        alert_event = Event(type=EventType.SYSTEM_DISK_LOW, source="system_monitor")
        ignored_event = Event(
            type=EventType.AGENT_STARTED,
            source="lifecycle",
            priority=Priority.DEBUG,
        )
        for event in (stored_event, analyze_event, alert_event, ignored_event):
            bus.publish(event)

        results = [dispatcher.dispatch_once(timeout=0.1) for _ in range(4)]

        assert [result.action for result in results if result is not None] == [
            RuleAction.STORE,
            RuleAction.ANALYZE,
            RuleAction.ALERT,
            RuleAction.IGNORE,
        ]
        assert store.count() == 3
        assert analyzed == [analyze_event]
        assert alerted == [alert_event]
        assert results[-1].stored is False


def test_dispatcher_background_loop_processes_events(tmp_path) -> None:
    bus = EventBus()
    with EventStore(tmp_path / "agent.db") as store:
        dispatcher = Dispatcher(bus, store, RuleEngine())
        dispatcher.start()
        bus.publish(Event(type=EventType.AGENT_STARTED, source="lifecycle"))
        deadline = time.monotonic() + 2
        while store.count() < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        dispatcher.stop(timeout=2)

        assert store.count() == 1
