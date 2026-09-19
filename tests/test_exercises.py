from app import curriculum, exercises

LESSON = curriculum.LESSON_SEQUENCE[0]


def test_practice_covers_every_item_in_the_lesson():
    lesson = curriculum.lesson(LESSON)
    built = exercises.build_practice(LESSON, seed=1)
    covered = {ex["item_id"] for ex in built}
    assert covered == {item["id"] for item in lesson["items"]}
    assert len(built) == len(lesson["items"]) * 2


def test_generation_is_deterministic_for_a_given_seed():
    first = exercises.build_practice(LESSON, seed=7)
    second = exercises.build_practice(LESSON, seed=7)
    assert first == second
    assert exercises.build_practice(LESSON, seed=8) != first


def test_multiple_choice_has_four_distinct_options_and_one_right_answer():
    for exercise in exercises.build_practice(LESSON, seed=3):
        if exercise["kind"] in exercises.TYPED_KINDS | exercises.PAIR_KINDS:
            continue
        keys = [choice["key"] for choice in exercise["choices"]]
        texts = [choice["text"] for choice in exercise["choices"]]
        assert len(keys) == exercises.N_CHOICES
        assert len(set(texts)) == exercises.N_CHOICES
        assert exercise["answer_key"] in keys


def test_the_correct_choice_really_is_the_items_meaning():
    for exercise in exercises.build_practice(LESSON, seed=4):
        if exercise["kind"] not in ("pa_to_en", "listen"):
            continue
        item = curriculum.item(exercise["item_id"])
        chosen = [c for c in exercise["choices"] if c["key"] == exercise["answer_key"]][0]
        assert chosen["text"] == item["en"]


def test_assembled_tiles_do_not_start_in_the_right_order():
    found = False
    for lesson_id in curriculum.LESSON_SEQUENCE:
        for exercise in exercises.build_practice(lesson_id, seed=11):
            if exercise["kind"] != "assemble":
                continue
            found = True
            item = curriculum.item(exercise["item_id"])
            assert sorted(exercise["tiles"]) == sorted(item["roman"].split())
            assert exercise["tiles"] != item["roman"].split()
    assert found, "no assemble exercises were generated anywhere in the course"


def test_typed_exercises_expect_the_romanisation():
    for lesson_id in curriculum.LESSON_SEQUENCE:
        for exercise in exercises.build_practice(lesson_id, seed=5):
            if exercise["kind"] in exercises.TYPED_KINDS:
                item = curriculum.item(exercise["item_id"])
                assert exercise["answer_text"] == item["roman"]
                assert "..." not in exercise["answer_text"]


def test_every_lesson_generates_a_full_exercise_set():
    for lesson_id in curriculum.LESSON_SEQUENCE:
        built = exercises.build_practice(lesson_id, seed=2)
        assert built
        for exercise in built:
            assert exercise["instruction"]
            assert exercise["reveal"]["pa"]
            assert exercise["speak"]


def test_answer_matching_is_forgiving_but_not_careless():
    assert exercises.answer_matches("Sat Sri Akal!", "sat sri akal")
    assert exercises.answer_matches("  main   thik  han ", "main thik han")
    assert exercises.answer_matches("srī akāl", "sri akal")
    assert not exercises.answer_matches("main thik", "main thik han")
    assert not exercises.answer_matches("", "sat sri akal")


def test_review_builds_only_for_known_items():
    ids = [curriculum.LESSON_SEQUENCE and curriculum.all_items()[0]["id"], "does-not-exist"]
    built = exercises.build_review(ids, seed=1)
    assert len(built) == 1


def test_unknown_lesson_yields_nothing():
    assert exercises.build_practice("no-such-lesson") == []


# --- pronunciation drills --------------------------------------------------

PRIMER = [l for l in curriculum.LESSON_SEQUENCE if curriculum.is_optional(l)]


def test_only_audible_contrasts_become_listening_drills():
    """Tone and gemination are taught in writing, not drilled by ear.

    The bundled synthesiser barely realises tone and ignores the addak
    entirely, so drilling them would ask learners to hear what is not there.
    """
    for lesson_id in PRIMER:
        for exercise in exercises.build_practice(lesson_id, seed=13):
            if exercise["kind"] != "minimal_pair":
                continue
            item = curriculum.item(exercise["item_id"])
            assert item["contrast"] in exercises.AUDIBLE_CONTRASTS


def test_aspiration_and_retroflex_items_do_get_a_listening_drill():
    built = []
    for lesson_id in PRIMER:
        built += exercises.build_practice(lesson_id, seed=13)
    contrasts = {
        curriculum.item(e["item_id"])["contrast"]
        for e in built if e["kind"] == "minimal_pair"
    }
    assert contrasts == exercises.AUDIBLE_CONTRASTS


def test_a_minimal_pair_offers_the_two_confusable_words():
    for lesson_id in PRIMER:
        for exercise in exercises.build_practice(lesson_id, seed=21):
            if exercise["kind"] != "minimal_pair":
                continue
            item = curriculum.item(exercise["item_id"])
            partner = curriculum.item(item["pair"])

            shown = {c["text"] for c in exercise["choices"]}
            assert shown == {item["pa"], partner["pa"]}
            assert len(exercise["choices"]) == 2

            answer = [c for c in exercise["choices"] if c["key"] == exercise["answer_key"]][0]
            assert answer["text"] == item["pa"]
            # The audio must be the word being asked about, not its partner.
            assert exercise["speak"] == item["pa"]


def test_tone_and_gemination_items_still_get_practised_another_way():
    quiet = [
        i["id"] for i in curriculum.all_items()
        if i.get("contrast") in ("tone", "gemination")
    ]
    assert quiet
    covered = set()
    for lesson_id in PRIMER:
        for exercise in exercises.build_practice(lesson_id, seed=13):
            covered.add(exercise["item_id"])
    assert set(quiet) <= covered
