import time

from config.settings import Settings, StorageSettings
from core.event import EventType
from core.lifecycle import Runtime
from core.event_store import EventStore


class FakeSensor:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def stop(self, timeout=None) -> None:
        self.stopped += 1


def test_runtime_starts_drains_and_stops_gracefully(tmp_path) -> None:
    database = tmp_path / "agent.db"
    settings = Settings(storage=StorageSettings(sqlite_path=str(database)))
    sensor = FakeSensor()
    runtime = Runtime(settings, sensors=(sensor,))

    runtime.start()
    deadline = time.monotonic() + 2
    while runtime.event_store.count() < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    runtime.shutdown(timeout=2)

    assert sensor.started == 1
    assert sensor.stopped == 1
    assert not runtime.is_running
    with EventStore(database) as store:
        events = store.query(limit=10)
    assert [event.type for event in events] == [EventType.AGENT_STARTED, EventType.AGENT_STOPPED]


def test_runtime_shutdown_is_idempotent(tmp_path) -> None:
    settings = Settings(storage=StorageSettings(sqlite_path=str(tmp_path / "agent.db")))
    runtime = Runtime(settings, sensors=())

    runtime.shutdown()
    runtime.shutdown()

    assert not runtime.is_running
