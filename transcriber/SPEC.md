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
      -> language timeline      (detect_language over windows)
      -> transcription          (faster-whisper, multilingual=True)
      -> diarization            (cluster | pyannote)  -> anonymous Speaker N
      -> speaker identification (voiceprint match vs. speaker DB) -> real names
      -> emotion                (language-aware fusion)

Identification slots between diarization and emotion: diarization says "these
turns are the same person", identification says "that person is Priya".

### Multilingual

`faster_whisper.WhisperModel.transcribe(multilingual=True)` re-runs language
detection on each 30s decode window and swaps the tokenizer, which is what makes
code-switching decode correctly. It does **not** report which language each
segment used — `Segment` has no language field and `info.language` is only the
first detection.

So `language.py` runs a separate `detect_language` pass over overlapping windows
to build a language timeline, then labels each segment by the dominant language
across its span. Cost is one extra encoder pass per window, no decode.

Contiguous same-language windows collapse into spans; spans shorter than
`min_span` (default 3s) are absorbed into their neighbour, because single-window
flips are usually detector noise rather than a real switch.

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
| `transcriber/core.py` | identification stage; per-segment `language`, `confidence` |
| `transcriber/transcribe.py` | `multilingual=True`; expose word/segment confidence |
| `transcriber/emotion.py` | skip English-only text model on non-English |
| `transcriber/output.py` | language + confidence in txt/json/srt |
| `transcriber/cli.py` | identification flags; `speakers` subcommands |
| `transcriber/gui.py` | name-a-speaker UI writing back to the store |
| `transcriber/tests/` | **new** — unit tests for matching, spans, alignment |
| `transcriber/runtime.py` | **new** — OpenMP guard; must import before any ML lib |

## Out of scope

- Real-time / streaming transcription.
- Cloud sync, multi-user accounts, sharing.
- Translation track (English translation alongside the native transcript).
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

    # 4. Confirm the store
    python -m transcriber speakers list

Success criterion: step 3 labels Priya and Rahul without being told, and a
bilingual recording shows per-segment language codes that track the actual
switches.
