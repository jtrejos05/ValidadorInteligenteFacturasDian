"""Persistence for reports and the human review queue.

- SQLite for local development and tests (zero setup).
- Postgres when DATABASE_URL / POSTGRES_URL is set (Vercel + Neon in production),
  because serverless functions have no persistent disk.

Reports are stored as one JSON document per row, plus the two columns the app
filters on (decision, review_status).
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Protocol

from app.models import ValidationReport


class ReportStore(Protocol):
    def save(self, report: ValidationReport) -> None: ...
    def get(self, report_id: str) -> ValidationReport | None: ...
    def list(
        self, review_status: str | None = None, limit: int = 100
    ) -> list[ValidationReport]: ...
    def all(self) -> list[ValidationReport]: ...


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    decision TEXT NOT NULL,
    review_status TEXT,
    body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_review ON reports(review_status);
"""


class SQLiteReportStore:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SQLITE_SCHEMA)

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


_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    decision TEXT NOT NULL,
    review_status TEXT,
    body JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_review ON reports(review_status);
CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at DESC);
"""


class PostgresReportStore:
    """One short-lived connection per operation: serverless instances come and go,
    so we rely on the provider's pooled endpoint instead of an in-process pool."""

    def __init__(self, url: str):
        import psycopg

        self._psycopg = psycopg
        self.url = url
        with self._connect() as conn:
            conn.execute(_PG_SCHEMA)

    def _connect(self):
        # prepare_threshold=None: required behind transaction-mode poolers (PgBouncer).
        return self._psycopg.connect(self.url, autocommit=True, prepare_threshold=None)

    def save(self, report: ValidationReport) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reports (id, created_at, decision, review_status, body)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    decision = EXCLUDED.decision,
                    review_status = EXCLUDED.review_status,
                    body = EXCLUDED.body
                """,
                (
                    report.id,
                    report.created_at,
                    report.decision.value,
                    report.review_status,
                    report.model_dump_json(),
                ),
            )

    def get(self, report_id: str) -> ValidationReport | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT body::text FROM reports WHERE id = %s", (report_id,)
            ).fetchone()
        return ValidationReport.model_validate_json(row[0]) if row else None

    def list(self, review_status: str | None = None, limit: int = 100) -> list[ValidationReport]:
        sql = "SELECT body::text FROM reports"
        args: tuple = ()
        if review_status:
            sql += " WHERE review_status = %s"
            args = (review_status,)
        sql += " ORDER BY created_at DESC LIMIT %s"
        with self._connect() as conn:
            rows = conn.execute(sql, (*args, limit)).fetchall()
        return [ValidationReport.model_validate_json(r[0]) for r in rows]

    def all(self) -> list[ValidationReport]:
        return self.list(limit=10_000)


def make_store(database_url: str | None, sqlite_path: Path) -> ReportStore:
    if database_url:
        return PostgresReportStore(database_url)
    return SQLiteReportStore(sqlite_path)
