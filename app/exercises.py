"""Builds exercise sets from curriculum items.

Exercises are generated rather than authored so every lesson gets the same
variety of drills for free, and so a review session can mix items from anywhere
in the course. Generation is seeded, which makes it reproducible in tests.
"""

from __future__ import annotations

import random
import re
import unicodedata
from typing import Any

from . import curriculum

CHOICE_KEYS = ["a", "b", "c", "d"]
N_CHOICES = 4

# Kinds where the learner types or assembles an answer instead of picking one.
TYPED_KINDS = {"type_roman", "assemble"}

# A minimal pair offers exactly two options, not the usual four.
PAIR_KINDS = {"minimal_pair"}

# Which written contrasts can honestly be drilled by ear.
#
# Measured against the bundled espeak-ng voice: aspiration and retroflexion are
# rendered clearly (the aspiration burst is plainly visible in the waveform),
# but tone is barely realised and the addak is ignored outright. Drilling those
# two by ear would be asking learners to hear a difference that is not in the
# audio, so Unit 0 teaches them in writing instead.
AUDIBLE_CONTRASTS = {"aspiration", "retroflex"}

# Items with a blank in them ("mera naan ... hai") cannot be typed or assembled.
_PLACEHOLDER = "..."

INSTRUCTIONS = {
    "pa_to_en": "What does this mean?",
    "en_to_pa": "How do you say this in Punjabi?",
    "listen": "Listen and choose the meaning",
    "type_roman": "Type it in Punjabi (romanised)",
    "assemble": "Put the words in the right order",
    "minimal_pair": "Which word did you hear?",
}


def normalize_answer(text: str) -> str:
    """Fold a typed answer down to something forgiving enough to compare.

    Learners should not lose a point for capitals, punctuation, doubled spaces
    or the diacritics used in strict transliteration.
    """
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def answer_matches(given: str, expected: str) -> bool:
    return normalize_answer(given) == normalize_answer(expected)


def _words(item: dict[str, Any]) -> list[str]:
    return item["roman"].split()


def _typeable(item: dict[str, Any]) -> bool:
    return _PLACEHOLDER not in item["roman"] and len(_words(item)) <= 3


def _assemblable(item: dict[str, Any]) -> bool:
    return _PLACEHOLDER not in item["roman"] and 3 <= len(_words(item)) <= 8


def _distractors(
    target: dict[str, Any], pool: list[dict[str, Any]], rng: random.Random, count: int
) -> list[dict[str, Any]]:
    """Pick wrong answers, preferring items of the same kind for plausibility."""
    candidates = [i for i in pool if i["id"] != target["id"] and i["en"] != target["en"]]
    same_kind = [i for i in candidates if i.get("kind") == target.get("kind")]

    chosen: list[dict[str, Any]] = []
    for group in (same_kind, candidates):
        rng.shuffle(group)
        for candidate in group:
            if len(chosen) >= count:
                break
            if all(c["id"] != candidate["id"] for c in chosen):
                chosen.append(candidate)
        if len(chosen) >= count:
            break

    if len(chosen) < count:
        # Very small pool: fall back to the whole course.
        everything = [
            i for i in curriculum.all_items()
            if i["id"] != target["id"] and all(c["id"] != i["id"] for c in chosen)
        ]
        rng.shuffle(everything)
        chosen.extend(everything[: count - len(chosen)])

    return chosen[:count]


def _multiple_choice(
    item: dict[str, Any],
    pool: list[dict[str, Any]],
    rng: random.Random,
    kind: str,
    index: int,
) -> dict[str, Any]:
    options = [item] + _distractors(item, pool, rng, N_CHOICES - 1)
    rng.shuffle(options)

    choices = []
    answer_key = CHOICE_KEYS[0]
    for key, option in zip(CHOICE_KEYS, options):
        show_punjabi = kind in ("en_to_pa",)
        choices.append(
            {
                "key": key,
                "text": option["pa"] if show_punjabi else option["en"],
                "sub": option["roman"] if show_punjabi else "",
            }
        )
        if option["id"] == item["id"]:
            answer_key = key

    if kind == "pa_to_en":
        prompt = {"main": item["pa"], "sub": item["roman"]}
    elif kind == "listen":
        prompt = {"main": "", "sub": ""}
    else:
        prompt = {"main": item["en"], "sub": ""}

    return {
        "id": f"{item['id']}:{kind}:{index}",
        "item_id": item["id"],
        "kind": kind,
        "instruction": INSTRUCTIONS[kind],
        "prompt": prompt,
        "choices": choices,
        "answer_key": answer_key,
        "answer_text": item["pa"] if kind == "en_to_pa" else item["en"],
        "speak": item["pa"],
        "reveal": {"pa": item["pa"], "roman": item["roman"], "en": item["en"]},
    }


def _typed(item: dict[str, Any], rng: random.Random, kind: str, index: int) -> dict[str, Any]:
    tiles: list[str] = []
    if kind == "assemble":
        tiles = _words(item)[:]
        # Guarantee the tiles do not start in the correct order.
        for _ in range(8):
            rng.shuffle(tiles)
            if tiles != _words(item):
                break

    return {
        "id": f"{item['id']}:{kind}:{index}",
        "item_id": item["id"],
        "kind": kind,
        "instruction": INSTRUCTIONS[kind],
        "prompt": {"main": item["en"], "sub": ""},
        "choices": [],
        "tiles": tiles,
        "answer_key": None,
        "answer_text": item["roman"],
        "speak": item["pa"],
        "reveal": {"pa": item["pa"], "roman": item["roman"], "en": item["en"]},
    }


def _minimal_pair(item: dict[str, Any], rng: random.Random, index: int) -> dict[str, Any]:
    """Play one word of a near-identical pair and ask which one it was.

    This is the only exercise that drills sound rather than meaning, so the two
    options differ by exactly one feature and the audio is the whole question.
    """
    partner = curriculum.item(item["pair"])
    options = [item, partner]
    rng.shuffle(options)

    choices = []
    answer_key = CHOICE_KEYS[0]
    for key, option in zip(CHOICE_KEYS, options):
        choices.append({"key": key, "text": option["pa"], "sub": option["roman"]})
        if option["id"] == item["id"]:
            answer_key = key

    return {
        "id": f"{item['id']}:minimal_pair:{index}",
        "item_id": item["id"],
        "kind": "minimal_pair",
        "instruction": INSTRUCTIONS["minimal_pair"],
        "prompt": {"main": "", "sub": ""},
        "choices": choices,
        "answer_key": answer_key,
        "answer_text": item["pa"],
        "speak": item["pa"],
        "contrast": item.get("contrast", ""),
        "reveal": {"pa": item["pa"], "roman": item["roman"], "en": item["en"]},
    }


def _build(
    item: dict[str, Any],
    pool: list[dict[str, Any]],
    rng: random.Random,
    kind: str,
    index: int,
) -> dict[str, Any]:
    if kind == "minimal_pair":
        return _minimal_pair(item, rng, index)
    if kind in TYPED_KINDS:
        return _typed(item, rng, kind, index)
    return _multiple_choice(item, pool, rng, kind, index)


def hearable_pair(item: dict[str, Any]) -> bool:
    """True when this item's contrast survives the synthesiser well enough to drill."""
    return bool(item.get("pair")) and item.get("contrast") in AUDIBLE_CONTRASTS


def _kinds_for(item: dict[str, Any], round_number: int) -> str:
    """Choose a drill kind, getting harder as the rounds go on."""
    if round_number == 0:
        # Pronunciation items lead with the ear; vocabulary items with meaning.
        return "minimal_pair" if hearable_pair(item) else "pa_to_en"
    if hearable_pair(item):
        return "pa_to_en"
    if _assemblable(item):
        return "assemble"
    if _typeable(item):
        return "type_roman"
    return "en_to_pa"


def build_practice(lesson_id: str, seed: int | None = None, rounds: int = 2) -> list[dict[str, Any]]:
    """The scored drill set for one lesson: every item, twice, two ways."""
    lesson = curriculum.lesson(lesson_id)
    if lesson is None:
        return []

    rng = random.Random(seed if seed is not None else lesson_id)
    unit_id = curriculum.unit_of(lesson_id) or ""
    pool = curriculum.unit_items(unit_id) or lesson["items"]

    exercises: list[dict[str, Any]] = []
    for round_number in range(rounds):
        items = lesson["items"][:]
        rng.shuffle(items)
        for index, item in enumerate(items):
            kind = _kinds_for(item, round_number)
            exercises.append(_build(item, pool, rng, kind, round_number * 100 + index))
    return exercises


def build_review(item_ids: list[str], seed: int | None = None) -> list[dict[str, Any]]:
    """A mixed drill over arbitrary items — used for spaced-repetition sessions."""
    rng = random.Random(seed if seed is not None else 0)
    pool = curriculum.all_items()

    exercises: list[dict[str, Any]] = []
    for index, item_id in enumerate(item_ids):
        item = curriculum.item(item_id)
        if item is None:
            continue
        options = ["pa_to_en", "en_to_pa", "listen"]
        if _assemblable(item):
            options.append("assemble")
        if _typeable(item):
            options.append("type_roman")
        if hearable_pair(item):
            options.append("minimal_pair")
        exercises.append(_build(item, pool, rng, rng.choice(options), index))
    return exercises
