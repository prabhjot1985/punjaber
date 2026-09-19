"""Offline pronunciation audio, rendered by espeak-ng and cached on disk.

Browser speech synthesis turned out to be a lottery: Edge exposes a real
Punjabi neural voice, Chrome has none and falls back to a Hindi voice that
cannot read Gurmukhi, and Firefox on Windows has neither. Rendering server-side
means every learner hears exactly the same thing, offline, in any browser.

espeak-ng's Punjabi voice is a formant synthesiser, so it sounds robotic — but
it renders the contrasts an English speaker actually gets wrong (aspiration,
retroflex vs dental, and tone). It does *not* render gemination; see
GEMINATION_IS_SILENT below.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CACHE_DIR = Path(os.environ.get("PUNJABER_AUDIO", "/data/audio"))

VOICE = "pa"
ESPEAK = "espeak-ng"

# Words per minute. The slow setting is for picking apart a phrase you missed.
SPEEDS = {"normal": 140, "slow": 90}
DEFAULT_SPEED = "normal"

# Guards on the text we hand to a subprocess.
MAX_TEXT_LENGTH = 300
GURMUKHI_RANGE = (0x0A00, 0x0A7F)

# espeak-ng ignores the addak (U+0A71), so `sat` and `satt` render identically.
# Unit 0 therefore teaches gemination in writing and never as a listening drill.
GEMINATION_IS_SILENT = True

RENDER_TIMEOUT_SECONDS = 15


class AudioUnavailable(RuntimeError):
    """espeak-ng is not installed in this container."""


def available() -> bool:
    return shutil.which(ESPEAK) is not None


def is_gurmukhi(text: str) -> bool:
    """True if the text contains at least one Gurmukhi letter.

    Used to reject junk before it reaches the synthesiser, and to skip
    rendering for the handful of romanised placeholders in the course.
    """
    return any(GURMUKHI_RANGE[0] <= ord(ch) <= GURMUKHI_RANGE[1] for ch in text)


def cache_path(text: str, speed: str = DEFAULT_SPEED) -> Path:
    digest = hashlib.sha256(f"{VOICE}:{speed}:{text}".encode("utf-8")).hexdigest()[:32]
    return CACHE_DIR / f"{digest}.wav"


def render(text: str, speed: str = DEFAULT_SPEED) -> Path:
    """Return a cached WAV for this text, synthesising it on first request."""
    if not available():
        raise AudioUnavailable(f"{ESPEAK} is not installed")

    text = (text or "").strip()
    if not text:
        raise ValueError("nothing to speak")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"text is longer than {MAX_TEXT_LENGTH} characters")
    if speed not in SPEEDS:
        raise ValueError(f"speed must be one of {sorted(SPEEDS)}")

    target = cache_path(text, speed)
    if target.exists() and target.stat().st_size > 0:
        return target

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Render to a temp file in the same directory, then rename. Two concurrent
    # requests for the same phrase then cannot serve a half-written file.
    handle, temp_name = tempfile.mkstemp(dir=CACHE_DIR, suffix=".wav")
    os.close(handle)
    temp_path = Path(temp_name)

    try:
        # Arguments are passed as a list and never through a shell, and the
        # text is validated above, so there is no injection surface here.
        subprocess.run(
            [ESPEAK, "-v", VOICE, "-s", str(SPEEDS[speed]), "-w", str(temp_path), "--", text],
            check=True,
            capture_output=True,
            timeout=RENDER_TIMEOUT_SECONDS,
        )
        if temp_path.stat().st_size == 0:
            raise AudioUnavailable("espeak-ng produced an empty file")
        temp_path.replace(target)
    except subprocess.CalledProcessError as error:
        temp_path.unlink(missing_ok=True)
        raise AudioUnavailable(error.stderr.decode("utf-8", "replace")[:200]) from error
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return target


def phonemes(text: str) -> str:
    """The phoneme string espeak-ng derives — handy for debugging content."""
    if not available():
        raise AudioUnavailable(f"{ESPEAK} is not installed")
    result = subprocess.run(
        [ESPEAK, "-v", VOICE, "-q", "-x", "--", text],
        capture_output=True,
        text=True,
        timeout=RENDER_TIMEOUT_SECONDS,
    )
    return result.stdout.strip()


def cache_stats() -> dict[str, int]:
    if not CACHE_DIR.is_dir():
        return {"files": 0, "bytes": 0}
    files = list(CACHE_DIR.glob("*.wav"))
    return {"files": len(files), "bytes": sum(f.stat().st_size for f in files)}


def clear_cache() -> int:
    if not CACHE_DIR.is_dir():
        return 0
    files = list(CACHE_DIR.glob("*.wav"))
    for path in files:
        path.unlink(missing_ok=True)
    return len(files)
