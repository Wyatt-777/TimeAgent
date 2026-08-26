"""Bounded, non-shell test execution for an explicitly resolved workspace."""

from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum

from .resolver import Workspace


class TestRunStatus(str, Enum):
    __test__ = False

    PASSED = "passed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class TestRunResult:
    status: TestRunStatus
    returncode: int | None
    duration_seconds: float
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    output: str = ""

    @property
    def successful(self) -> bool:
        return self.status is TestRunStatus.PASSED

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "returncode": self.returncode,
            "duration_seconds": self.duration_seconds,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
            "output": self.output,
            "successful": self.successful,
        }


class TestRunner:
    """Run only pytest through the current Python interpreter."""

    __test__ = False

    def __init__(
        self,
        workspace: Workspace,
        *,
        timeout_seconds: float = 300.0,
        max_output_chars: int = 20_000,
    ) -> None:
        if not isinstance(workspace, Workspace):
            raise TypeError("workspace must be a Workspace")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if max_output_chars <= 0:
            raise ValueError("max_output_chars must be greater than zero")
        self.workspace = workspace
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

    def run(self) -> TestRunResult:
        command = (sys.executable, "-m", "pytest", "-q")
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=self.workspace.path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            output = _bounded_output(str(exc.output or ""), self.max_output_chars)
            return TestRunResult(
                status=TestRunStatus.TIMED_OUT,
                returncode=None,
                duration_seconds=time.monotonic() - started,
                output=output,
            )
        except OSError as exc:
            return TestRunResult(
                status=TestRunStatus.ERROR,
                returncode=None,
                duration_seconds=time.monotonic() - started,
                output=str(exc),
            )

        full_output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        counts = parse_pytest_summary(full_output)
        output = _bounded_output(
            full_output,
            self.max_output_chars,
        )
        return TestRunResult(
            status=TestRunStatus.PASSED if completed.returncode == 0 else TestRunStatus.FAILED,
            returncode=completed.returncode,
            duration_seconds=time.monotonic() - started,
            output=output,
            **counts,
        )


def parse_pytest_summary(output: str) -> dict[str, int]:
    def count(label: str) -> int:
        match = re.search(rf"(\d+)\s+{label}", output)
        return int(match.group(1)) if match else 0

    return {
        "passed": count("passed"),
        "failed": count("failed"),
        "skipped": count("skipped"),
        "errors": count("errors?"),
    }


def _bounded_output(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]
