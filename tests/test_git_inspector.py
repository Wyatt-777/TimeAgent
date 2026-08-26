import subprocess
from pathlib import Path

import pytest

from workspace.git import GitCommandError, GitInspector, parse_status
from workspace.resolver import Workspace


def test_parse_porcelain_status() -> None:
    status = parse_status(
        "## master...origin/master [ahead 2, behind 1]\n"
        "M  staged.py\n"
        " M changed.py\n"
        "?? new.py\n"
        "UU conflict.py\n"
    )

    assert status.branch == "master"
    assert status.ahead == 2
    assert status.behind == 1
    assert status.staged == ("staged.py", "conflict.py")
    assert status.unstaged == ("changed.py", "conflict.py")
    assert status.untracked == ("new.py",)
    assert status.conflicted == ("conflict.py",)
    assert status.clean is False


def test_inspector_runs_only_fixed_read_only_query(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return subprocess.CompletedProcess(arguments, 0, "## main\n", "")

    monkeypatch.setattr("workspace.git.subprocess.run", fake_run)
    inspector = GitInspector(Workspace(tmp_path, "project"))

    assert inspector.status().branch == "main"
    assert calls[0][0] == ("git", "status", "--porcelain=v1", "--branch")
    assert calls[0][1]["cwd"] == tmp_path


def test_inspector_surfaces_git_failures(monkeypatch, tmp_path: Path) -> None:
    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(("git",), 128, "", "not a repository")

    monkeypatch.setattr("workspace.git.subprocess.run", fake_run)

    with pytest.raises(GitCommandError, match="not a repository"):
        GitInspector(Workspace(tmp_path, "project")).status()
