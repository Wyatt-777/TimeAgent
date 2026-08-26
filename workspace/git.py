"""Read-only Git inspection for explicitly resolved workspaces."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .resolver import Workspace


class GitCommandError(RuntimeError):
    """Raised when a read-only Git query cannot be completed."""


@dataclass(frozen=True, slots=True)
class GitStatus:
    branch: str | None
    ahead: int = 0
    behind: int = 0
    staged: tuple[str, ...] = ()
    unstaged: tuple[str, ...] = ()
    untracked: tuple[str, ...] = ()
    conflicted: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        return not (self.staged or self.unstaged or self.untracked or self.conflicted)

    def to_dict(self) -> dict[str, object]:
        return {
            "branch": self.branch,
            "ahead": self.ahead,
            "behind": self.behind,
            "staged": list(self.staged),
            "unstaged": list(self.unstaged),
            "untracked": list(self.untracked),
            "conflicted": list(self.conflicted),
            "clean": self.clean,
        }


@dataclass(frozen=True, slots=True)
class GitDiffFile:
    path: str
    additions: int | None
    deletions: int | None


@dataclass(frozen=True, slots=True)
class GitDiffStat:
    files: tuple[GitDiffFile, ...] = ()

    @property
    def additions(self) -> int:
        return sum(item.additions or 0 for item in self.files)

    @property
    def deletions(self) -> int:
        return sum(item.deletions or 0 for item in self.files)

    def to_dict(self) -> dict[str, object]:
        return {
            "files": [
                {
                    "path": item.path,
                    "additions": item.additions,
                    "deletions": item.deletions,
                }
                for item in self.files
            ],
            "additions": self.additions,
            "deletions": self.deletions,
        }


class GitInspector:
    """Run a fixed, read-only Git status query in one workspace."""

    def __init__(self, workspace: Workspace, *, timeout_seconds: float = 10.0) -> None:
        if not isinstance(workspace, Workspace):
            raise TypeError("workspace must be a Workspace")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self.workspace = workspace
        self.timeout_seconds = timeout_seconds

    def status(self) -> GitStatus:
        result = self._run(("status", "--porcelain=v1", "--branch"))
        return parse_status(result.stdout)

    def diff_stat(self) -> GitDiffStat:
        result = self._run(("diff", "--numstat", "--no-ext-diff", "--"))
        return parse_diff_numstat(result.stdout)

    def _run(self, arguments: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                ("git", *arguments),
                cwd=self.workspace.path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitCommandError(f"unable to run git query in {self.workspace.path}") from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or "unknown git error"
            raise GitCommandError(detail)
        return result


def parse_status(output: str) -> GitStatus:
    """Parse porcelain-v1 status output without exposing command details."""
    branch: str | None = None
    ahead = behind = 0
    staged: list[str] = []
    unstaged: list[str] = []
    untracked: list[str] = []
    conflicted: list[str] = []

    for line in output.splitlines():
        if line.startswith("## "):
            branch, ahead, behind = _parse_branch(line[3:])
            continue
        if len(line) < 3:
            continue
        index, worktree, path = line[0], line[1], line[3:]
        if index == "?" and worktree == "?":
            untracked.append(path)
            continue
        if (index in {"U", "A"} and worktree == "U") or (index == "U" and worktree in {"D", "A"}):
            conflicted.append(path)
        if index not in {" ", "?"}:
            staged.append(path)
        if worktree not in {" ", "?"}:
            unstaged.append(path)

    return GitStatus(
        branch=branch,
        ahead=ahead,
        behind=behind,
        staged=tuple(staged),
        unstaged=tuple(unstaged),
        untracked=tuple(untracked),
        conflicted=tuple(conflicted),
    )


def parse_diff_numstat(output: str) -> GitDiffStat:
    files: list[GitDiffFile] = []
    for line in output.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        additions = _diff_count(parts[0])
        deletions = _diff_count(parts[1])
        files.append(GitDiffFile(path=parts[2], additions=additions, deletions=deletions))
    return GitDiffStat(files=tuple(files))


def _parse_branch(value: str) -> tuple[str | None, int, int]:
    if value == "No commits yet on HEAD":
        return "HEAD", 0, 0
    branch = value.split("...", 1)[0].strip() or None
    ahead_match = re.search(r"ahead (\d+)", value)
    behind_match = re.search(r"behind (\d+)", value)
    return branch, int(ahead_match.group(1)) if ahead_match else 0, int(behind_match.group(1)) if behind_match else 0


def _diff_count(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None
