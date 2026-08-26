"""Resolve paths only inside explicitly configured workspace roots."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class Workspace:
    path: Path
    name: str


@dataclass(frozen=True, slots=True)
class WorkspaceMatch:
    workspace: Workspace
    path: Path
    relative_path: Path


class WorkspaceResolver:
    """Match a path to the most specific configured workspace root."""

    def __init__(self, paths: Iterable[str | Path]) -> None:
        workspaces: list[Workspace] = []
        seen: set[str] = set()
        for raw_path in paths:
            path = Path(raw_path).expanduser().resolve(strict=False)
            key = os.path.normcase(str(path))
            if key in seen:
                continue
            seen.add(key)
            workspaces.append(Workspace(path=path, name=path.name or str(path)))
        self.workspaces = tuple(workspaces)

    def resolve(self, path: str | Path | None) -> WorkspaceMatch | None:
        if path is None or not str(path).strip():
            return None
        candidate = Path(path).expanduser().resolve(strict=False)
        matches = [workspace for workspace in self.workspaces if _is_within(candidate, workspace.path)]
        if not matches:
            return None
        workspace = max(matches, key=lambda item: len(item.path.parts))
        return WorkspaceMatch(
            workspace=workspace,
            path=candidate,
            relative_path=candidate.relative_to(workspace.path),
        )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
