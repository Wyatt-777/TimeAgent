import psutil

from config.settings import ProcessMonitorSettings
from core.event import EventType, Priority
from core.event_bus import EventBus
from sensors.process_monitor import ProcessMonitor


class FakeProcess:
    def __init__(self, info):
        self.info = info


class DeniedProcess:
    @property
    def info(self):
        raise psutil.AccessDenied(pid=99)


def test_process_monitor_detects_start_and_stop(monkeypatch) -> None:
    snapshots = [
        [FakeProcess({"pid": 1, "name": "system.exe", "create_time": 1.0})],
        [
            FakeProcess({"pid": 1, "name": "system.exe", "create_time": 1.0}),
            FakeProcess({"pid": 2, "name": "Code.exe", "create_time": 2.0}),
        ],
        [FakeProcess({"pid": 1, "name": "system.exe", "create_time": 1.0})],
    ]

    monkeypatch.setattr("sensors.process_monitor.psutil.process_iter", lambda _attrs: snapshots.pop(0))
    monitor = ProcessMonitor(settings=ProcessMonitorSettings(important_processes=("Code.exe",)))

    assert monitor.scan_once() == []
    started = monitor.scan_once()
    stopped = monitor.scan_once()

    assert [event.type for event in started] == [EventType.PROCESS_STARTED]
    assert started[0].data["pid"] == 2
    assert started[0].priority == Priority.IMPORTANT
    assert [event.type for event in stopped] == [EventType.PROCESS_STOPPED]


def test_process_monitor_publishes_to_bus_and_ignores_access_denied(monkeypatch) -> None:
    snapshots = [
        [DeniedProcess(), FakeProcess({"pid": 1, "name": "python.exe", "create_time": 1.0})],
        [DeniedProcess(), FakeProcess({"pid": 1, "name": "python.exe", "create_time": 1.0}), FakeProcess({"pid": 2, "name": "worker.exe", "create_time": 2.0})],
    ]
    monkeypatch.setattr("sensors.process_monitor.psutil.process_iter", lambda _attrs: snapshots.pop(0))
    bus = EventBus()
    monitor = ProcessMonitor(event_bus=bus)

    monitor.scan_once()
    events = monitor.scan_once()

    assert len(events) == 1
    assert bus.consume(timeout=0.1) is events[0]


def test_disabled_process_monitor_does_not_start_a_thread() -> None:
    monitor = ProcessMonitor(settings=ProcessMonitorSettings(enabled=False))

    monitor.start()

    assert monitor._thread is None
