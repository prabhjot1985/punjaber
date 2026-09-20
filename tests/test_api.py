"""End-to-end tests over the HTTP API, including the full progression path."""

from app import curriculum

FIRST = curriculum.LESSON_SEQUENCE[0]
SECOND = curriculum.LESSON_SEQUENCE[1]


def pass_lesson(client, lesson_id):
    """Answer every practice exercise correctly and record the pass."""
    exercises = client.get(f"/api/lessons/{lesson_id}/practice").json()["exercises"]
    for exercise in exercises:
        client.post(
            "/api/attempts",
            json={"item_id": exercise["item_id"], "kind": exercise["kind"], "correct": True},
        )
    return client.post(
        f"/api/lessons/{lesson_id}/complete",
        json={"correct": len(exercises), "total": len(exercises)},
    ).json()


def test_health_reports_the_loaded_curriculum(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["curriculum"]["lessons"] == 33


def test_the_course_starts_with_the_two_openers_available(client):
    course = client.get("/api/course").json()
    open_now = [
        l["id"] for u in course["units"] for l in u["lessons"] if l["status"] == "available"
    ]
    # The primer's first lesson, and the first lesson of the main course.
    assert open_now == [FIRST, curriculum.REQUIRED_SEQUENCE[0]]
    assert course["summary"]["next_lesson"] == FIRST
    assert course["summary"]["percent"] == 0


def test_the_primer_never_blocks_the_main_course(client):
    main_first = curriculum.REQUIRED_SEQUENCE[0]
    # Untouched primer, yet the real course is open from the start.
    assert client.get(f"/api/lessons/{main_first}").json()["locked"] is False
    assert client.get(f"/api/lessons/{main_first}/practice").status_code == 200


def test_passing_a_lesson_unlocks_the_next_one(client):
    assert client.get("/api/lessons/" + SECOND).json()["locked"] is True

    result = pass_lesson(client, FIRST)
    assert result["passed"] is True
    assert result["score"] == 1.0
    assert result["unlocked_next"] == SECOND

    assert client.get("/api/lessons/" + SECOND).json()["locked"] is False
    course = client.get("/api/course").json()
    assert course["summary"]["lessons_passed"] == 1
    assert course["summary"]["next_lesson"] == SECOND


def test_a_failing_score_does_not_unlock_anything(client):
    result = client.post(
        f"/api/lessons/{FIRST}/complete", json={"correct": 5, "total": 20}
    ).json()
    assert result["passed"] is False
    assert result["unlocked_next"] is None
    assert client.get("/api/lessons/" + SECOND).json()["locked"] is True


def test_a_locked_lesson_will_not_hand_out_practice(client):
    response = client.get(f"/api/lessons/{SECOND}/practice")
    assert response.status_code == 403


def test_best_score_is_kept_and_attempts_accumulate(client):
    client.post(f"/api/lessons/{FIRST}/complete", json={"correct": 18, "total": 20})
    client.post(f"/api/lessons/{FIRST}/complete", json={"correct": 4, "total": 20})
    result = client.post(f"/api/lessons/{FIRST}/complete", json={"correct": 10, "total": 20}).json()
    assert result["best_score"] == 0.9
    assert result["attempts"] == 3


def test_a_typed_answer_is_graded_against_the_romanisation(client):
    item = curriculum.lesson(FIRST)["items"][0]

    right = client.post(
        "/api/attempts",
        json={"item_id": item["id"], "kind": "type_roman", "given": item["roman"].upper()},
    ).json()
    assert right["correct"] is True
    assert right["expected"]["pa"] == item["pa"]

    wrong = client.post(
        "/api/attempts",
        json={"item_id": item["id"], "kind": "type_roman", "given": "definitely not it"},
    ).json()
    assert wrong["correct"] is False


def test_an_attempt_needs_an_answer_and_a_real_item(client):
    item_id = curriculum.lesson(FIRST)["items"][0]["id"]
    assert client.post("/api/attempts", json={"item_id": item_id}).status_code == 422
    assert client.post(
        "/api/attempts", json={"item_id": "nope", "correct": True}
    ).status_code == 404


def test_answering_schedules_the_item_for_review(client):
    item_id = curriculum.lesson(FIRST)["items"][0]["id"]
    result = client.post("/api/attempts", json={"item_id": item_id, "correct": True}).json()
    assert result["schedule"]["interval_days"] == 1
    assert result["schedule"]["due_at"]

    # Scheduled a day out, so it is not due now.
    assert client.get("/api/review").json()["due_count"] == 0


def test_a_wrong_answer_comes_back_in_the_review_queue(client):
    item_id = curriculum.lesson(FIRST)["items"][0]["id"]
    client.post("/api/attempts", json={"item_id": item_id, "correct": False})

    review = client.get("/api/review").json()
    assert review["due_count"] == 1
    assert review["exercises"][0]["item_id"] == item_id


def test_review_is_empty_for_a_learner_who_has_done_nothing(client):
    review = client.get("/api/review").json()
    assert review["exercises"] == []
    assert review["due_count"] == 0


def test_practice_exercises_are_well_formed(client):
    body = client.get(f"/api/lessons/{FIRST}/practice?seed=1").json()
    assert body["count"] == len(body["exercises"])
    for exercise in body["exercises"]:
        assert exercise["item_id"]
        assert exercise["instruction"]
        assert exercise["reveal"]["en"]


def test_stats_track_accuracy_and_progress(client):
    pass_lesson(client, FIRST)
    item_id = curriculum.lesson(FIRST)["items"][0]["id"]
    client.post("/api/attempts", json={"item_id": item_id, "correct": False})

    stats = client.get("/api/stats").json()
    assert stats["lessons_passed"] == 1
    assert stats["answers"] > 0
    assert 0 < stats["accuracy"] < 1
    assert stats["streak"] == 1
    assert stats["trouble_words"][0]["item_id"] == item_id
    assert stats["words_total"] == curriculum.stats()["items"]


def test_progress_is_kept_separate_per_profile(client):
    pass_lesson(client, FIRST)
    assert client.get("/api/course").json()["summary"]["lessons_passed"] == 1

    other = client.get("/api/course", headers={"X-Punjaber-User": "someone-else"}).json()
    assert other["summary"]["lessons_passed"] == 0

    client.post("/api/reset", headers={"X-Punjaber-User": "someone-else"})


def test_settings_round_trip_and_validate(client):
    assert client.get("/api/settings").json()["script"] == "both"

    saved = client.put("/api/settings", json={"script": "roman", "audio": False}).json()
    assert saved["script"] == "roman"
    assert saved["audio"] is False
    assert saved["gender"] == "male"  # untouched keys survive

    assert client.get("/api/settings").json()["script"] == "roman"
    assert client.put("/api/settings", json={"daily_goal": 9999}).status_code == 422


def test_reset_clears_everything_for_the_profile(client):
    pass_lesson(client, FIRST)
    client.post("/api/reset")

    course = client.get("/api/course").json()
    assert course["summary"]["lessons_passed"] == 0
    assert client.get("/api/stats").json()["answers"] == 0
    assert client.get("/api/lessons/" + SECOND).json()["locked"] is True


def test_unknown_lessons_are_not_found(client):
    assert client.get("/api/lessons/nope").status_code == 404
    assert client.get("/api/lessons/nope/practice").status_code == 404
    assert client.post("/api/lessons/nope/complete", json={"correct": 1, "total": 1}).status_code == 404


def test_the_web_app_is_served(client):
    home = client.get("/")
    assert home.status_code == 200
    assert "Punjaber" in home.text
    assert client.get("/app.js").status_code == 200
    assert client.get("/styles.css").status_code == 200


def test_the_whole_course_can_be_completed_in_order(client):
    for lesson_id in curriculum.LESSON_SEQUENCE:
        assert client.get(f"/api/lessons/{lesson_id}").json()["locked"] is False
        assert pass_lesson(client, lesson_id)["passed"] is True

    summary = client.get("/api/course").json()["summary"]
    assert summary["percent"] == 100
    assert summary["next_lesson"] is None


def test_health_reports_the_active_backend_and_studio_state(client):
    body = client.get("/api/health").json()
    assert body["backend"] == "sqlite"
    assert body["studio"] is True


def test_studio_uploads_are_refused_when_recording_is_disabled(client, monkeypatch):
    """A public deployment must not accept audio from anyone who finds the URL."""
    from app import main

    monkeypatch.setattr(main, "STUDIO_ENABLED", False)
    phrase = curriculum.lesson(FIRST)["items"][0]["pa"]

    upload = client.post(
        "/api/recordings",
        data={"text": phrase},
        files={"clip": ("take.webm", b"x" * 2048, "audio/webm")},
    )
    assert upload.status_code == 403

    removal = client.request("DELETE", "/api/recordings", params={"text": phrase})
    assert removal.status_code == 403

    # Reading the course is unaffected: learners only ever read.
    assert client.get("/api/course").status_code == 200
    assert client.get("/api/recordings").status_code == 200
    assert client.get("/api/studio/texts").status_code == 200
