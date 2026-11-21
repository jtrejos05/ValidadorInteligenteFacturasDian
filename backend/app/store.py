"""SQLite persistence for reports and the human review queue."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from app.models import ValidationReport

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    decision TEXT NOT NULL,
    review_status TEXT,
    body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_review ON reports(review_status);
"""


class ReportStore:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)

    def save(self, report: ValidationReport) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO reports VALUES (?, ?, ?, ?, ?)",
                (
                    report.id,
                    report.created_at.isoformat(),
                    report.decision.value,
                    report.review_status,
                    report.model_dump_json(),
                ),
            )
            self._conn.commit()

    def get(self, report_id: str) -> ValidationReport | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT body FROM reports WHERE id = ?", (report_id,)
            ).fetchone()
        return ValidationReport.model_validate_json(row[0]) if row else None

    def list(self, review_status: str | None = None, limit: int = 100) -> list[ValidationReport]:
        sql = "SELECT body FROM reports"
        args: tuple = ()
        if review_status:
            sql += " WHERE review_status = ?"
            args = (review_status,)
        sql += " ORDER BY created_at DESC LIMIT ?"
        with self._lock:
            rows = self._conn.execute(sql, (*args, limit)).fetchall()
        return [ValidationReport.model_validate_json(r[0]) for r in rows]

    def all(self) -> list[ValidationReport]:
        return self.list(limit=10_000)
