"""Tests for offline pronunciation audio.

These run against the real espeak-ng in the image, because the thing worth
testing is that the synthesiser actually renders the contrasts the course
claims it does. They skip cleanly if it is not installed.
"""

import wave

import pytest

from app import audio, curriculum, exercises

pytestmark = pytest.mark.skipif(not audio.available(), reason="espeak-ng is not installed")

HELLO = "ਸਤ ਸ੍ਰੀ ਅਕਾਲ"  # sat sri akal


def read_frames(path):
    with wave.open(str(path)) as handle:
        return handle.readframes(handle.getnframes())


def test_rendering_produces_a_playable_wav():
    path = audio.render(HELLO)
    assert path.exists() and path.stat().st_size > 1000
    with wave.open(str(path)) as handle:
        assert handle.getnframes() > 0
        assert handle.getframerate() > 0


def test_the_same_text_is_only_rendered_once():
    path = audio.render(HELLO)
    first_mtime = path.stat().st_mtime_ns
    assert audio.render(HELLO) == path
    assert path.stat().st_mtime_ns == first_mtime


def test_speed_changes_the_audio_and_the_cache_key():
    normal = audio.render(HELLO, "normal")
    slow = audio.render(HELLO, "slow")
    assert normal != slow
    with wave.open(str(normal)) as a, wave.open(str(slow)) as b:
        assert b.getnframes() > a.getnframes()


def test_bad_input_is_rejected():
    with pytest.raises(ValueError):
        audio.render("")
    with pytest.raises(ValueError):
        audio.render(HELLO, "sprint")
    with pytest.raises(ValueError):
        audio.render("ਸ" * (audio.MAX_TEXT_LENGTH + 1))


def test_gurmukhi_detection_gates_the_endpoint():
    assert audio.is_gurmukhi(HELLO)
    assert not audio.is_gurmukhi("sat sri akal")
    assert not audio.is_gurmukhi("")


def test_the_synthesiser_distinguishes_the_contrasts_the_course_drills():
    """Every audio-drilled minimal pair must actually sound different."""
    drilled = [i for i in curriculum.all_items() if exercises.hearable_pair(i)]
    assert drilled, "expected some audio-drillable minimal pairs"

    for item in drilled:
        partner = curriculum.item(item["pair"])
        assert read_frames(audio.render(item["pa"])) != read_frames(
            audio.render(partner["pa"])
        ), f"{item['roman']} and {partner['roman']} render identically"


def test_gemination_is_not_drilled_by_ear_because_espeak_ignores_it():
    """Guards the reason addak pairs are taught in writing only.

    If a future espeak-ng starts honouring the addak, this test fails and the
    contrast can be promoted into AUDIBLE_CONTRASTS.
    """
    geminate = [
        i for i in curriculum.all_items()
        if i.get("contrast") == "gemination" and i.get("pair")
    ]
    assert geminate, "expected the primer to teach gemination"
    assert "gemination" not in exercises.AUDIBLE_CONTRASTS

    identical = 0
    for item in geminate:
        partner = curriculum.item(item["pair"])
        if read_frames(audio.render(item["pa"])) == read_frames(audio.render(partner["pa"])):
            identical += 1
    assert identical, "espeak-ng now distinguishes the addak; revisit AUDIBLE_CONTRASTS"


def test_phonemes_expose_the_aspiration_contrast():
    kaal = audio.phonemes("ਕਾਲ")
    khaal = audio.phonemes("ਖਾਲ")
    assert kaal != khaal
    assert "#" in khaal  # espeak marks aspiration with a trailing #


# --- the HTTP surface ------------------------------------------------------


def test_the_speech_endpoint_serves_cacheable_audio(client):
    response = client.get("/api/speech", params={"text": HELLO})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert "immutable" in response.headers.get("cache-control", "")
    assert response.content[:4] == b"RIFF"


def test_the_speech_endpoint_rejects_junk(client):
    assert client.get("/api/speech", params={"text": "hello"}).status_code == 400
    assert client.get("/api/speech", params={"text": ""}).status_code == 400
    assert client.get(
        "/api/speech", params={"text": HELLO, "speed": "sprint"}
    ).status_code == 400


def test_health_reports_audio_availability(client):
    body = client.get("/api/health").json()
    assert body["audio"]["offline"] is True
    assert body["audio"]["cache"]["files"] >= 0
