import psutil

from config.settings import CodingAgentMonitorSettings
from core.event import EventType, Priority
from core.event_bus import EventBus
from core.session_store import SessionStore
from sensors.coding_agent_monitor import CodingAgentMonitor
from workspace.resolver import WorkspaceResolver


class FakeProcess:
    def __init__(self, info, cwd=None):
        self.info = info
        self._cwd = cwd

    def cwd(self):
        if self._cwd is None:
            raise psutil.AccessDenied(pid=self.info.get("pid"))
        return self._cwd


class DeniedProcess:
    @property
    def info(self):
        raise psutil.AccessDenied(pid=99)


def test_monitor_detects_session_start_and_finish(monkeypatch) -> None:
    snapshots = [
        [FakeProcess({"pid": 7, "name": "codex.exe", "create_time": 1.0})],
        [
            FakeProcess({"pid": 7, "name": "codex.exe", "create_time": 1.0}),
            FakeProcess({"pid": 8, "name": "claude.exe", "create_time": 2.0}),
        ],
        [FakeProcess({"pid": 7, "name": "codex.exe", "create_time": 1.0})],
    ]
    monkeypatch.setattr("sensors.coding_agent_monitor.psutil.process_iter", lambda _attrs: snapshots.pop(0))
    bus = EventBus()
    monitor = CodingAgentMonitor(
        event_bus=bus,
        settings=CodingAgentMonitorSettings(process_names=("codex.exe", "claude.exe")),
    )

    assert monitor.scan_once() == []
    started = monitor.scan_once()
    finished = monitor.scan_once()

    assert [event.type for event in started] == [EventType.CODING_SESSION_STARTED]
    assert started[0].priority == Priority.IMPORTANT
    assert started[0].data["agent_name"] == "claude.exe"
    assert [event.type for event in finished] == [EventType.CODING_SESSION_FINISHED]
    assert finished[0].data["session_id"] == started[0].data["session_id"]
    assert finished[0].data["duration_seconds"] >= 0
    assert bus.consume(timeout=0.1) is started[0]


def test_monitor_ignores_unconfigured_processes_and_access_denied(monkeypatch) -> None:
    snapshots = [
        [DeniedProcess(), FakeProcess({"pid": 1, "name": "Code.exe", "create_time": 1.0})],
        [
            DeniedProcess(),
            FakeProcess({"pid": 1, "name": "Code.exe", "create_time": 1.0}),
            FakeProcess({"pid": 2, "name": "codex.exe", "create_time": 2.0}),
        ],
    ]
    monkeypatch.setattr("sensors.coding_agent_monitor.psutil.process_iter", lambda _attrs: snapshots.pop(0))
    monitor = CodingAgentMonitor(settings=CodingAgentMonitorSettings(process_names=("codex.exe",)))

    monitor.scan_once()
    events = monitor.scan_once()

    assert len(events) == 1
    assert events[0].data["agent_name"] == "codex.exe"


def test_monitor_detects_pid_reuse_as_new_session(monkeypatch) -> None:
    snapshots = [
        [FakeProcess({"pid": 3, "name": "codex.exe", "create_time": 1.0})],
        [FakeProcess({"pid": 3, "name": "codex.exe", "create_time": 2.0})],
    ]
    monkeypatch.setattr("sensors.coding_agent_monitor.psutil.process_iter", lambda _attrs: snapshots.pop(0))
    monitor = CodingAgentMonitor()

    monitor.scan_once()
    events = monitor.scan_once()

    assert [event.type for event in events] == [
        EventType.CODING_SESSION_FINISHED,
        EventType.CODING_SESSION_STARTED,
    ]
    assert events[0].data["session_id"] != events[1].data["session_id"]


def test_disabled_monitor_does_not_start_thread() -> None:
    monitor = CodingAgentMonitor(settings=CodingAgentMonitorSettings(enabled=False))

    monitor.start()

    assert monitor._thread is None


def test_monitor_attaches_only_configured_project_root(monkeypatch, tmp_path) -> None:
    project = tmp_path / "project"
    process = FakeProcess(
        {"pid": 10, "name": "codex.exe", "create_time": 1.0},
        cwd=str(project / "src"),
    )
    snapshots = [[process], [process]]
    monkeypatch.setattr("sensors.coding_agent_monitor.psutil.process_iter", lambda _attrs: snapshots.pop(0))
    monitor = CodingAgentMonitor(workspace_resolver=WorkspaceResolver([project]))

    monitor.scan_once()

    assert monitor.active_sessions()[0].project_path == str(project.resolve())


def test_monitor_does_not_request_cwd_for_every_process(monkeypatch) -> None:
    requested = []
    monkeypatch.setattr(
        "sensors.coding_agent_monitor.psutil.process_iter",
        lambda attrs: requested.append(tuple(attrs)) or [],
    )

    CodingAgentMonitor().scan_once()

    assert requested == [("pid", "name", "create_time")]


def test_monitor_persists_active_and_finished_sessions(monkeypatch, tmp_path) -> None:
    process = FakeProcess({"pid": 10, "name": "codex.exe", "create_time": 1.0})
    snapshots = [[process], [], []]
    monkeypatch.setattr("sensors.coding_agent_monitor.psutil.process_iter", lambda _attrs: snapshots.pop(0))

    with SessionStore(tmp_path / "agent.db") as store:
        monitor = CodingAgentMonitor(session_store=store)

        assert monitor.scan_once() == []
        assert [session.session_id for session in store.list_active()] == [monitor.active_sessions()[0].session_id]

        finished = monitor.scan_once()

        assert [event.type for event in finished] == [EventType.CODING_SESSION_FINISHED]
        assert store.list_active() == []

        monitor.scan_once()
        assert store.list_active() == []
