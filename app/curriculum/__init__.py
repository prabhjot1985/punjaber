"""Loads the course from the JSON files in ./data and indexes it for fast lookup.

The curriculum is static content, so it is read once at import time and then
served from memory. Validation happens here rather than at request time so a
malformed data file fails loudly on startup instead of quietly at runtime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent / "data"

# A lesson is unlocked once the previous one has been passed at this score.
PASS_THRESHOLD = 0.8


class CurriculumError(RuntimeError):
    """Raised when the course data on disk is malformed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CurriculumError(message)


def _load_units() -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for path in sorted(DATA_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            unit = json.load(handle)
        _validate_unit(unit, path.name)
        units.append(unit)
    _require(bool(units), f"no curriculum files found in {DATA_DIR}")
    units.sort(key=lambda u: u["order"])
    return units


def _validate_unit(unit: dict[str, Any], filename: str) -> None:
    for key in ("id", "order", "title", "description", "lessons"):
        _require(key in unit, f"{filename}: unit is missing '{key}'")
    _require(bool(unit["lessons"]), f"{filename}: unit has no lessons")
    for lesson in unit["lessons"]:
        for key in ("id", "title", "goal", "items"):
            _require(key in lesson, f"{filename}: lesson is missing '{key}'")
        _require(
            len(lesson["items"]) >= 4,
            f"{filename}: lesson {lesson['id']} needs at least 4 items to build exercises",
        )
        for item in lesson["items"]:
            for key in ("id", "pa", "roman", "en"):
                _require(key in item, f"{filename}: item in {lesson['id']} is missing '{key}'")


_UNITS = _load_units()

# Flat indexes. Order matters: LESSON_SEQUENCE defines the path through the course.
LESSON_SEQUENCE: list[str] = []

# The prerequisite chain runs through the required units only. An optional unit
# (the pronunciation primer) is offered first but never blocks the main course,
# so a learner can start at "hello" and come back to phonetics later.
REQUIRED_SEQUENCE: list[str] = []

_LESSONS: dict[str, dict[str, Any]] = {}
_ITEMS: dict[str, dict[str, Any]] = {}
_LESSON_UNIT: dict[str, str] = {}
_ITEM_LESSON: dict[str, str] = {}
_OPTIONAL_UNITS: set[str] = set()
_UNIT_LESSONS: dict[str, list[str]] = {}

for _unit in _UNITS:
    _UNIT_LESSONS[_unit["id"]] = []
    if _unit.get("optional"):
        _OPTIONAL_UNITS.add(_unit["id"])
    for _lesson in _unit["lessons"]:
        _require(_lesson["id"] not in _LESSONS, f"duplicate lesson id {_lesson['id']}")
        LESSON_SEQUENCE.append(_lesson["id"])
        _UNIT_LESSONS[_unit["id"]].append(_lesson["id"])
        if not _unit.get("optional"):
            REQUIRED_SEQUENCE.append(_lesson["id"])
        _LESSONS[_lesson["id"]] = _lesson
        _LESSON_UNIT[_lesson["id"]] = _unit["id"]
        for _item in _lesson["items"]:
            _require(_item["id"] not in _ITEMS, f"duplicate item id {_item['id']}")
            _ITEMS[_item["id"]] = _item
            _ITEM_LESSON[_item["id"]] = _lesson["id"]

# Minimal pairs must point at a real item, and point back at each other.
for _item in _ITEMS.values():
    _partner_id = _item.get("pair")
    if _partner_id:
        _require(_partner_id in _ITEMS, f"{_item['id']}: pair {_partner_id} does not exist")
        _require(
            _ITEMS[_partner_id].get("pair") == _item["id"],
            f"{_item['id']}: pair {_partner_id} does not point back",
        )


def units() -> list[dict[str, Any]]:
    """Every unit, in course order."""
    return _UNITS


def lesson(lesson_id: str) -> dict[str, Any] | None:
    return _LESSONS.get(lesson_id)


def item(item_id: str) -> dict[str, Any] | None:
    return _ITEMS.get(item_id)


def unit_of(lesson_id: str) -> str | None:
    return _LESSON_UNIT.get(lesson_id)


def lesson_of(item_id: str) -> str | None:
    return _ITEM_LESSON.get(item_id)


def is_optional(lesson_id: str) -> bool:
    """True for lessons in a unit that never blocks the main course."""
    return _LESSON_UNIT.get(lesson_id) in _OPTIONAL_UNITS


def previous_lesson(lesson_id: str) -> str | None:
    """The lesson that must be passed before this one unlocks.

    Optional units chain internally but hang off the main course, so their
    first lesson — and the first required lesson — are both open from the start.
    """
    if is_optional(lesson_id):
        within_unit = _UNIT_LESSONS[_LESSON_UNIT[lesson_id]]
        index = within_unit.index(lesson_id)
        return None if index == 0 else within_unit[index - 1]

    index = REQUIRED_SEQUENCE.index(lesson_id)
    return None if index == 0 else REQUIRED_SEQUENCE[index - 1]


def unit_items(unit_id: str) -> list[dict[str, Any]]:
    """All items in a unit — the preferred pool for plausible wrong answers."""
    for unit in _UNITS:
        if unit["id"] == unit_id:
            return [item for lesson in unit["lessons"] for item in lesson["items"]]
    return []


def all_items() -> list[dict[str, Any]]:
    return list(_ITEMS.values())


def _build_spoken_texts() -> dict[str, dict[str, Any]]:
    """Every distinct Punjabi string the app ever speaks, in course order.

    Keyed by the text itself rather than by item id, so a word that appears in
    two lessons (taal turns up in both primer lessons) is recorded once and
    reused everywhere. Dialogue lines are included — they are spoken too.
    """
    seen: dict[str, dict[str, Any]] = {}

    for unit in _UNITS:
        for lesson in unit["lessons"]:
            rows = [
                {
                    "text": item["pa"],
                    "roman": item["roman"],
                    "en": item["en"],
                    "kind": "item",
                    "speaker": "",
                }
                for item in lesson["items"]
            ] + [
                {
                    "text": turn["pa"],
                    "roman": turn["roman"],
                    "en": turn["en"],
                    "kind": "dialogue",
                    "speaker": turn.get("speaker", ""),
                }
                for turn in lesson.get("dialogue", [])
            ]

            for row in rows:
                existing = seen.get(row["text"])
                if existing:
                    existing["uses"] += 1
                    continue
                seen[row["text"]] = {
                    **row,
                    "unit_id": unit["id"],
                    "unit_title": unit["title"],
                    "unit_order": unit["order"],
                    "lesson_id": lesson["id"],
                    "lesson_title": lesson["title"],
                    "uses": 1,
                }

    return seen


# The course is static, so this is built once at import rather than per request.
_SPOKEN = _build_spoken_texts()


def spoken_texts() -> list[dict[str, Any]]:
    """Every distinct spoken phrase in the course, in course order."""
    return list(_SPOKEN.values())


def is_spoken(text: str) -> bool:
    """True if this exact string appears in the course.

    Guards the recording upload: only course text may be stored.
    """
    return text in _SPOKEN


def stats() -> dict[str, int]:
    return {
        "units": len(_UNITS),
        "lessons": len(_LESSONS),
        "items": len(_ITEMS),
        "spoken_texts": len(spoken_texts()),
    }
