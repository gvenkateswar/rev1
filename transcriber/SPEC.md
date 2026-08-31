# SPEC — Multilingual transcription with persistent speaker identity

Source of truth for what the transcriber does and why. Update this before
changing behaviour.

## Goal

Transcribe audio/video at a quality bar comparable to Otter, with two
capabilities Otter charges for or lacks:

1. **Code-switching multilingual** — a recording where speakers switch language
   mid-conversation transcribes correctly throughout, with each segment
   labelled by the language actually spoken.
2. **Speaker memory** — speakers are recognised across recordings. Name someone
   once; every later transcript tags them automatically.

Everything runs locally. No audio or voiceprint leaves the machine.

## Mode

PRODUCTION. Real audio, real biometric data, persistent state on disk.

## Privacy: this stores biometric data

A voiceprint is a biometric identifier. Treat the store accordingly:

- Lives at `~/.transcriber/speakers.db` (override: `TRANSCRIBER_HOME` env var or
  `--speaker-db`). Never inside the repo; `*.db` is gitignored.
- Local-only. Nothing is uploaded, and no network call carries embeddings.
- `speakers forget` deletes a speaker and their voiceprints outright — a real
  delete, not a soft flag, so "forget me" is honourable.
- Enrolling a third party's voice is the operator's legal call, not the tool's.
  README states this; the tool does not enforce consent.

## Design

### Pipeline

    extract audio (ffmpeg)
      -> language timeline      (detect_language over overlapping windows)
      -> transcription          (one decode per span, language pinned)
      -> translation            (Whisper translate task, non-English spans)
      -> diarization            (cluster | pyannote)  -> anonymous Speaker N
      -> speaker identification (voiceprint match vs. speaker DB) -> real names
      -> transliteration        (uroman, non-Latin scripts)
      -> emotion                (language-aware fusion)

Identification slots between diarization and emotion: diarization says "these
turns are the same person", identification says "that person is Priya".

### Multilingual

`language.py` runs a `detect_language` pass over overlapping windows (30s, 15s
hop) to build a language timeline. Cost is one encoder pass per window, no
decode. Contiguous same-language windows collapse into spans; spans shorter
than `min_span` (default 3s) are absorbed into their neighbour, and a switch
must be confirmed by two consecutive probes, because single-window flips are
usually detector noise rather than a real switch.

The timeline then **steers the decode**: each span is transcribed separately
with `language=` pinned to it. Two reasons, both observed as non-English
speech coming back written in English:

1. `transcribe(multilingual=True)` re-detects on each 30s window in isolation.
   The timeline sees overlapping windows and requires confirmation, so it is
   the better answer; re-guessing during the decode can only lose. It also
   does not report which language each segment used — `Segment` has no
   language field and `info.language` is only the first detection — so it
   could never have labelled segments on its own.
2. Whisper conditions each window on the previous window's output
   (`condition_on_previous_text`, default True). Across a language change that
   prompt is a block of the old language and the model follows it. Spans are
   decoded independently, so no span prompts the next one. Where a single pass
   is still used (no timeline, or a pinned language), the flag is off unless
   the language is pinned.

Whisper model size is the remaining limit: `tiny` and `base` have high error
rates outside English and drift into it regardless. Documented in the README
and in both UIs rather than worked around.

### Three renderings

Non-English speech is presented three ways, because the useful rendering
depends on the reader:

| Field | Content | Produced by |
|---|---|---|
| `text` | the words, in the script they were spoken in | Whisper `transcribe` |
| `latin` | the *same words*, in the Latin alphabet | uroman |
| `english` | what those words *mean* | Whisper `translate` |

Each optional field is `None` when it would add nothing — `latin` for text
already in Latin script (including accented Latin: French, Vietnamese,
Turkish), `english` for English. The renderers show a line only for a field
that is set, so an English transcript is unchanged.

Translation is Whisper's own `translate` task; English is the only target it
was trained for. It is a second decode, so it runs over the non-English spans
only and is skippable (`--no-translate`).

The two passes segment independently, so they cannot be zipped. Each
translated segment is assigned to the transcript segment it overlaps most — a
partition, so no sentence is attributed to two speakers.

Transliteration uses uroman: rule-driven (no model, no network) and script-
driven, so one API covers every writing system instead of a per-script library
that silently does nothing for the script nobody wired up. It is imported only
when a run actually has a non-Latin script to romanize.

### Speaker identification

Embeddings are Resemblyzer 256-d unit-norm vectors — the same encoder the
`cluster` diarization backend already uses, so no new dependency.

Per diarized cluster: concatenate that cluster's speech, embed once, get a
voiceprint. Match against every known speaker's centroid (normalised mean of
their stored voiceprints) by cosine similarity.

A match is accepted only when **both** hold:

- `sim >= threshold` (default 0.72), and
- `sim - runner_up_sim >= margin` (default 0.05).

The margin matters more than the threshold: two similar voices can both clear
0.72, and picking the higher one silently mislabels people. Ambiguity stays
anonymous rather than guessing.

Assignment is one-to-one and greedy over globally sorted candidate pairs — one
known speaker cannot be assigned to two clusters in the same recording, since a
person cannot be two participants in one conversation.

**Enrollment quality gate.** A cluster with less than `min_enroll_seconds`
(default 6s) of speech is not enrollable. Short, noisy voiceprints poison the
store and degrade every future match, so refusing is better than storing junk.
Matching against short audio is still allowed — only writing is gated.

Naming an already-known speaker appends a voiceprint rather than replacing it,
so the centroid improves with each recording. Samples are capped at
`max_samples` (default 20, oldest evicted) to bound drift and DB size.

### Language-aware emotion

The text emotion model is English-only RoBERTa. Today it scores non-English text
anyway and returns confident nonsense. Fix: for non-English segments use the
audio channel alone, and record that the text channel was skipped rather than
silently reweighting.

## Files

| File | Change |
|---|---|
| `transcriber/speakerdb.py` | **new** — SQLite store: schema, CRUD, centroids |
| `transcriber/identify.py` | **new** — voiceprint extraction, matching, assignment |
| `transcriber/language.py` | **new** — language timeline, span grouping |
| `transcriber/translit.py` | **new** — uroman romanization, script test |
| `transcriber/core.py` | identification, translation and transliteration stages; per-segment `language`, `latin`, `english`, `confidence` |
| `transcriber/transcribe.py` | per-span decode, translate task, timestamp shifting, confidence |
| `transcriber/emotion.py` | skip English-only text model on non-English |
| `transcriber/output.py` | language, confidence and the three renderings in txt/json/srt/vtt |
| `transcriber/cli.py` | identification flags; `speakers` subcommands |
| `transcriber/gui.py` | name-a-speaker UI writing back to the store |
| `transcriber/tests/` | **new** — unit tests for matching, spans, alignment |
| `transcriber/runtime.py` | **new** — OpenMP guard; must import before any ML lib; `require()` for optional deps |

## Optional dependency errors

faster-whisper, pyannote.audio, Resemblyzer and scikit-learn are all imported
lazily, at the point the stage that needs them runs, so a user who never turns
on diarization never has to install its dependencies.

Those imports go through `runtime.require()`, never a bare
`except ImportError`. `ModuleNotFoundError` subclasses `ImportError`, so a
bare guard cannot tell "this package is missing" from "this package is present
and something inside its import chain is broken", and reports both as absence.
`require()` reads `ImportError.name`: it equals the requested module only in
the genuine-absence case. Anything else names the module that actually failed,
quotes the original exception, and says that reinstalling will not help.

The original exception is always chained (`raise ... from exc`). The GUI shows
only `str(exc)`, so it also prints the traceback to the terminal.

## Out of scope

- Real-time / streaming transcription.
- Cloud sync, multi-user accounts, sharing.
- Translation into any language other than English. Whisper's translate task
  has one target and there is no second translation model here.
- Voice as an authentication factor. Matching here is a labelling convenience
  with a deliberate false-negative bias; it is not a security control.
- Replacing the diarization backends.

## Verification

On macOS, ctranslate2 and torch each bundle `libiomp5`; the second to load
aborts the process. `runtime.py` sets `KMP_DUPLICATE_LIB_OK` at package import,
before either can load. Keep that import first in `__init__.py`.

Pure-logic tests (no ML deps, no audio) must pass:

    python -m pytest transcriber/tests -q

End-to-end, on a machine with the full requirements and ffmpeg installed:

    # 1. First pass — speakers are anonymous
    python -m transcriber meeting1.wav
    #    -> [0:00:02] Speaker 1: ...

    # 2. Name them; voiceprints are stored
    python -m transcriber meeting1.wav --name-speaker "Speaker 1=Priya" \
                                       --name-speaker "Speaker 2=Rahul"

    # 3. A different recording, same voices — names appear with no prompting
    python -m transcriber meeting2.wav
    #    -> [0:00:05] Priya: ...

    # 4. A non-English recording — three renderings, native script first
    python -m transcriber hindi-call.m4a --model small
    #    -> [0:00:03] Priya [hi]: नमस्ते, कैसे हैं आप?
    #                 [latin] namaste, kaise haim aap?
    #                 [english] Hello, how are you?
    #    Check: the first line is in Devanagari, not English. If it is not,
    #    the model is too small before anything else is wrong.

    # 5. Confirm the store
    python -m transcriber speakers list

Success criterion: step 3 labels Priya and Rahul without being told; a
bilingual recording shows per-segment language codes that track the actual
switches; and step 4's native line is in the script that was spoken.
