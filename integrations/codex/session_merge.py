"""Merge process-based and Codex Hook-based active sessions safely."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from core.event import Event, EventType
from sensors.coding_agent_monitor import CodingAgentSession


@dataclass(frozen=True, slots=True)
class MergedCodingSession:
    """One logical active session assembled from one or more observers."""

    session_id: str
    agent_name: str
    pid: int | None
    started_at: datetime
    project_path: str | None
    codex_session_id: str | None = None
    process_session_id: str | None = None
    sources: tuple[str, ...] = ()


class SessionMerger:
    """Correlate active process and Hook sessions without making either required."""

    def __init__(self, *, match_window_seconds: float = 300.0) -> None:
        if match_window_seconds <= 0:
            raise ValueError("match_window_seconds must be greater than zero")
        self.match_window_seconds = match_window_seconds

    def merge(
        self,
        process_sessions: Iterable[CodingAgentSession],
        hook_events: Iterable[Event],
    ) -> tuple[MergedCodingSession, ...]:
        processes = tuple(process_sessions)
        hooks = _active_hook_sessions(hook_events)
        matched_processes: set[str] = set()
        merged: list[MergedCodingSession] = []

        for hook in hooks:
            match = self._best_process_match(hook, processes, matched_processes)
            if match is None:
                merged.append(
                    MergedCodingSession(
                        session_id=f"codex:{hook.session_id}",
                        agent_name="codex",
                        pid=None,
                        started_at=hook.started_at,
                        project_path=hook.cwd,
                        codex_session_id=hook.session_id,
                        sources=("codex_hook_adapter",),
                    )
                )
                continue
            matched_processes.add(match.session_id)
            merged.append(
                MergedCodingSession(
                    session_id=match.session_id,
                    agent_name=match.agent_name,
                    pid=match.pid,
                    started_at=min(match.started_at, hook.started_at),
                    project_path=match.project_path or hook.cwd,
                    codex_session_id=hook.session_id,
                    process_session_id=match.session_id,
                    sources=("process_monitor", "codex_hook_adapter"),
                )
            )

        for process in processes:
            if process.session_id not in matched_processes:
                merged.append(
                    MergedCodingSession(
                        session_id=process.session_id,
                        agent_name=process.agent_name,
                        pid=process.pid,
                        started_at=process.started_at,
                        project_path=process.project_path,
                        process_session_id=process.session_id,
                        sources=("process_monitor",),
                    )
                )
        return tuple(sorted(merged, key=lambda session: (session.started_at, session.session_id)))

    def _best_process_match(
        self,
        hook: "_HookSession",
        processes: tuple[CodingAgentSession, ...],
        matched_processes: set[str],
    ) -> CodingAgentSession | None:
        candidates = [
            process
            for process in processes
            if process.session_id not in matched_processes
            and _paths_match(hook.cwd, process.project_path)
            and abs((process.started_at - hook.started_at).total_seconds()) <= self.match_window_seconds
        ]
        return min(candidates, key=lambda process: abs((process.started_at - hook.started_at).total_seconds()), default=None)


@dataclass(frozen=True, slots=True)
class _HookSession:
    session_id: str
    started_at: datetime
    cwd: str | None


def _active_hook_sessions(events: Iterable[Event]) -> tuple[_HookSession, ...]:
    starts: dict[str, _HookSession] = {}
    finished: set[str] = set()
    for event in events:
        if event.type not in {EventType.CODEX_SESSION_STARTED, EventType.CODEX_SESSION_FINISHED}:
            continue
        session_id = event.data.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            continue
        if event.type is EventType.CODEX_SESSION_FINISHED:
            finished.add(session_id)
            continue
        cwd = event.data.get("cwd")
        starts.setdefault(
            session_id,
            _HookSession(session_id=session_id, started_at=event.timestamp, cwd=cwd if isinstance(cwd, str) else None),
        )
    return tuple(session for session_id, session in starts.items() if session_id not in finished)


def _paths_match(cwd: str | None, project_path: str | None) -> bool:
    if not cwd or not project_path:
        return False
    try:
        cwd_path = Path(cwd).expanduser().resolve()
        project = Path(project_path).expanduser().resolve()
        return cwd_path == project or project in cwd_path.parents
    except (OSError, RuntimeError, ValueError):
        return cwd.casefold().rstrip("/\\") == project_path.casefold().rstrip("/\\")
