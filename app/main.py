"""Punjaber API and static host.

The app is deliberately single-process and file-backed: it is a personal
language tutor, not a multi-tenant service. A "user" is just a string key so
that several people can share one container without sharing progress.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import audio, curriculum, db, exercises, recordings

WEB_DIR = Path(os.environ.get("PUNJABER_WEB", "/app/web"))
DEFAULT_USER = "local"

@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    yield


app = FastAPI(
    title="Punjaber",
    description="A progressive conversational Punjabi course for English speakers.",
    version="1.0.0",
    lifespan=lifespan,
)


def current_user(x_punjaber_user: str | None = Header(default=None)) -> str:
    """Identify the learner. Any non-empty header value works as a profile name."""
    user = (x_punjaber_user or "").strip()
    return user[:64] if user else DEFAULT_USER


# --- request models --------------------------------------------------------


class AttemptIn(BaseModel):
    item_id: str
    kind: str = "pa_to_en"
    correct: bool | None = None
    given: str | None = None
    elapsed_ms: int | None = Field(default=None, ge=0)


class LessonResultIn(BaseModel):
    correct: int = Field(ge=0)
    total: int = Field(gt=0)


class SettingsIn(BaseModel):
    script: str | None = None
    gender: str | None = None
    audio: bool | None = None
    voice_source: Literal["auto", "offline", "browser"] | None = None
    daily_goal: int | None = Field(default=None, ge=5, le=200)


# --- course structure ------------------------------------------------------


def _lesson_status(lesson_id: str, progress: dict[str, dict[str, Any]]) -> str:
    record = progress.get(lesson_id)
    if record and record["completed_at"]:
        return "passed"
    previous = curriculum.previous_lesson(lesson_id)
    if previous is None:
        return "started" if record else "available"
    previous_record = progress.get(previous)
    if previous_record and previous_record["completed_at"]:
        return "started" if record else "available"
    return "locked"


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "curriculum": curriculum.stats(),
        "audio": {"offline": audio.available(), "cache": audio.cache_stats()},
        "recordings": recordings.stats(),
    }


# --- pronunciation audio ---------------------------------------------------


@app.get("/api/speech")
def speech(text: str, speed: str = audio.DEFAULT_SPEED, synth: bool = False) -> FileResponse:
    """Serve audio for the given Gurmukhi text.

    A native-speaker recording wins whenever one exists; otherwise the text is
    synthesised by espeak-ng and cached. Because every part of the app already
    plays from this one URL, recording a word is all it takes for the whole
    course to start using the real voice. Pass synth=true to hear the
    synthesiser regardless, which the studio uses for side-by-side comparison.
    """
    if not audio.is_gurmukhi(text):
        raise HTTPException(status_code=400, detail="Text must contain Gurmukhi")

    if not synth:
        recorded = recordings.path_for(text)
        if recorded is not None:
            return FileResponse(
                recorded,
                media_type=(recordings.meta(text) or {}).get("mime", "audio/webm"),
                # A re-recording changes the file in place under the same URL,
                # so this must stay revalidated rather than cached forever.
                headers={"Cache-Control": "no-cache"},
            )

    if not audio.available():
        raise HTTPException(status_code=503, detail="Offline audio is not installed")

    try:
        path = audio.render(text, speed)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except audio.AudioUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return FileResponse(
        path,
        media_type="audio/wav",
        # Synthesis is deterministic, so it can be cached hard.
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


# --- the recording studio --------------------------------------------------


@app.get("/api/studio/texts")
def studio_texts() -> dict[str, Any]:
    """Everything the course speaks, with its recording status.

    This is the studio's worklist: one row per distinct phrase, in course
    order, so recording top to bottom follows the lessons.
    """
    recorded = set(recordings.recorded_texts())
    rows = [
        {**row, "recorded": row["text"] in recorded, "key": recordings.key_for(row["text"])}
        for row in curriculum.spoken_texts()
    ]
    return {
        "texts": rows,
        "total": len(rows),
        "recorded": sum(1 for row in rows if row["recorded"]),
    }


@app.get("/api/recordings")
def list_recordings() -> dict[str, Any]:
    """The client's manifest: which texts have a real voice behind them."""
    texts = recordings.recorded_texts()
    return {"texts": texts, "count": len(texts), "stats": recordings.stats()}


@app.post("/api/recordings")
async def upload_recording(
    text: str = Form(...), clip: UploadFile = File(...)
) -> dict[str, Any]:
    # Only course text may be stored — this endpoint is not general file upload.
    if not curriculum.is_spoken(text):
        raise HTTPException(status_code=400, detail="That phrase is not part of the course")

    data = await clip.read()
    try:
        record = recordings.save(text, data, clip.content_type or "")
    except recordings.RecordingError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {"saved": True, **record}


@app.delete("/api/recordings")
def delete_recording(text: str) -> dict[str, Any]:
    return {"deleted": recordings.delete(text), "text": text}


@app.get("/api/course")
def course(user: str = Depends(current_user)) -> dict[str, Any]:
    progress = db.lesson_progress(user)

    units = []
    passed_total = 0
    for unit in curriculum.units():
        lessons = []
        for lesson in unit["lessons"]:
            status = _lesson_status(lesson["id"], progress)
            record = progress.get(lesson["id"], {})
            if status == "passed":
                passed_total += 1
            lessons.append(
                {
                    "id": lesson["id"],
                    "title": lesson["title"],
                    "goal": lesson["goal"],
                    "item_count": len(lesson["items"]),
                    "has_dialogue": bool(lesson.get("dialogue")),
                    "status": status,
                    "best_score": record.get("best_score", 0),
                    "attempts": record.get("attempts", 0),
                }
            )
        units.append(
            {
                "id": unit["id"],
                "order": unit["order"],
                "optional": bool(unit.get("optional")),
                "title": unit["title"],
                "description": unit["description"],
                "lessons": lessons,
                "passed": sum(1 for l in lessons if l["status"] == "passed"),
                "total": len(lessons),
            }
        )

    total_lessons = len(curriculum.LESSON_SEQUENCE)
    next_lesson = next(
        (
            lesson_id
            for lesson_id in curriculum.LESSON_SEQUENCE
            if _lesson_status(lesson_id, progress) in ("available", "started")
        ),
        None,
    )

    return {
        "units": units,
        "summary": {
            "lessons_passed": passed_total,
            "lessons_total": total_lessons,
            "percent": round(100 * passed_total / total_lessons) if total_lessons else 0,
            "streak": db.streak(user),
            "due_count": len(db.due_item_ids(user, limit=999)),
            "next_lesson": next_lesson,
        },
    }


@app.get("/api/lessons/{lesson_id}")
def get_lesson(lesson_id: str, user: str = Depends(current_user)) -> dict[str, Any]:
    lesson = curriculum.lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="No such lesson")

    progress = db.lesson_progress(user)
    status = _lesson_status(lesson_id, progress)
    index = curriculum.LESSON_SEQUENCE.index(lesson_id)
    following = curriculum.LESSON_SEQUENCE[index + 1 :]

    return {
        "id": lesson["id"],
        "title": lesson["title"],
        "goal": lesson["goal"],
        "notes": lesson.get("notes", []),
        "items": lesson["items"],
        "dialogue": lesson.get("dialogue", []),
        "unit_id": curriculum.unit_of(lesson_id),
        "status": status,
        "locked": status == "locked",
        "next_lesson": following[0] if following else None,
        "position": {"index": index + 1, "total": len(curriculum.LESSON_SEQUENCE)},
    }


@app.get("/api/lessons/{lesson_id}/practice")
def get_practice(
    lesson_id: str, seed: int | None = None, user: str = Depends(current_user)
) -> dict[str, Any]:
    if curriculum.lesson(lesson_id) is None:
        raise HTTPException(status_code=404, detail="No such lesson")
    if _lesson_status(lesson_id, db.lesson_progress(user)) == "locked":
        raise HTTPException(status_code=403, detail="Finish the previous lesson first")

    built = exercises.build_practice(lesson_id, seed=seed)
    return {"lesson_id": lesson_id, "exercises": built, "count": len(built)}


@app.post("/api/lessons/{lesson_id}/complete")
def complete_lesson(
    lesson_id: str, result: LessonResultIn, user: str = Depends(current_user)
) -> dict[str, Any]:
    if curriculum.lesson(lesson_id) is None:
        raise HTTPException(status_code=404, detail="No such lesson")

    score = result.correct / result.total
    passed = score >= curriculum.PASS_THRESHOLD
    record = db.record_lesson_result(user, lesson_id, score, passed)

    index = curriculum.LESSON_SEQUENCE.index(lesson_id)
    following = curriculum.LESSON_SEQUENCE[index + 1 :]

    return {
        "lesson_id": lesson_id,
        "score": round(score, 4),
        "passed": passed,
        "threshold": curriculum.PASS_THRESHOLD,
        "best_score": record["best_score"],
        "attempts": record["attempts"],
        "unlocked_next": following[0] if (passed and following) else None,
        "streak": db.streak(user),
    }


# --- answering -------------------------------------------------------------


@app.post("/api/attempts")
def record_attempt(attempt: AttemptIn, user: str = Depends(current_user)) -> dict[str, Any]:
    item = curriculum.item(attempt.item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="No such item")

    if attempt.given is not None:
        correct = exercises.answer_matches(attempt.given, item["roman"])
    elif attempt.correct is not None:
        correct = attempt.correct
    else:
        raise HTTPException(status_code=422, detail="Send either 'correct' or 'given'")

    schedule = db.record_answer(user, attempt.item_id, correct, attempt.elapsed_ms)
    return {
        "correct": correct,
        "expected": {"pa": item["pa"], "roman": item["roman"], "en": item["en"]},
        "schedule": schedule,
    }


# --- review ----------------------------------------------------------------


@app.get("/api/review")
def get_review(
    limit: int = 15, seed: int | None = None, user: str = Depends(current_user)
) -> dict[str, Any]:
    limit = max(1, min(limit, 50))
    item_ids = db.due_item_ids(user, limit=limit)

    # If nothing is strictly due, drill the items they get wrong most.
    topped_up = False
    if len(item_ids) < limit:
        extra = [i for i in db.weak_item_ids(user, limit=limit) if i not in item_ids]
        if extra:
            topped_up = True
        item_ids.extend(extra[: limit - len(item_ids)])

    built = exercises.build_review(item_ids, seed=seed)
    return {
        "exercises": built,
        "count": len(built),
        "due_count": len(db.due_item_ids(user, limit=999)),
        "topped_up": topped_up,
    }


# --- progress, settings, reset ---------------------------------------------


@app.get("/api/stats")
def stats(user: str = Depends(current_user)) -> dict[str, Any]:
    item_states = db.item_stats(user)
    progress = db.lesson_progress(user)

    known = sum(1 for s in item_states.values() if s["repetitions"] >= 2)
    seen = len(item_states)
    answers = sum(s["n_correct"] + s["n_wrong"] for s in item_states.values())
    correct = sum(s["n_correct"] for s in item_states.values())

    trouble = sorted(
        (
            {
                "item_id": item_id,
                "n_wrong": state["n_wrong"],
                **{k: v for k, v in (curriculum.item(item_id) or {}).items() if k in ("pa", "roman", "en")},
            }
            for item_id, state in item_states.items()
            if state["n_wrong"] > 0
        ),
        key=lambda row: -row["n_wrong"],
    )[:10]

    return {
        "words_seen": seen,
        "words_known": known,
        "words_total": curriculum.stats()["items"],
        "answers": answers,
        "accuracy": round(correct / answers, 4) if answers else 0,
        "lessons_passed": sum(1 for p in progress.values() if p["completed_at"]),
        "lessons_total": len(curriculum.LESSON_SEQUENCE),
        "streak": db.streak(user),
        "due_count": len(db.due_item_ids(user, limit=999)),
        "activity": db.activity(user, days=30),
        "trouble_words": trouble,
    }


@app.get("/api/settings")
def get_settings(user: str = Depends(current_user)) -> dict[str, Any]:
    return db.settings(user)


@app.put("/api/settings")
def put_settings(values: SettingsIn, user: str = Depends(current_user)) -> dict[str, Any]:
    return db.save_settings(user, values.model_dump())


@app.post("/api/reset")
def reset(user: str = Depends(current_user)) -> dict[str, Any]:
    db.reset(user)
    return {"status": "reset", "user": user}


# --- static site -----------------------------------------------------------


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
