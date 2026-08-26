import subprocess

from core.event import EventType, Priority
from core.event_bus import EventBus
from core.event_store import EventStore
from integrations.codex.hooks import (
    HookAdapter,
    HookAdapterError,
    detect_hook_capabilities,
)


def _runner(responses):
    def run(args):
        return responses[tuple(args)]

    return run


def test_detect_hook_capabilities_reads_feature_and_version() -> None:
    runner = _runner(
        {
            ("codex", "--version"): subprocess.CompletedProcess(
                (), 0, stdout="codex-cli 0.150.0-alpha.8\n", stderr=""
            ),
            ("codex", "features", "list"): subprocess.CompletedProcess(
                (), 0, stdout="hooks                                    stable             true\n", stderr=""
            ),
        }
    )

    report = detect_hook_capabilities(runner=runner)

    assert report.available is True
    assert report.codex_version == "codex-cli 0.150.0-alpha.8"
    assert "SessionStart" in report.supported_events


def test_detect_hook_capabilities_reports_disabled_hooks() -> None:
    runner = _runner(
        {
            ("codex", "--version"): subprocess.CompletedProcess((), 0, stdout="codex\n", stderr=""),
            ("codex", "features", "list"): subprocess.CompletedProcess(
                (), 0, stdout="hooks stable false\n", stderr=""
            ),
        }
    )

    report = detect_hook_capabilities(runner=runner)

    assert report.available is False
    assert report.supported_events == ()
    assert report.reason == "Codex hooks feature is disabled"


def test_hook_adapter_normalizes_session_start_without_sensitive_payload() -> None:
    adapter = HookAdapter()

    event = adapter.adapt(
        {
            "hook_event_name": "SessionStart",
            "session_id": "thr_123",
            "cwd": "D:/project",
            "transcript_path": "D:/private/transcript.jsonl",
            "source": "startup",
        }
    )

    assert event is not None
    assert event.type is EventType.CODEX_SESSION_STARTED
    assert event.priority is Priority.IMPORTANT
    assert event.data == {
        "session_id": "thr_123",
        "cwd": "D:/project",
        "hook_event_name": "SessionStart",
        "source": "startup",
    }
    assert "transcript_path" not in event.data


def test_hook_adapter_publishes_tool_activity() -> None:
    bus = EventBus()
    adapter = HookAdapter(bus)

    event = adapter.handle(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "thr_123",
            "cwd": "D:/project",
            "tool_name": "Bash",
            "tool_input": {"command": "secret should not be persisted here"},
        }
    )

    assert event is not None
    assert event.type is EventType.CODEX_TOOL_ACTIVITY
    assert bus.consume(timeout=0.1) is event
    assert "tool_input" not in event.data


def test_hook_adapter_deduplicates_repeated_lifecycle_payloads(tmp_path) -> None:
    payload = {"hook_event_name": "SessionStart", "session_id": "thr_123", "cwd": "D:/project"}
    with EventStore(tmp_path / "agent.db") as store:
        adapter = HookAdapter(event_store=store)

        first = adapter.handle(payload)
        second = adapter.handle(payload)

        assert first is not None and second is not None
        assert first.id == second.id
        assert store.count() == 1


def test_disabled_hook_adapter_is_a_noop() -> None:
    adapter = HookAdapter(enabled=False)

    assert adapter.handle({"hook_event_name": "SessionStart"}) is None


def test_hook_adapter_rejects_unknown_payload() -> None:
    adapter = HookAdapter()

    try:
        adapter.adapt({"hook_event_name": "Unknown"})
    except HookAdapterError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("expected HookAdapterError")
