"""Operational state in SQLite: idempotency log, source cursors, and the
dead-letter queue. Cognee remains the system of record for KNOWLEDGE; this is
only for pipeline bookkeeping that guarantees correctness.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class StateStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        # check_same_thread=False so the FastAPI app and worker can share it.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._tx() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS processed_events (
                    event_id TEXT PRIMARY KEY,
                    processed_at REAL NOT NULL
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS cursors (
                    source TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS dead_letters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job TEXT NOT NULL,
                    error TEXT NOT NULL,
                    failed_at REAL NOT NULL
                )"""
            )

    @contextmanager
    def _tx(self):
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    # -- idempotency ---------------------------------------------------------
    def is_processed(self, event_id: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM processed_events WHERE event_id = ?", (event_id,)
        )
        return cur.fetchone() is not None

    def mark_processed(self, event_id: str) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO processed_events(event_id, processed_at) VALUES(?, ?)",
                (event_id, time.time()),
            )

    # -- cursors -------------------------------------------------------------
    def get_cursor(self, source: str) -> str | None:
        cur = self._conn.execute("SELECT value FROM cursors WHERE source = ?", (source,))
        row = cur.fetchone()
        return row["value"] if row else None

    def set_cursor(self, source: str, value: str) -> None:
        with self._tx() as cur:
            cur.execute(
                """INSERT INTO cursors(source, value, updated_at) VALUES(?, ?, ?)
                   ON CONFLICT(source) DO UPDATE SET value=excluded.value,
                   updated_at=excluded.updated_at""",
                (source, value, time.time()),
            )

    # -- dead-letter queue ---------------------------------------------------
    def add_dead_letter(self, job: dict, error: str) -> int:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO dead_letters(job, error, failed_at) VALUES(?, ?, ?)",
                (json.dumps(job), error, time.time()),
            )
            return int(cur.lastrowid)

    def list_dead_letters(self) -> list[dict]:
        cur = self._conn.execute("SELECT * FROM dead_letters ORDER BY id")
        return [
            {"id": r["id"], "job": json.loads(r["job"]), "error": r["error"], "failed_at": r["failed_at"]}
            for r in cur.fetchall()
        ]

    def remove_dead_letter(self, dl_id: int) -> None:
        with self._tx() as cur:
            cur.execute("DELETE FROM dead_letters WHERE id = ?", (dl_id,))

    def close(self) -> None:
        self._conn.close()
