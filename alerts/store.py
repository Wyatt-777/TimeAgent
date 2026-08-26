"""SQLite persistence for the Alert Inbox."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

from core.event import Priority
from core.migrations import DEFAULT_MIGRATIONS, MigrationRunner

from .model import Alert, AlertStatus


class AlertStore:
    """Persist alerts and support bounded Inbox queries."""

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

    def insert(self, alert: Alert) -> None:
        if not isinstance(alert, Alert):
            raise TypeError("AlertStore accepts Alert instances only")
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO alerts
                    (id, event_id, created_at, priority, title, summary, status, dedup_key, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.id,
                    alert.event_id,
                    alert.created_at.isoformat(),
                    int(alert.priority),
                    alert.title,
                    alert.summary,
                    alert.status.value,
                    alert.dedup_key,
                    json.dumps(alert.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )

    def get(self, alert_id: str) -> Alert | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM alerts WHERE id = ?", (alert_id,)
            ).fetchone()
        return self._row_to_alert(row) if row is not None else None

    def list(
        self,
        *,
        status: AlertStatus | None = None,
        min_priority: Priority | int | None = None,
        limit: int = 100,
    ) -> list[Alert]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        clauses: list[str] = []
        parameters: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            parameters.append(AlertStatus(status).value)
        if min_priority is not None:
            clauses.append("priority >= ?")
            parameters.append(int(Priority(min_priority)))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM alerts {where} ORDER BY created_at DESC LIMIT ?", parameters
            ).fetchall()
        return [self._row_to_alert(row) for row in rows]

    def update_status(self, alert_id: str, status: AlertStatus) -> Alert:
        status = AlertStatus(status)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "UPDATE alerts SET status = ? WHERE id = ?",
                (status.value, alert_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Unknown alert: {alert_id}")
        alert = self.get(alert_id)
        assert alert is not None
        return alert

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "AlertStore":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()

    @staticmethod
    def _row_to_alert(row: sqlite3.Row) -> Alert:
        return Alert(
            id=row["id"],
            event_id=row["event_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            priority=Priority(row["priority"]),
            title=row["title"],
            summary=row["summary"],
            status=AlertStatus(row["status"]),
            dedup_key=row["dedup_key"],
            metadata=json.loads(row["metadata"]),
        )
