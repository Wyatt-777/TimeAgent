from config.settings import WindowMonitorSettings
from core.event import EventType
from core.event_bus import EventBus
from sensors.window_monitor import WindowMonitor


def test_window_monitor_emits_only_on_title_change(monkeypatch) -> None:
    titles = iter(["VS Code", "VS Code", "Windows Terminal"])
    monkeypatch.setattr("sensors.window_monitor.win32gui.GetForegroundWindow", lambda: 123)
    monkeypatch.setattr("sensors.window_monitor.win32gui.GetWindowText", lambda _hwnd: next(titles))
    bus = EventBus()
    monitor = WindowMonitor(event_bus=bus)

    first = monitor.scan_once()
    unchanged = monitor.scan_once()
    changed = monitor.scan_once()

    assert first is not None
    assert first.type is EventType.ACTIVE_WINDOW_CHANGED
    assert first.data == {"title": "VS Code"}
    assert unchanged is None
    assert changed is not None
    assert changed.data["title"] == "Windows Terminal"
    assert bus.consume(timeout=0.1) is first
    assert bus.consume(timeout=0.1) is changed


def test_window_monitor_handles_windows_api_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "sensors.window_monitor.win32gui.GetForegroundWindow",
        lambda: (_ for _ in ()).throw(OSError("access denied")),
    )
    monitor = WindowMonitor(settings=WindowMonitorSettings())

    assert monitor.scan_once() is None
