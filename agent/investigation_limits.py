"""Bounded invocation limits for the optional investigation layer."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock


class InvestigationLimitExceeded(RuntimeError):
    """Raised when the configured investigation invocation budget is exhausted."""


@dataclass(frozen=True, slots=True)
class InvocationBudget:
    max_invocations: int = 3
    window_seconds: float = 3600.0

    def __post_init__(self) -> None:
        if self.max_invocations <= 0:
            raise ValueError("max_invocations must be greater than zero")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be greater than zero")


class InvocationLimiter:
    """Keep a small in-memory rolling budget; no billing API is contacted."""

    def __init__(self, budget: InvocationBudget | None = None) -> None:
        self.budget = budget or InvocationBudget()
        self._timestamps: deque[datetime] = deque()
        self._lock = Lock()

    def acquire(self, *, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        with self._lock:
            cutoff = timestamp - timedelta(seconds=self.budget.window_seconds)
            while self._timestamps and self._timestamps[0] <= cutoff:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.budget.max_invocations:
                raise InvestigationLimitExceeded("investigation invocation limit reached")
            self._timestamps.append(timestamp)

    def remaining(self, *, now: datetime | None = None) -> int:
        timestamp = now or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        with self._lock:
            cutoff = timestamp - timedelta(seconds=self.budget.window_seconds)
            while self._timestamps and self._timestamps[0] <= cutoff:
                self._timestamps.popleft()
            return self.budget.max_invocations - len(self._timestamps)
