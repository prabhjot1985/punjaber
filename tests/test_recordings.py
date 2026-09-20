"""Tests for native-speaker recordings and the studio worklist."""

import pytest

from app import curriculum, recordings

HELLO = "ਸਤ ਸ੍ਰੀ ਅਕਾਲ"
CLIP = b"\x1a\x45\xdf\xa3" + b"fake opus payload" * 64   # comfortably over MIN_BYTES


@pytest.fixture(autouse=True)
def clean_store():
    """Recordings are global, so each test starts and ends with an empty store."""
    for record in recordings.all_records():
        recordings.delete(record["text"])
    yield
    for record in recordings.all_records():
        recordings.delete(record["text"])


# --- storage ---------------------------------------------------------------


def test_saving_then_reading_back_a_clip():
    assert not recordings.exists(HELLO)

    record = recordings.save(HELLO, CLIP, "audio/webm;codecs=opus")
    assert record["text"] == HELLO
    assert record["mime"] == "audio/webm"       # codec parameter is stripped
    assert record["bytes"] == len(CLIP)

    assert recordings.exists(HELLO)
    assert recordings.path_for(HELLO).read_bytes() == CLIP
    assert recordings.recorded_texts() == [HELLO]


def test_keys_are_stable_and_distinct():
    other = "ਪਾਣੀ"
    assert recordings.key_for(HELLO) == recordings.key_for(HELLO)
    assert recordings.key_for(HELLO) != recordings.key_for(other)


def test_re_recording_replaces_the_previous_take():
    recordings.save(HELLO, CLIP, "audio/webm")
    replacement = CLIP + b"second take"
    recordings.save(HELLO, replacement, "audio/webm")

    assert recordings.path_for(HELLO).read_bytes() == replacement
    assert len(recordings.all_records()) == 1


def test_re_recording_in_another_format_leaves_no_orphan():
    """A second browser can hand us a different container for the same text."""
    recordings.save(HELLO, CLIP, "audio/webm")
    recordings.save(HELLO, CLIP, "audio/ogg")

    key = recordings.key_for(HELLO)
    audio_files = [p for p in recordings.STORE_DIR.glob(f"{key}.*") if p.suffix != ".json"]
    assert len(audio_files) == 1
    assert audio_files[0].suffix == ".ogg"


def test_deleting_removes_the_clip_and_its_sidecar():
    recordings.save(HELLO, CLIP, "audio/webm")
    assert recordings.delete(HELLO) is True

    assert not recordings.exists(HELLO)
    assert recordings.all_records() == []
    assert list(recordings.STORE_DIR.glob(f"{recordings.key_for(HELLO)}.*")) == []
    # Deleting again is harmless.
    assert recordings.delete(HELLO) is False


def test_junk_uploads_are_refused():
    with pytest.raises(recordings.RecordingError):
        recordings.save(HELLO, b"tiny", "audio/webm")
    with pytest.raises(recordings.RecordingError):
        recordings.save(HELLO, b"x" * (recordings.MAX_BYTES + 1), "audio/webm")
    with pytest.raises(recordings.RecordingError):
        recordings.save(HELLO, CLIP, "text/html")
    assert not recordings.exists(HELLO)


def test_extension_is_chosen_from_the_mime_type():
    assert recordings.extension_for("audio/ogg;codecs=opus") == ".ogg"
    assert recordings.extension_for("audio/mp4") == ".m4a"
    assert recordings.extension_for("audio/something-new") == recordings.DEFAULT_EXTENSION


# --- the studio worklist ---------------------------------------------------


def test_every_spoken_phrase_appears_exactly_once():
    rows = curriculum.spoken_texts()
    texts = [row["text"] for row in rows]
    assert len(texts) == len(set(texts))

    # Items and dialogue lines are both recordable.
    kinds = {row["kind"] for row in rows}
    assert kinds == {"item", "dialogue"}


def test_a_word_used_in_two_lessons_is_listed_once_and_counted():
    shared = [row for row in curriculum.spoken_texts() if row["uses"] > 1]
    assert shared, "expected at least one phrase reused across lessons"
    for row in shared:
        assert row["text"]


def test_only_course_text_counts_as_spoken():
    assert curriculum.is_spoken(HELLO)
    assert not curriculum.is_spoken("ਪੀਜ਼ਾ ਖਾਓ")


def test_studio_worklist_reports_recording_status(client):
    body = client.get("/api/studio/texts").json()
    assert body["total"] == len(curriculum.spoken_texts())
    assert body["recorded"] == 0
    assert all(row["recorded"] is False for row in body["texts"])

    recordings.save(HELLO, CLIP, "audio/webm")
    body = client.get("/api/studio/texts").json()
    assert body["recorded"] == 1
    assert [r["text"] for r in body["texts"] if r["recorded"]] == [HELLO]


# --- the HTTP surface ------------------------------------------------------


def test_uploading_a_recording_through_the_api(client):
    response = client.post(
        "/api/recordings",
        data={"text": HELLO},
        files={"clip": ("take.webm", CLIP, "audio/webm")},
    )
    assert response.status_code == 200
    assert response.json()["saved"] is True
    assert recordings.exists(HELLO)

    manifest = client.get("/api/recordings").json()
    assert manifest["texts"] == [HELLO]
    assert manifest["count"] == 1


def test_the_upload_endpoint_only_accepts_course_text(client):
    response = client.post(
        "/api/recordings",
        data={"text": "ਪੀਜ਼ਾ ਖਾਓ"},
        files={"clip": ("take.webm", CLIP, "audio/webm")},
    )
    assert response.status_code == 400
    assert recordings.all_records() == []


def test_the_upload_endpoint_rejects_a_misfire(client):
    response = client.post(
        "/api/recordings",
        data={"text": HELLO},
        files={"clip": ("take.webm", b"tiny", "audio/webm")},
    )
    assert response.status_code == 400
    assert not recordings.exists(HELLO)


def test_a_recording_takes_over_the_speech_endpoint(client):
    synthesised = client.get("/api/speech", params={"text": HELLO})
    assert synthesised.status_code == 200
    assert synthesised.headers["content-type"] == "audio/wav"

    recordings.save(HELLO, CLIP, "audio/webm")

    recorded = client.get("/api/speech", params={"text": HELLO})
    assert recorded.status_code == 200
    assert recorded.headers["content-type"] == "audio/webm"
    assert recorded.content == CLIP
    # Re-recording reuses the URL, so this must not be cached forever.
    assert "no-cache" in recorded.headers.get("cache-control", "")


def test_the_synthesiser_stays_reachable_for_comparison(client):
    recordings.save(HELLO, CLIP, "audio/webm")

    comparison = client.get("/api/speech", params={"text": HELLO, "synth": "true"})
    assert comparison.status_code == 200
    assert comparison.headers["content-type"] == "audio/wav"
    assert comparison.content[:4] == b"RIFF"


def test_deleting_a_recording_restores_the_synthesiser(client):
    recordings.save(HELLO, CLIP, "audio/webm")
    assert client.request("DELETE", "/api/recordings", params={"text": HELLO}).json()["deleted"]

    fallback = client.get("/api/speech", params={"text": HELLO})
    assert fallback.headers["content-type"] == "audio/wav"


def test_health_counts_recordings(client):
    recordings.save(HELLO, CLIP, "audio/webm")
    body = client.get("/api/health").json()
    assert body["recordings"]["count"] == 1
    assert body["recordings"]["bytes"] == len(CLIP)


# --- seeding onto a fresh data volume --------------------------------------
#
# The published image carries the course audio; a newly provisioned instance
# has an empty disk. These cover the copy that bridges the two, because a
# silent deployment is the failure this prevents.


def test_seeding_fills_an_empty_store(tmp_path, monkeypatch):
    seed = tmp_path / "seed"
    seed.mkdir()
    recordings.save(HELLO, CLIP, "audio/webm")
    for path in recordings.STORE_DIR.iterdir():
        (seed / path.name).write_bytes(path.read_bytes())
        path.unlink()

    assert not recordings.exists(HELLO)

    monkeypatch.setattr(recordings, "SEED_DIR", seed)
    assert recordings.seed_if_empty() == 2      # the clip and its sidecar
    assert recordings.exists(HELLO)
    assert recordings.path_for(HELLO).read_bytes() == CLIP


def test_seeding_never_overwrites_an_existing_store(tmp_path, monkeypatch):
    """A deployment that has recorded new takes must not be reset to the
    image's older copies on the next restart."""
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / f"{recordings.key_for(HELLO)}.webm").write_bytes(b"stale" * 200)
    (seed / f"{recordings.key_for(HELLO)}.json").write_text("{}", encoding="utf-8")

    newer = CLIP + b"newer take"
    recordings.save(HELLO, newer, "audio/webm")

    monkeypatch.setattr(recordings, "SEED_DIR", seed)
    assert recordings.seed_if_empty() == 0
    assert recordings.path_for(HELLO).read_bytes() == newer


def test_seeding_is_a_no_op_without_a_seed_directory(monkeypatch):
    """A local checkout has no bundled copy; data/recordings is the real one."""
    monkeypatch.setattr(recordings, "SEED_DIR", None)
    assert recordings.seed_if_empty() == 0


def test_seeding_tolerates_a_missing_seed_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(recordings, "SEED_DIR", tmp_path / "does-not-exist")
    assert recordings.seed_if_empty() == 0
