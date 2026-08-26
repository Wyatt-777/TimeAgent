from core.event import Event, EventType, Priority
from core.rule_engine import RuleAction, RuleEngine


def test_file_modification_is_stored() -> None:
    engine = RuleEngine()
    event = Event(type=EventType.FILE_MODIFIED, source="file_monitor")

    assert engine.classify(event) is RuleAction.STORE


def test_important_process_stop_is_analyzed() -> None:
    engine = RuleEngine(important_processes=("Code.exe",))
    event = Event(
        type=EventType.PROCESS_STOPPED,
        source="process_monitor",
        data={"name": "code.exe"},
    )

    assert engine.classify(event) is RuleAction.ANALYZE


def test_system_failure_is_alerted() -> None:
    engine = RuleEngine()
    event = Event(type=EventType.SYSTEM_DISK_LOW, source="system_monitor")

    assert engine.classify(event) is RuleAction.ALERT


def test_debug_event_is_ignored() -> None:
    engine = RuleEngine()
    event = Event(type=EventType.AGENT_STARTED, source="lifecycle", priority=Priority.DEBUG)

    assert engine.classify(event) is RuleAction.IGNORE
