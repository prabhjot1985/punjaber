from datetime import datetime, timedelta, timezone

from app import srs

AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_a_correct_answer_schedules_one_day_out():
    state = srs.review(srs.ReviewState(), srs.QUALITY_GOOD, at=AT)
    assert state.repetitions == 1
    assert state.interval_days == 1
    assert state.due_at == AT + timedelta(days=1)


def test_intervals_grow_with_each_success():
    state = srs.ReviewState()
    intervals = []
    for _ in range(5):
        state = srs.review(state, srs.QUALITY_GOOD, at=AT)
        intervals.append(state.interval_days)
    assert intervals == sorted(intervals)
    assert intervals[-1] > intervals[0]


def test_a_wrong_answer_resets_the_ladder_and_returns_within_the_session():
    state = srs.ReviewState()
    for _ in range(3):
        state = srs.review(state, srs.QUALITY_GOOD, at=AT)
    lapsed = srs.review(state, srs.QUALITY_WRONG, at=AT)

    assert lapsed.repetitions == 0
    assert lapsed.interval_days < 1
    assert srs.is_due(lapsed, at=AT)


def test_ease_never_falls_below_the_floor():
    state = srs.ReviewState()
    for _ in range(20):
        state = srs.review(state, srs.QUALITY_WRONG, at=AT)
    assert state.ease >= srs.MIN_EASE


def test_easy_answers_raise_ease_and_hard_ones_lower_it():
    easy = srs.review(srs.ReviewState(), srs.QUALITY_EASY, at=AT)
    hard = srs.review(srs.ReviewState(), srs.QUALITY_HARD, at=AT)
    assert easy.ease > srs.DEFAULT_EASE
    assert hard.ease < srs.DEFAULT_EASE


def test_intervals_are_capped():
    state = srs.ReviewState()
    for _ in range(40):
        state = srs.review(state, srs.QUALITY_EASY, at=AT)
    assert state.interval_days <= srs.MAX_INTERVAL_DAYS


def test_grade_uses_speed_as_a_proxy_for_confidence():
    assert srs.grade(False, 100) == srs.QUALITY_WRONG
    assert srs.grade(True, 500) == srs.QUALITY_EASY
    assert srs.grade(True, 5000) == srs.QUALITY_GOOD
    assert srs.grade(True, 20000) == srs.QUALITY_HARD
    assert srs.grade(True, None) == srs.QUALITY_GOOD


def test_an_unseen_item_is_due_immediately():
    assert srs.is_due(srs.ReviewState(), at=AT)
    scheduled = srs.review(srs.ReviewState(), srs.QUALITY_GOOD, at=AT)
    assert not srs.is_due(scheduled, at=AT)
    assert srs.is_due(scheduled, at=AT + timedelta(days=2))
