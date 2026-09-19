# Punjaber

A progressive course that takes an English speaker to conversational Punjabi in
small, easy increments. A pronunciation primer plus ten units — 33 lessons and
278 words and phrases, each one in Gurmukhi, romanised Punjabi and English, with
offline audio and spaced repetition so what you learn stays learned.

Runs entirely in Docker. You need nothing installed but Docker and `make`.

## Start

```sh
make start
```

Then open **http://localhost:8000**.

```sh
make down     # stop
make logs     # follow the logs
make test     # run the test suite
make help     # every command
```

To run on a different port: `PUNJABER_PORT=9000 make start`.

## How the course works

Each lesson is three stages:

1. **Learn** — flashcards for every new word: Gurmukhi, romanisation, meaning,
   a spoken pronunciation, and a note where the word has a catch.
2. **Notes and dialogue** — the grammar pattern behind the lesson, then the words
   used in a short conversation you would actually have.
3. **Practice** — every word drilled twice, in different directions: recognise it,
   produce it, hear it, type it, or assemble a sentence from scrambled words. In
   the pronunciation primer you also get minimal pairs: two words that differ by
   one sound, and you pick the one you heard.

Score 80% or better and the next lesson unlocks. Below that, the lesson repeats —
which is the point, not a punishment.

Words you have met come back on a **spaced-repetition schedule** (a trimmed-down
SM-2). Get one right and it moves further out — 1 day, 3 days, then multiplying.
Get one wrong and it returns immediately and starts the ladder again. The
**Review** tab drills whatever is due, mixed across the whole course.

Answer speed feeds the schedule too: an instant answer is graded "easy" and
pushed out further than a laboured one.

## The curriculum

| Unit | Title | You can... |
|-----:|-------|-----------|
| — | Sounds and Script *(optional primer)* | make the sounds English does not have, and know what tone is |
| 1 | First Words | greet, thank, apologise, answer "how are you?" |
| 2 | Meeting People | use pronouns, exchange names, say where you're from |
| 3 | Numbers and Counting | count, ask prices, give your age |
| 4 | Family and People | name relatives, introduce someone, say how many children you have |
| 5 | Asking Questions | use the question words, and rescue yourself when lost |
| 6 | Food and Drink | order, say you're hungry, compliment the cook, refuse politely |
| 7 | Out and About | follow directions, name places, haggle in a market |
| 8 | Time and Daily Life | talk about today and tomorrow, tell the time, describe your routine |
| 9 | Verbs and Making Sentences | use "to be", eight core verbs, and build your own sentences |
| 10 | Real Conversations | small talk, being a guest, a full hello-to-goodbye exchange |

Units 1–5 give you survival Punjabi. Units 6–8 make you useful in daily
situations. Units 9–10 move you from repeating phrases to building your own.

The **Sounds and Script** primer sits before Unit 1 but never blocks it — you
can start at "hello" and come back to phonetics whenever you like. It covers the
four things Punjabi does that English does not:

- **Aspiration** — the puff of air that separates `pal` (a moment) from `phal`
  (fruit). English has both sounds but uses them at random; Punjabi does not.
- **Retroflex vs dental** — `taal` (rhythm) versus `ttaal` (postpone). English
  `t` and `d` sit halfway between the two and are wrong for both. This is the
  single biggest giveaway of an English accent.
- **Tone** — Punjabi is tonal. `ghorha` (horse) and `korha` (whip) differ only
  in pitch.
- **Gemination** — the addak doubles a consonant: `pata` (knowledge) versus
  `patta` (leaf).

## Pronunciation and audio

Audio comes from one of two places, and the app always prefers the better one:

1. **Your own recordings**, if you have made any — see [Recording in your own
   voice](#recording-in-your-own-voice) below.
2. **espeak-ng**, rendered offline inside the container. It has a native Punjabi
   voice that reads Gurmukhi directly, so every learner hears the same thing in
   every browser, with no network call and nothing to install. Clips are
   synthesised once and cached under `./data/audio`.

The 🐢 button replays a word slowly.

This replaced browser speech synthesis, which turned out to be a lottery: Edge
exposes a real Punjabi neural voice, Chrome has none and fell back to a Hindi
voice that cannot read Gurmukhi at all, and Firefox on Windows had neither. If
your browser *does* have a genuine Punjabi voice, Punjaber prefers it — it
sounds far better than a formant synthesiser. Settings → Voice lets you force
either, and reports what it found.

**What the built-in voice does and does not do.** This is measured, not assumed,
and the measurements are pinned by tests in `tests/test_audio.py`:

| Feature | Rendered? | So the course... |
|---|---|---|
| Aspiration (`k` / `kh`) | Yes, clearly | drills it by ear with minimal pairs |
| Retroflex vs dental | Yes, clearly | drills it by ear with minimal pairs |
| Tone | Barely | teaches it in writing only |
| Gemination (addak) | No — ignored outright | teaches it in writing only |

Asking someone to hear a difference that is not in the audio teaches them
nothing, so the primer only turns the first two into listening exercises. If a
future espeak-ng starts honouring the addak, `test_audio.py` fails and tells you
to move that contrast into `exercises.AUDIBLE_CONTRASTS`.

For tone and gemination especially, trust the written explanation over what you
hear. Recorded human audio is the only real fix for those two — so the app can
record it.

## Recording in your own voice

If you speak Punjabi, the **Studio** tab replaces the synthesiser with you.

```
make start   →   http://localhost:8000   →   Studio
```

It lists all **323 distinct phrases** the course speaks — every vocabulary item
plus every dialogue line — in course order, and walks you through them. The flow
is built for the keyboard, because clicking through 323 recordings would be an
ordeal:

| Key | Does |
|---|---|
| <kbd>space</kbd> | start recording / stop and save |
| <kbd>→</kbd> <kbd>←</kbd> | step through every phrase, recorded or not |
| <kbd>n</kbd> | jump to the next phrase still needing a recording |
| <kbd>p</kbd> | play your take |
| <kbd>s</kbd> | play the synthesiser, to compare |

Stopping uploads the clip and jumps straight to the next unrecorded phrase, so
the fast loop is just: read, space, speak, space, repeat.

**Fixing a bad take.** The arrows move through the *whole* course in order, not
just the phrases still outstanding, so you can always walk back to something you
already recorded, play it, and record over it. Re-recording deliberately does
*not* auto-advance — it leaves you on the phrase so you can play it back and
check you actually fixed it. The filter tabs only change the list below; they
never limit where the arrows can take you.

The studio also reopens at the first phrase you have not recorded, so coming
back to it resumes rather than starting from the top.

**Recording once is enough.** Clips are keyed by the Gurmukhi text, not by
lesson, so a word that appears in several lessons (`ਤਾਲ` is in both primer
lessons) is recorded once and used everywhere — which is why 278 items plus 61
dialogue lines come to 323 rather than 339.

**Your voice takes over immediately.** Every part of the app already plays audio
from a single endpoint, and that endpoint prefers a recording whenever one
exists. Save a clip and the flashcards, drills, dialogues and reviews all switch
to it on the spot — no rebuild, no re-import, no setting to flip. Anything not
yet recorded keeps using the synthesiser, so a half-finished pass is perfectly
usable.

The 🐢 slow button still works on recordings: they play back at 60% speed
(browsers preserve pitch), while un-recorded phrases get a properly re-articulated
slow rendering from espeak-ng.

Delete a take and that phrase silently falls back to the synthesiser again.

### Tips for a usable pass

- Record somewhere quiet, close to the mic, at a steady level.
- Say it the way you would to a learner: clear, unhurried, but not robotic.
- Leave a beat of silence before and after — clipped starts are the most common
  problem, and the studio does not trim for you.
- Units 0–3 first if you want the biggest early win; a learner meets those most.

### Where recordings live

`./data/recordings/` on the host, as one audio file plus a small JSON sidecar per
clip. They are deliberately kept **out of** `punjaber.db` so that
`make reset-data` — which wipes learner progress — can never touch them.

```sh
make recordings-backup    # tar them into ./backups
make recordings-restore   # restore the newest backup
```

They are also **not** in `.gitignore`, on the grounds that the one irreplaceable
thing in the project should be hard to lose. If you would rather not commit
audio, uncomment `data/recordings/` there.

### Browser requirements

Recording needs microphone access, which browsers only grant on a secure origin.
**`http://localhost:8000` counts as secure** and works in Chrome, Edge and
Firefox. Reaching the app over your LAN by IP address does not — the Studio tab
will tell you so rather than failing silently. Everything else in Punjaber works
fine over LAN.

## Settings

- **Script** — show both Gurmukhi and romanisation (default), Gurmukhi only
  (harder), or romanised only (easier). Start with both; drop the romanisation
  once the letters start to stick.
- **Gender** — Punjabi verbs change with the speaker's gender
  (`main kamm karda han` vs `main kamm kardi han`). Lessons teach both forms
  where it matters.
- **Audio** — on or off.
- **Voice** — automatic (a real browser Punjabi voice if you have one, otherwise
  the built-in offline voice), or force either. The hint underneath tells you
  what was actually detected; **Test voice** plays a phrase so you can check.
- **Profile name** — separate profiles keep separate progress in the same
  container.

## Your data

Progress lives in a SQLite database at `./data/punjaber.db` on the host, mounted
into the container, alongside the rendered audio cache in `./data/audio`.
Rebuilding the image never touches either. Nothing leaves your machine — there
is no account, no network call, no telemetry.

```sh
make reset-data   # delete the database (asks first)
```

The **Reset progress** button in Settings clears one profile without touching
the others.

## Development

```sh
make dev    # live reload; edit app/, web/ or the course JSON and refresh
make test   # 84 tests, in the same image the app ships in
make shell  # a shell inside the container
```

### Layout

```
app/
  main.py              FastAPI routes and the lock/unlock rules
  curriculum/          course loader, validated at import
    data/*.json        the course content — one file per unit
  exercises.py         generates drills from curriculum items
  audio.py             espeak-ng rendering and the on-disk clip cache
  recordings.py        native-speaker clips: storage, lookup, manifest
  srs.py               spaced-repetition scheduling (SM-2, trimmed)
  db.py                SQLite persistence
web/                   the client: one HTML file, one CSS file, one JS file
tests/                 curriculum integrity, SRS maths, exercise generation,
                       audio contrasts, recordings, API
```

### Adding to the course

Drop a new JSON file in `app/curriculum/data/`, following the shape of the
existing ones — a unit with an `order`, a title, a description, and lessons of
at least four items each. Every item needs `id`, `pa`, `roman` and `en`.
Optional item fields: `note` (background), `say` (a pronunciation hint shown on
the flashcard), and `pair` + `contrast` to declare a minimal pair. A unit marked
`"optional": true` is offered in sequence but never gates the lessons after it.

A `pair` must point at another item that points back, and a `contrast` listed in
`exercises.AUDIBLE_CONTRASTS` turns the pair into a listening drill — so only
add one there if the synthesiser genuinely renders it.

The loader validates on startup, so a malformed file fails immediately with a
message naming the file rather than breaking a lesson later. `make test` checks
that every `pa` field is really Gurmukhi, every `roman` field is ASCII, and that
ids are unique across the whole course.

Exercises are generated, not authored — new items get the full range of drills
automatically.

### API

`GET /api/course`, `GET /api/lessons/{id}`, `GET /api/lessons/{id}/practice`,
`POST /api/lessons/{id}/complete`, `POST /api/attempts`, `GET /api/review`,
`GET /api/speech?text=…&speed=normal|slow&synth=true`, `GET /api/stats`,
`GET|PUT /api/settings`, `POST /api/reset`.

Studio: `GET /api/studio/texts` (the worklist), `GET /api/recordings` (the
manifest the client uses to know which phrases have a real voice),
`POST /api/recordings` (multipart: `text` + `clip`), `DELETE /api/recordings?text=…`.

Uploads are accepted only for text that actually appears in the course, so this
is not a general file-upload endpoint.

Interactive docs at http://localhost:8000/docs while the app is running. The
profile is chosen with an `X-Punjaber-User` header, defaulting to `local`.

## Without make

```sh
docker compose up -d --build          # start
docker compose down                   # stop
docker compose run --rm --no-deps punjaber python -m pytest -q   # test
```

## A note on the Punjabi

The course teaches spoken Majhi/standard Punjabi as used in Indian Punjab,
written in Gurmukhi. Romanisation is deliberately plain ASCII — `sat sri akal`,
not `sat srī akāl` — so you can type it on any keyboard. Typed answers are
matched forgivingly: capitals, punctuation, extra spaces and diacritics are all
ignored.
