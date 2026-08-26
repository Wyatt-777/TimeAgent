from datetime import datetime, timedelta, timezone

from core.event import EventType
from core.failure_tracker import TestFailureTracker
from core.rule_engine import RuleAction, RuleEngine
from workspace.tests import TestRunResult, TestRunStatus


def failed_result() -> TestRunResult:
    return TestRunResult(status=TestRunStatus.FAILED, returncode=1, duration_seconds=1.0, failed=1)


def passed_result() -> TestRunResult:
    return TestRunResult(status=TestRunStatus.PASSED, returncode=0, duration_seconds=1.0, passed=3)


def test_repeated_failures_create_high_signal_on_threshold() -> None:
    tracker = TestFailureTracker(threshold=3, window_minutes=10)
    start = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)

    assert [event.type for event in tracker.record(failed_result(), project_path="D:/project", timestamp=start)] == [EventType.TEST_FAILED]
    assert [event.type for event in tracker.record(failed_result(), project_path="D:/project", timestamp=start + timedelta(minutes=1))] == [EventType.TEST_FAILED]
    events = tracker.record(failed_result(), project_path="D:/project", timestamp=start + timedelta(minutes=2))

    assert [event.type for event in events] == [EventType.TEST_FAILED, EventType.TEST_FAILED_REPEATEDLY]
    assert events[1].data["consecutive_failures"] == 3
    assert RuleEngine().classify(events[1]) is RuleAction.ALERT


def test_success_resets_consecutive_failures() -> None:
    tracker = TestFailureTracker()
    start = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    tracker.record(failed_result(), project_path="D:/project", timestamp=start)
    tracker.record(passed_result(), project_path="D:/project", timestamp=start + timedelta(minutes=1))

    assert tracker.failure_count(project_path="D:/project") == 0
    assert [event.type for event in tracker.record(failed_result(), project_path="D:/project", timestamp=start + timedelta(minutes=2))] == [EventType.TEST_FAILED]


def test_failures_outside_window_do_not_combine() -> None:
    tracker = TestFailureTracker(threshold=3, window_minutes=10)
    start = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)

    tracker.record(failed_result(), project_path="D:/project", timestamp=start)
    tracker.record(failed_result(), project_path="D:/project", timestamp=start + timedelta(minutes=11))

    assert tracker.failure_count(project_path="D:/project") == 1
