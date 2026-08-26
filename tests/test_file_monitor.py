import time
from pathlib import Path

from config.settings import FileMonitorSettings
from core.event import EventType
from core.event_bus import EventBus
from sensors.file_monitor import FileMonitor
from watchdog.events import FileCreatedEvent, FileModifiedEvent


def test_file_monitor_merges_repeated_modifications() -> None:
    monitor = FileMonitor(debounce_seconds=0.05)
    path = "D:/Projects/demo/main.py"

    monitor.handle_event(FileModifiedEvent(path), EventType.FILE_MODIFIED)
    monitor.handle_event(FileModifiedEvent(path), EventType.FILE_MODIFIED)
    assert monitor.flush_pending() == []

    deadline = time.monotonic() + 1
    events = []
    while not events and time.monotonic() < deadline:
        events = monitor.flush_pending()
        if not events:
            time.sleep(0.01)

    assert len(events) == 1
    assert events[0].type is EventType.FILE_MODIFIED
    assert events[0].data["count"] == 2


def test_file_monitor_aggregates_1000_modifications_into_one_event() -> None:
    monitor = FileMonitor(debounce_seconds=0.05)
    path = "D:/Projects/demo/main.py"

    for _ in range(1000):
        monitor.handle_event(FileModifiedEvent(path), EventType.FILE_MODIFIED)

    events = monitor.flush_pending(force=True)

    assert len(events) == 1
    assert events[0].data["count"] == 1000


def test_file_monitor_applies_ignore_rules_and_publishes() -> None:
    bus = EventBus()
    settings = FileMonitorSettings(paths=("D:/Projects",), ignore=(".git", "*.log"))
    monitor = FileMonitor(event_bus=bus, settings=settings, debounce_seconds=0)

    monitor.handle_event(FileCreatedEvent("D:/Projects/demo/.git/config"), EventType.FILE_CREATED)
    monitor.handle_event(FileCreatedEvent("D:/Projects/demo/run.log"), EventType.FILE_CREATED)
    monitor.handle_event(FileCreatedEvent("D:/Projects/demo/main.py"), EventType.FILE_CREATED)
    events = monitor.flush_pending()

    assert monitor.is_ignored("D:/Projects/demo/.git/config")
    assert monitor.is_ignored("D:/Projects/demo/run.log")
    assert len(events) == 1
    assert events[0].data["path"].endswith("main.py")
    assert bus.consume(timeout=0.1) is events[0]


def test_file_monitor_observes_a_real_directory(tmp_path: Path) -> None:
    bus = EventBus()
    settings = FileMonitorSettings(paths=(str(tmp_path),), recursive=True, ignore=())
    monitor = FileMonitor(event_bus=bus, settings=settings, debounce_seconds=0.05)
    monitor.start()
    try:
        created = tmp_path / "created.txt"
        created.write_text("hello", encoding="utf-8")
        deadline = time.monotonic() + 3
        event = None
        while time.monotonic() < deadline and event is None:
            event = bus.consume(timeout=0.1)
        assert event is not None
        assert event.type is EventType.FILE_CREATED
        assert event.data["path"].endswith("created.txt")
    finally:
        monitor.stop(timeout=2)
