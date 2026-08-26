import subprocess
from pathlib import Path

from workspace.resolver import Workspace
from workspace.tests import TestRunStatus, TestRunner, parse_pytest_summary


def test_parse_pytest_summary() -> None:
    counts = parse_pytest_summary("10 passed, 2 failed, 1 skipped, 1 error in 3.2s")

    assert counts == {"passed": 10, "failed": 2, "skipped": 1, "errors": 1}


def test_runner_uses_current_python_and_parses_success(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "10 passed, 1 skipped in 1s", "")

    monkeypatch.setattr("workspace.tests.subprocess.run", fake_run)
    result = TestRunner(Workspace(tmp_path, "project")).run()

    assert result.status is TestRunStatus.PASSED
    assert result.passed == 10
    assert result.skipped == 1
    assert calls[0][0][1:] == ("-m", "pytest", "-q")
    assert calls[0][1]["cwd"] == tmp_path


def test_runner_reports_failure_and_bounds_output(monkeypatch, tmp_path: Path) -> None:
    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, "1 failed in 1s", "details")

    monkeypatch.setattr("workspace.tests.subprocess.run", fake_run)
    result = TestRunner(Workspace(tmp_path, "project"), max_output_chars=10).run()

    assert result.status is TestRunStatus.FAILED
    assert result.failed == 1
    assert len(result.output) <= 10


def test_runner_reports_timeout(monkeypatch, tmp_path: Path) -> None:
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("pytest", 1, output="timed out")

    monkeypatch.setattr("workspace.tests.subprocess.run", fake_run)
    result = TestRunner(Workspace(tmp_path, "project")).run()

    assert result.status is TestRunStatus.TIMED_OUT
    assert result.successful is False
