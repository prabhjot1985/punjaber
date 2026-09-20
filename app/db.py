"""SQLite persistence for learner progress.

One row per (user, lesson) for course progress and one per (user, item) for the
spaced-repetition schedule. A connection is opened per call rather than shared,
which keeps things safe under FastAPI's thread pool without a lock.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from . import srs

DB_PATH = Path(os.environ.get("PUNJABER_DB", "/data/punjaber.db"))

# Reported by /api/health so a deployment can be identified at a glance.
name = "sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS lesson_progress (
    user_id      TEXT NOT NULL,
    lesson_id    TEXT NOT NULL,
    best_score   REAL NOT NULL DEFAULT 0,
    attempts     INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    PRIMARY KEY (user_id, lesson_id)
);

CREATE TABLE IF NOT EXISTS item_srs (
    user_id       TEXT NOT NULL,
    item_id       TEXT NOT NULL,
    ease          REAL NOT NULL DEFAULT 2.5,
    interval_days REAL NOT NULL DEFAULT 0,
    repetitions   INTEGER NOT NULL DEFAULT 0,
    due_at        TEXT,
    last_seen     TEXT,
    n_correct     INTEGER NOT NULL DEFAULT 0,
    n_wrong       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_item_srs_due ON item_srs (user_id, due_at);

CREATE TABLE IF NOT EXISTS activity (
    user_id  TEXT NOT NULL,
    day      TEXT NOT NULL,
    answers  INTEGER NOT NULL DEFAULT 0,
    correct  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);

CREATE TABLE IF NOT EXISTS settings (
    user_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
"""

DEFAULT_SETTINGS: dict[str, Any] = {
    "script": "both",      # both | gurmukhi | roman
    "gender": "male",      # affects which gendered example is highlighted
    "audio": True,
    "voice_source": "auto",   # auto | offline | browser
    "daily_goal": 20,
}


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# --- lesson progress -------------------------------------------------------


def lesson_progress(user_id: str) -> dict[str, dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM lesson_progress WHERE user_id = ?", (user_id,)
        ).fetchall()
    return {
        row["lesson_id"]: {
            "best_score": row["best_score"],
            "attempts": row["attempts"],
            "completed_at": row["completed_at"],
        }
        for row in rows
    }


def record_lesson_result(user_id: str, lesson_id: str, score: float, passed: bool) -> dict[str, Any]:
    completed = _iso(srs.now()) if passed else None
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO lesson_progress (user_id, lesson_id, best_score, attempts, completed_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT (user_id, lesson_id) DO UPDATE SET
                best_score   = MAX(best_score, excluded.best_score),
                attempts     = attempts + 1,
                completed_at = COALESCE(lesson_progress.completed_at, excluded.completed_at)
            """,
            (user_id, lesson_id, score, completed),
        )
        row = conn.execute(
            "SELECT * FROM lesson_progress WHERE user_id = ? AND lesson_id = ?",
            (user_id, lesson_id),
        ).fetchone()
    return dict(row)


# --- spaced repetition -----------------------------------------------------


def _state_from_row(row: sqlite3.Row | None) -> srs.ReviewState:
    if row is None:
        return srs.ReviewState()
    return srs.ReviewState(
        ease=row["ease"],
        interval_days=row["interval_days"],
        repetitions=row["repetitions"],
        due_at=_parse(row["due_at"]),
    )


def item_state(user_id: str, item_id: str) -> srs.ReviewState:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM item_srs WHERE user_id = ? AND item_id = ?", (user_id, item_id)
        ).fetchone()
    return _state_from_row(row)


def record_answer(
    user_id: str, item_id: str, correct: bool, elapsed_ms: int | None = None
) -> dict[str, Any]:
    """Grade one answer, advance the item's schedule, and log the day's activity."""
    quality = srs.grade(correct, elapsed_ms)
    seen_at = srs.now()

    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM item_srs WHERE user_id = ? AND item_id = ?", (user_id, item_id)
        ).fetchone()
        new_state = srs.review(_state_from_row(row), quality, at=seen_at)

        conn.execute(
            """
            INSERT INTO item_srs (user_id, item_id, ease, interval_days, repetitions,
                                  due_at, last_seen, n_correct, n_wrong)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, item_id) DO UPDATE SET
                ease          = excluded.ease,
                interval_days = excluded.interval_days,
                repetitions   = excluded.repetitions,
                due_at        = excluded.due_at,
                last_seen     = excluded.last_seen,
                n_correct     = item_srs.n_correct + excluded.n_correct,
                n_wrong       = item_srs.n_wrong + excluded.n_wrong
            """,
            (
                user_id,
                item_id,
                new_state.ease,
                new_state.interval_days,
                new_state.repetitions,
                _iso(new_state.due_at),
                _iso(seen_at),
                1 if correct else 0,
                0 if correct else 1,
            ),
        )
        conn.execute(
            """
            INSERT INTO activity (user_id, day, answers, correct) VALUES (?, ?, 1, ?)
            ON CONFLICT (user_id, day) DO UPDATE SET
                answers = answers + 1,
                correct = correct + excluded.correct
            """,
            (user_id, seen_at.date().isoformat(), 1 if correct else 0),
        )

    return {
        "item_id": item_id,
        "quality": quality,
        "ease": new_state.ease,
        "interval_days": new_state.interval_days,
        "due_at": _iso(new_state.due_at),
    }


def due_item_ids(user_id: str, limit: int = 20, at: datetime | None = None) -> list[str]:
    """Items whose review is due, soonest-overdue first."""
    at = at or srs.now()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT item_id FROM item_srs
            WHERE user_id = ? AND due_at IS NOT NULL AND due_at <= ?
            ORDER BY due_at ASC
            LIMIT ?
            """,
            (user_id, _iso(at), limit),
        ).fetchall()
    return [row["item_id"] for row in rows]


def weak_item_ids(user_id: str, limit: int = 20) -> list[str]:
    """Items answered wrong most often — used to top up a short review session."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT item_id FROM item_srs
            WHERE user_id = ? AND n_wrong > 0
            ORDER BY n_wrong DESC, ease ASC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [row["item_id"] for row in rows]


def item_stats(user_id: str) -> dict[str, dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM item_srs WHERE user_id = ?", (user_id,)).fetchall()
    return {
        row["item_id"]: {
            "ease": row["ease"],
            "interval_days": row["interval_days"],
            "repetitions": row["repetitions"],
            "due_at": row["due_at"],
            "n_correct": row["n_correct"],
            "n_wrong": row["n_wrong"],
        }
        for row in rows
    }


# --- activity and streaks --------------------------------------------------


def activity(user_id: str, days: int = 30) -> list[dict[str, Any]]:
    since = (srs.now().date() - timedelta(days=days - 1)).isoformat()
    with connect() as conn:
        rows = conn.execute(
            "SELECT day, answers, correct FROM activity WHERE user_id = ? AND day >= ? ORDER BY day",
            (user_id, since),
        ).fetchall()
    return [dict(row) for row in rows]


def streak(user_id: str) -> int:
    """Consecutive days with at least one answer, counting back from today."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT day FROM activity WHERE user_id = ? AND answers > 0 ORDER BY day DESC",
            (user_id,),
        ).fetchall()
    active = {date.fromisoformat(row["day"]) for row in rows}
    if not active:
        return 0

    today = srs.now().date()
    # A streak stays alive until the end of tomorrow, so start from today if
    # they have practised, otherwise from yesterday.
    cursor = today if today in active else today - timedelta(days=1)
    count = 0
    while cursor in active:
        count += 1
        cursor -= timedelta(days=1)
    return count


# --- settings and reset ----------------------------------------------------


def settings(user_id: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            "SELECT payload FROM settings WHERE user_id = ?", (user_id,)
        ).fetchone()
    stored = json.loads(row["payload"]) if row else {}
    return {**DEFAULT_SETTINGS, **stored}


def save_settings(user_id: str, values: dict[str, Any]) -> dict[str, Any]:
    merged = {**settings(user_id), **{k: v for k, v in values.items() if v is not None}}
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO settings (user_id, payload) VALUES (?, ?)
            ON CONFLICT (user_id) DO UPDATE SET payload = excluded.payload
            """,
            (user_id, json.dumps(merged)),
        )
    return merged


def reset(user_id: str, tables: Iterable[str] = ("lesson_progress", "item_srs", "activity")) -> None:
    with connect() as conn:
        for table in tables:
            conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
