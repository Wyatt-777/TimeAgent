"""Aggregate repeated test failures into a bounded high-priority signal."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Deque

from workspace.tests import TestRunResult

from .event import Event, EventType, Priority


class TestFailureTracker:
    """Track consecutive failures per explicit project and test group."""

    __test__ = False

    def __init__(self, *, threshold: int = 3, window_minutes: int = 10) -> None:
        if threshold <= 1:
            raise ValueError("threshold must be greater than one")
        if window_minutes <= 0:
            raise ValueError("window_minutes must be greater than zero")
        self.threshold = threshold
        self.window = timedelta(minutes=window_minutes)
        self._failures: dict[tuple[str, str], Deque[datetime]] = defaultdict(deque)

    def record(
        self,
        result: TestRunResult,
        *,
        project_path: str | None,
        test_group: str = "default",
        timestamp: datetime | None = None,
    ) -> list[Event]:
        if not isinstance(result, TestRunResult):
            raise TypeError("result must be a TestRunResult")
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if not test_group.strip():
            raise ValueError("test_group must not be empty")

        key = (project_path or "<unresolved-project>", test_group)
        failures = self._failures[key]
        cutoff = timestamp - self.window
        while failures and failures[0] < cutoff:
            failures.popleft()

        if result.successful:
            failures.clear()
            return []

        failures.append(timestamp)
        count = len(failures)
        data = {
            "project_path": project_path,
            "test_group": test_group,
            "consecutive_failures": count,
            "result": result.to_dict(),
        }
        events = [
            Event(
                type=EventType.TEST_FAILED,
                source="test_failure_tracker",
                priority=Priority.IMPORTANT,
                data=data,
            )
        ]
        if count == self.threshold:
            events.append(
                Event(
                    type=EventType.TEST_FAILED_REPEATEDLY,
                    source="test_failure_tracker",
                    priority=Priority.IMPORTANT,
                    data=data,
                )
            )
        return events

    def failure_count(self, *, project_path: str | None, test_group: str = "default") -> int:
        key = (project_path or "<unresolved-project>", test_group)
        return len(self._failures.get(key, ()))
