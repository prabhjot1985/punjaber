"""Spaced repetition scheduling (a trimmed-down SM-2).

Each vocabulary item carries an ease factor, a repetition count and an interval
in days. A correct answer pushes the next review further out; a wrong answer
resets the item so it comes back in the same session.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

MIN_EASE = 1.3
DEFAULT_EASE = 2.5
MAX_INTERVAL_DAYS = 180.0

# A lapsed item is due again straight away, so it reappears in this session.
RELEARN_INTERVAL_DAYS = 0.0

# Answer quality, in SM-2 terms.
QUALITY_WRONG = 0
QUALITY_HARD = 3
QUALITY_GOOD = 4
QUALITY_EASY = 5

# Above this, a hesitant answer is graded "hard" rather than "good".
SLOW_ANSWER_MS = 8000
FAST_ANSWER_MS = 2500


@dataclass(frozen=True)
class ReviewState:
    ease: float = DEFAULT_EASE
    interval_days: float = 0.0
    repetitions: int = 0
    due_at: datetime | None = None


def now() -> datetime:
    return datetime.now(timezone.utc)


def grade(correct: bool, elapsed_ms: int | None = None) -> int:
    """Turn a raw answer into an SM-2 quality score.

    Speed is a proxy for confidence: an instant correct answer is "easy", a
    laboured one is "hard", and anything in between is "good".
    """
    if not correct:
        return QUALITY_WRONG
    if elapsed_ms is None:
        return QUALITY_GOOD
    if elapsed_ms <= FAST_ANSWER_MS:
        return QUALITY_EASY
    if elapsed_ms >= SLOW_ANSWER_MS:
        return QUALITY_HARD
    return QUALITY_GOOD


def review(state: ReviewState, quality: int, at: datetime | None = None) -> ReviewState:
    """Apply one answer to an item's schedule and return the new schedule."""
    at = at or now()
    quality = max(0, min(5, quality))

    if quality < QUALITY_HARD:
        # Lapse: start the ladder again, but keep (slightly reduced) ease so
        # items you have historically found easy do not become punishing.
        ease = max(MIN_EASE, state.ease - 0.2)
        return ReviewState(
            ease=ease,
            interval_days=RELEARN_INTERVAL_DAYS,
            repetitions=0,
            due_at=at + timedelta(days=RELEARN_INTERVAL_DAYS),
        )

    repetitions = state.repetitions + 1
    if repetitions == 1:
        interval = 1.0
    elif repetitions == 2:
        interval = 3.0
    else:
        interval = min(MAX_INTERVAL_DAYS, state.interval_days * state.ease)

    # Standard SM-2 ease adjustment.
    ease = state.ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    ease = max(MIN_EASE, ease)

    return ReviewState(
        ease=round(ease, 4),
        interval_days=round(interval, 4),
        repetitions=repetitions,
        due_at=at + timedelta(days=interval),
    )


def is_due(state: ReviewState, at: datetime | None = None) -> bool:
    if state.due_at is None:
        return True
    return state.due_at <= (at or now())
