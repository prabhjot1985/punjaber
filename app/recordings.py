"""Storage for native-speaker recordings.

Recordings are course content, not learner progress: they are shared by every
profile and they are the most valuable thing in the data directory. So they live
as plain files on disk — one audio file plus one JSON sidecar per clip — rather
than inside punjaber.db, which `make reset-data` is allowed to delete.

Clips are keyed by the Gurmukhi text itself, so a word used in several lessons
is recorded once and reused everywhere.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STORE_DIR = Path(os.environ.get("PUNJABER_RECORDINGS", "/data/recordings"))

# Recordings ship inside the published image, but at runtime they must live on
# the persistent volume so the studio can add to them. On a fresh deployment
# that volume is empty, so the bundled copy is seeded across once. Set by the
# Dockerfile; empty on a local checkout, where data/recordings is already the
# real thing and nothing needs copying.
SEED_DIR = Path(os.environ["PUNJABER_RECORDINGS_SEED"]) if os.environ.get(
    "PUNJABER_RECORDINGS_SEED"
) else None

# Browsers hand us whatever their MediaRecorder supports, which differs by
# engine. We store the file as-is and remember its type for playback.
EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}
DEFAULT_EXTENSION = ".webm"

MAX_BYTES = 8 * 1024 * 1024   # a spoken phrase; generous but bounded
MIN_BYTES = 512               # anything smaller is a misfire, not a recording


class RecordingError(ValueError):
    """The upload was not something we are willing to store."""


def seed_if_empty() -> int:
    """Populate an empty store from the copy bundled in the image.

    Only ever fills a store that has nothing in it, so a deployment that has
    since recorded new takes is never overwritten by the image's older ones.
    Returns the number of files copied.
    """
    if SEED_DIR is None or not SEED_DIR.is_dir():
        return 0
    if STORE_DIR.is_dir() and any(STORE_DIR.glob("*.json")):
        return 0

    STORE_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for source in SEED_DIR.iterdir():
        if not source.is_file():
            continue
        target = STORE_DIR / source.name
        if not target.exists():
            _atomic_write(target, source.read_bytes())
            copied += 1
    return copied


def key_for(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _normalise_mime(mime: str) -> str:
    """MediaRecorder reports things like 'audio/webm;codecs=opus'."""
    return (mime or "").split(";")[0].strip().lower()


def extension_for(mime: str) -> str:
    return EXTENSIONS.get(_normalise_mime(mime), DEFAULT_EXTENSION)


def _sidecar(key: str) -> Path:
    return STORE_DIR / f"{key}.json"


def meta(text: str) -> dict[str, Any] | None:
    """The stored metadata for this text, or None if it is not recorded."""
    path = _sidecar(key_for(text))
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return None


def path_for(text: str) -> Path | None:
    """The audio file for this text, or None if it is missing or unreadable."""
    record = meta(text)
    if not record:
        return None
    audio_path = STORE_DIR / record["file"]
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        return None
    return audio_path


def exists(text: str) -> bool:
    return path_for(text) is not None


def save(text: str, data: bytes, mime: str) -> dict[str, Any]:
    """Store a clip for this text, replacing any previous take."""
    if len(data) < MIN_BYTES:
        raise RecordingError("That recording is too short to keep — try again.")
    if len(data) > MAX_BYTES:
        raise RecordingError(f"Recording is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    if not _normalise_mime(mime).startswith("audio/"):
        raise RecordingError(f"Expected audio, got {mime!r}.")

    STORE_DIR.mkdir(parents=True, exist_ok=True)
    key = key_for(text)
    extension = extension_for(mime)
    filename = f"{key}{extension}"

    # Replacing a take with a different browser leaves the old file behind
    # under a different extension, so clear any previous audio first.
    _remove_audio_files(key)

    _atomic_write(STORE_DIR / filename, data)

    record = {
        "key": key,
        "text": text,
        "file": filename,
        "mime": _normalise_mime(mime),
        "bytes": len(data),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write(_sidecar(key), json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8"))
    return record


def delete(text: str) -> bool:
    key = key_for(text)
    had_any = _sidecar(key).exists()
    _remove_audio_files(key)
    _sidecar(key).unlink(missing_ok=True)
    return had_any


def all_records() -> list[dict[str, Any]]:
    if not STORE_DIR.is_dir():
        return []
    records = []
    for sidecar in STORE_DIR.glob("*.json"):
        try:
            with sidecar.open(encoding="utf-8") as handle:
                records.append(json.load(handle))
        except (json.JSONDecodeError, OSError):
            continue
    return records


def recorded_texts() -> list[str]:
    """Every text that has a playable clip — the client's manifest."""
    return [r["text"] for r in all_records() if exists(r["text"])]


def stats() -> dict[str, int]:
    records = all_records()
    return {
        "count": len(records),
        "bytes": sum(r.get("bytes", 0) for r in records),
    }


def _remove_audio_files(key: str) -> None:
    if not STORE_DIR.is_dir():
        return
    for candidate in STORE_DIR.glob(f"{key}.*"):
        if candidate.suffix != ".json":
            candidate.unlink(missing_ok=True)


def _atomic_write(target: Path, data: bytes) -> None:
    """Write via a temp file in the same directory, then rename into place.

    A half-written clip served to the player would be worse than none.
    """
    handle, temp_name = tempfile.mkstemp(dir=target.parent, suffix=".part")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(data)
        Path(temp_name).replace(target)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise
