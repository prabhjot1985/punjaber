"""The course data is content, so these tests guard its shape and integrity."""

from app import curriculum


def test_course_has_the_expected_shape():
    stats = curriculum.stats()
    assert stats["units"] == 11        # ten taught units plus the sounds primer
    assert stats["lessons"] == 33
    assert stats["items"] > 200


def test_units_are_in_order_and_uniquely_numbered():
    orders = [unit["order"] for unit in curriculum.units()]
    assert orders == sorted(orders)
    assert len(set(orders)) == len(orders)


def test_every_item_has_all_three_representations():
    for item in curriculum.all_items():
        assert item["pa"].strip(), item["id"]
        assert item["roman"].strip(), item["id"]
        assert item["en"].strip(), item["id"]


def test_gurmukhi_is_actually_gurmukhi():
    # Gurmukhi occupies U+0A00-U+0A7F. Latin letters in a `pa` field mean a
    # content mistake, except for the digits used in a few borrowed words.
    for item in curriculum.all_items():
        letters = [ch for ch in item["pa"] if ch.isalpha()]
        assert letters, item["id"]
        assert all(0x0A00 <= ord(ch) <= 0x0A7F for ch in letters), item["id"]


def test_romanisation_is_plain_ascii():
    for item in curriculum.all_items():
        assert item["roman"].isascii(), item["id"]


def test_lesson_sequence_covers_every_lesson_exactly_once():
    assert len(curriculum.LESSON_SEQUENCE) == len(set(curriculum.LESSON_SEQUENCE))
    assert len(curriculum.LESSON_SEQUENCE) == curriculum.stats()["lessons"]


def test_exactly_two_lessons_open_the_course():
    """The primer's first lesson and the main course's first lesson.

    The pronunciation primer is offered first but must never gate the course,
    so a learner can go straight to "hello" and come back to phonetics later.
    """
    openers = [l for l in curriculum.LESSON_SEQUENCE if curriculum.previous_lesson(l) is None]
    assert openers == [curriculum.LESSON_SEQUENCE[0], curriculum.REQUIRED_SEQUENCE[0]]


def test_the_primer_chains_within_itself_and_never_gates_the_course():
    optional = [l for l in curriculum.LESSON_SEQUENCE if curriculum.is_optional(l)]
    assert optional, "expected an optional primer unit"

    # No required lesson may depend on an optional one.
    for lesson_id in curriculum.REQUIRED_SEQUENCE:
        previous = curriculum.previous_lesson(lesson_id)
        assert previous is None or not curriculum.is_optional(previous)

    # But the primer's own lessons still unlock in order.
    for earlier, later in zip(optional, optional[1:]):
        assert curriculum.previous_lesson(later) == earlier


def test_every_other_lesson_has_a_prerequisite():
    openers = {curriculum.LESSON_SEQUENCE[0], curriculum.REQUIRED_SEQUENCE[0]}
    for lesson_id in curriculum.LESSON_SEQUENCE:
        if lesson_id not in openers:
            assert curriculum.previous_lesson(lesson_id) is not None


def test_minimal_pairs_are_mutual_and_differ_in_exactly_one_way():
    paired = [i for i in curriculum.all_items() if i.get("pair")]
    assert paired, "expected the primer to define minimal pairs"

    for item in paired:
        partner = curriculum.item(item["pair"])
        assert partner is not None
        assert partner["pair"] == item["id"]
        assert item["contrast"] == partner["contrast"]
        # A pair that shares a romanisation is not a pair.
        assert item["roman"] != partner["roman"]
        assert item["pa"] != partner["pa"]


def test_pronunciation_items_explain_themselves():
    for item in curriculum.all_items():
        if item.get("pair"):
            assert item.get("say", "").strip(), f"{item['id']} needs a 'say' hint"


def test_item_and_lesson_lookups_agree():
    for item in curriculum.all_items():
        lesson_id = curriculum.lesson_of(item["id"])
        lesson = curriculum.lesson(lesson_id)
        assert any(i["id"] == item["id"] for i in lesson["items"])
        assert curriculum.unit_of(lesson_id) is not None


def test_dialogue_turns_are_complete():
    for lesson_id in curriculum.LESSON_SEQUENCE:
        for turn in curriculum.lesson(lesson_id).get("dialogue", []):
            assert set(turn) >= {"speaker", "pa", "roman", "en"}, lesson_id
