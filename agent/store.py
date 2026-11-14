"""SQLite journal: resumable steps, cycle status and persistent state (parameterized SQL only)."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

CYCLE_SCOPE = "*"

SCHEMA = """
CREATE TABLE IF NOT EXISTS steps (
    cycle_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (cycle_id, symbol, name)
);
CREATE TABLE IF NOT EXISTS cycles (
    cycle_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class StepRow(NamedTuple):
    cycle_id: str
    symbol: str
    result: str
    created_at: datetime


class CycleRow(NamedTuple):
    cycle_id: str
    started_at: datetime
    finished_at: datetime | None
    status: str | None
    detail: str | None


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path: Path) -> None:
        self._db = sqlite3.connect(path)
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def get_step(self, cycle_id: str, symbol: str, name: str) -> str | None:
        row = self._db.execute(
            "SELECT result FROM steps WHERE cycle_id = ? AND symbol = ? AND name = ?",
            (cycle_id, symbol, name),
        ).fetchone()
        return None if row is None else str(row[0])

    def save_step(self, cycle_id: str, symbol: str, name: str, result: str) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO steps VALUES (?, ?, ?, ?, ?)",
                (cycle_id, symbol, name, result, _now()),
            )

    def list_steps(self, name: str) -> list[StepRow]:
        rows = self._db.execute(
            "SELECT cycle_id, symbol, result, created_at FROM steps WHERE name = ?"
            " ORDER BY created_at, cycle_id, symbol",
            (name,),
        ).fetchall()
        return [StepRow(r[0], r[1], r[2], datetime.fromisoformat(r[3])) for r in rows]

    def list_cycles(self) -> list[CycleRow]:
        rows = self._db.execute(
            "SELECT cycle_id, started_at, finished_at, status, detail FROM cycles"
            " ORDER BY started_at"
        ).fetchall()
        return [
            CycleRow(
                r[0],
                datetime.fromisoformat(r[1]),
                None if r[2] is None else datetime.fromisoformat(r[2]),
                r[3],
                r[4],
            )
            for r in rows
        ]

    def start_cycle(self, cycle_id: str) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO cycles (cycle_id, started_at) VALUES (?, ?)",
                (cycle_id, _now()),
            )

    def finish_cycle(self, cycle_id: str, status: str, detail: str) -> None:
        with self._db:
            self._db.execute(
                "UPDATE cycles SET finished_at = ?, status = ?, detail = ? WHERE cycle_id = ?",
                (_now(), status, detail, cycle_id),
            )

    def get_state(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def set_state(self, key: str, value: str) -> None:
        with self._db:
            self._db.execute("INSERT OR REPLACE INTO state VALUES (?, ?)", (key, value))

    def get_or_set_state(self, key: str, value: str) -> str:
        with self._db:
            self._db.execute("INSERT OR IGNORE INTO state VALUES (?, ?)", (key, value))
        stored = self.get_state(key)
        assert stored is not None
        return stored

    def delete_state(self, key: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM state WHERE key = ?", (key,))
