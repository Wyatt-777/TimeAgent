"""Bounded Codex CLI launcher restricted to read-only investigations."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence

from .investigation import InvestigationContextPackage, InvestigationTask


class SandboxPolicyError(ValueError):
    """Raised when a launcher command is not read-only."""


@dataclass(frozen=True, slots=True)
class ReadOnlySandboxPolicy:
    """Build the only sandbox and approval flags allowed for investigations."""

    def command_args(self) -> tuple[str, ...]:
        return ("--sandbox", "read-only", "--ask-for-approval", "never", "--ephemeral", "--json")

    def validate(self, command: Sequence[str]) -> None:
        values = tuple(command)
        if "--dangerously-bypass-approvals-and-sandbox" in values:
            raise SandboxPolicyError("dangerous approval and sandbox bypass is forbidden")
        if _flag_value(values, "--sandbox") != "read-only":
            raise SandboxPolicyError("investigation must use the read-only sandbox")
        if _flag_value(values, "--ask-for-approval") != "never":
            raise SandboxPolicyError("investigation must not request approvals")
        if "--ephemeral" not in values:
            raise SandboxPolicyError("investigation sessions must be ephemeral")


class LaunchStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class LaunchResult:
    status: LaunchStatus
    returncode: int | None
    duration_seconds: float
    stdout: str = ""
    stderr: str = ""

    @property
    def successful(self) -> bool:
        return self.status is LaunchStatus.COMPLETED


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class CodexLauncher:
    """Launch Codex with a fixed read-only command envelope."""

    def __init__(
        self,
        *,
        codex_command: str = "codex",
        policy: ReadOnlySandboxPolicy | None = None,
        timeout_seconds: float = 120.0,
        max_output_chars: int = 20_000,
        runner: CommandRunner | None = None,
    ) -> None:
        if not isinstance(codex_command, str) or not codex_command.strip():
            raise ValueError("codex_command must be a non-empty string")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if max_output_chars <= 0:
            raise ValueError("max_output_chars must be greater than zero")
        self.codex_command = codex_command
        self.policy = policy or ReadOnlySandboxPolicy()
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars
        self.runner = runner or subprocess.run

    def launch(self, task: InvestigationTask, context: InvestigationContextPackage) -> LaunchResult:
        if not isinstance(task, InvestigationTask):
            raise TypeError("task must be an InvestigationTask")
        if not isinstance(context, InvestigationContextPackage):
            raise TypeError("context must be an InvestigationContextPackage")
        if task.task_id != context.task.task_id:
            raise ValueError("task and context ids do not match")
        project = Path(task.project_path).expanduser().resolve(strict=False)
        command = (
            self.codex_command,
            "exec",
            *self.policy.command_args(),
            "--cd",
            str(project),
            context.to_prompt(),
        )
        self.policy.validate(command)
        started = time.monotonic()
        try:
            result = self.runner(
                command,
                cwd=project,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return LaunchResult(
                status=LaunchStatus.TIMED_OUT,
                returncode=None,
                duration_seconds=time.monotonic() - started,
                stdout=_bounded(str(exc.stdout or ""), self.max_output_chars),
                stderr=_bounded(str(exc.stderr or ""), self.max_output_chars),
            )
        except OSError as exc:
            return LaunchResult(
                status=LaunchStatus.ERROR,
                returncode=None,
                duration_seconds=time.monotonic() - started,
                stderr=str(exc),
            )
        return LaunchResult(
            status=LaunchStatus.COMPLETED if result.returncode == 0 else LaunchStatus.FAILED,
            returncode=result.returncode,
            duration_seconds=time.monotonic() - started,
            stdout=_bounded(result.stdout or "", self.max_output_chars),
            stderr=_bounded(result.stderr or "", self.max_output_chars),
        )


def _bounded(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[-limit:]


def _flag_value(command: Sequence[str], flag: str) -> str | None:
    try:
        index = tuple(command).index(flag)
        return command[index + 1] if index + 1 < len(command) else None
    except ValueError:
        return None
