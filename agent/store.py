"""SQLite journal: resumable steps, cycle status and persistent state (parameterized SQL only)."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from agent.data import Article, Usage

CYCLE_SCOPE = "*"
SIMULATION_PREFIX = "sim-"

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

NEWS_SCHEMA = """
CREATE TABLE IF NOT EXISTS news_articles (
    symbol TEXT NOT NULL,
    article_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT,
    PRIMARY KEY (symbol, article_id)
);
CREATE TABLE IF NOT EXISTS news_scores (
    symbol TEXT NOT NULL,
    article_id INTEGER NOT NULL,
    sentiment REAL NOT NULL,
    relevance REAL NOT NULL,
    PRIMARY KEY (symbol, article_id)
);
CREATE TABLE IF NOT EXISTS llm_calls (
    at TEXT NOT NULL,
    purpose TEXT NOT NULL,
    symbol TEXT NOT NULL,
    calls INTEGER NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS news_days (
    symbol TEXT NOT NULL,
    day TEXT NOT NULL,
    PRIMARY KEY (symbol, day)
);
"""


class StepRow(NamedTuple):
    cycle_id: str
    symbol: str
    result: str
    created_at: datetime


class ArticleScore(NamedTuple):
    sentiment: float
    relevance: float


class CycleRow(NamedTuple):
    cycle_id: str
    started_at: datetime
    finished_at: datetime | None
    status: str | None
    detail: str | None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def is_simulation(cycle_id: str) -> bool:
    """Simulated cycles send no order and are never shown on the dashboard."""
    return cycle_id.startswith(SIMULATION_PREFIX)


class Store:
    def __init__(self, path: Path, news_tables: bool = False) -> None:
        """The news tables are only created for news scripts or when news is enabled."""
        self._db = sqlite3.connect(path)
        self._db.executescript(SCHEMA)
        if news_tables:
            self._db.executescript(NEWS_SCHEMA)

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

    def update_step(self, cycle_id: str, symbol: str, name: str, result: str) -> None:
        """Replace the stored result of a step, keeping its original timestamp."""
        with self._db:
            self._db.execute(
                "UPDATE steps SET result = ? WHERE cycle_id = ? AND symbol = ? AND name = ?",
                (result, cycle_id, symbol, name),
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

    def save_articles(self, symbol: str, articles: list[Article]) -> None:
        with self._db:
            self._db.executemany(
                "INSERT OR IGNORE INTO news_articles VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (symbol, a.id, a.created_at.isoformat(), a.headline, a.summary, a.source, a.url)
                    for a in articles
                ],
            )

    def list_articles(self, symbol: str, after: datetime, until: datetime) -> list[Article]:
        """Articles created in (after, until], oldest first."""
        rows = self._db.execute(
            "SELECT article_id, created_at, headline, summary, source, url FROM news_articles"
            " WHERE symbol = ? AND created_at > ? AND created_at <= ?"
            " ORDER BY created_at, article_id",
            (symbol, after.isoformat(), until.isoformat()),
        ).fetchall()
        return [
            Article(
                id=r[0],
                created_at=datetime.fromisoformat(r[1]),
                headline=r[2],
                summary=r[3],
                source=r[4],
                url=r[5],
            )
            for r in rows
        ]

    def fetched_days(self, symbol: str, start: datetime, end: datetime) -> set[datetime]:
        """Days in [start, end) whose headlines were already fetched."""
        rows = self._db.execute(
            "SELECT day FROM news_days WHERE symbol = ? AND day >= ? AND day < ?",
            (symbol, start.isoformat(), end.isoformat()),
        ).fetchall()
        return {datetime.fromisoformat(r[0]) for r in rows}

    def mark_day_fetched(self, symbol: str, day: datetime) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO news_days VALUES (?, ?)", (symbol, day.isoformat())
            )

    def save_scores(self, symbol: str, scores: dict[int, ArticleScore]) -> None:
        with self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO news_scores VALUES (?, ?, ?, ?)",
                [(symbol, i, s.sentiment, s.relevance) for i, s in scores.items()],
            )

    def get_scores(self, symbol: str) -> dict[int, ArticleScore]:
        rows = self._db.execute(
            "SELECT article_id, sentiment, relevance FROM news_scores WHERE symbol = ?", (symbol,)
        ).fetchall()
        return {r[0]: ArticleScore(r[1], r[2]) for r in rows}

    def log_llm_calls(self, purpose: str, symbol: str, usage: Usage) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO llm_calls VALUES (?, ?, ?, ?, ?, ?)", (_now(), purpose, symbol, *usage)
            )

    def llm_usage(self, purpose: str) -> Usage:
        row = self._db.execute(
            "SELECT COALESCE(SUM(calls), 0), COALESCE(SUM(prompt_tokens), 0),"
            " COALESCE(SUM(completion_tokens), 0) FROM llm_calls WHERE purpose = ?",
            (purpose,),
        ).fetchone()
        return Usage(*row)
