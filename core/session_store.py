"""SQLite persistence for Coding Agent sessions shared with Observer MCP."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

from .migrations import DEFAULT_MIGRATIONS, MigrationRunner


class SessionStore:
    """Persist active and completed Coding Agent sessions in the runtime database."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._lock, self._connection:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._migrations = MigrationRunner(DEFAULT_MIGRATIONS)
            self._migrations.apply(self._connection)

    @property
    def schema_version(self) -> int:
        with self._lock:
            return self._migrations.current_version(self._connection)

    def upsert_active(self, session: Any) -> None:
        """Insert or refresh a session that is currently being observed."""
        _validate_session(session)
        if session.ended_at is not None:
            raise ValueError("active sessions must not have ended_at")
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO coding_sessions
                    (session_id, agent_name, pid, started_at, project_path, ended_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                ON CONFLICT(session_id) DO UPDATE SET
                    agent_name = excluded.agent_name,
                    pid = excluded.pid,
                    started_at = excluded.started_at,
                    project_path = excluded.project_path,
                    ended_at = NULL
                """,
                (
                    session.session_id,
                    session.agent_name,
                    session.pid,
                    _timestamp(session.started_at),
                    session.project_path,
                ),
            )

    def mark_finished(self, session: Any, *, ended_at: datetime) -> None:
        """Mark a session finished, preserving its original start metadata."""
        _validate_session(session)
        _validate_timestamp(ended_at)
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO coding_sessions
                    (session_id, agent_name, pid, started_at, project_path, ended_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET ended_at = excluded.ended_at
                """,
                (
                    session.session_id,
                    session.agent_name,
                    session.pid,
                    _timestamp(session.started_at),
                    session.project_path,
                    ended_at.isoformat(),
                ),
            )

    def close_all_active(self, *, ended_at: datetime) -> int:
        """Close stale active rows left by a previous runtime process."""
        _validate_timestamp(ended_at)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "UPDATE coding_sessions SET ended_at = ? WHERE ended_at IS NULL",
                (ended_at.isoformat(),),
            )
        return int(cursor.rowcount)

    def list_active(self, *, limit: int = 100) -> list[Any]:
        """Return sessions that are active in the shared runtime database."""
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT session_id, agent_name, pid, started_at, project_path, ended_at
                FROM coding_sessions
                WHERE ended_at IS NULL
                ORDER BY started_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        from sensors.coding_agent_monitor import CodingAgentSession

        return [
            CodingAgentSession(
                session_id=row["session_id"],
                agent_name=row["agent_name"],
                pid=int(row["pid"]),
                started_at=datetime.fromisoformat(row["started_at"]),
                project_path=row["project_path"],
                ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
            )
            for row in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SessionStore":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()


def _validate_session(session: Any) -> None:
    required = ("session_id", "agent_name", "pid", "started_at", "project_path", "ended_at")
    if any(not hasattr(session, name) for name in required):
        raise TypeError("session must be a CodingAgentSession-like object")
    if not isinstance(session.session_id, str) or not session.session_id.strip():
        raise ValueError("session_id must not be empty")
    if not isinstance(session.agent_name, str) or not session.agent_name.strip():
        raise ValueError("agent_name must not be empty")
    if not isinstance(session.pid, int) or isinstance(session.pid, bool) or session.pid <= 0:
        raise ValueError("pid must be a positive integer")
    _validate_timestamp(session.started_at)


def _validate_timestamp(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")


def _timestamp(value: datetime) -> str:
    _validate_timestamp(value)
    return value.isoformat()
