# 🎙️ Multilingual Speaker Transcriber

Transcribe an audio or video file, **recognise who is speaking — by name, across
recordings**, handle **conversations that switch language mid-sentence**, and tag
each segment with an **emotion** fused from *how* it was said (voice tone) and
*what* was said (the words).

Runs **entirely on your machine**. The Streamlit GUI just opens in your
browser; nothing is uploaded anywhere.

```
extract audio (ffmpeg) → detect language timeline → Whisper transcription
                       → speaker diarization → recognise known speakers
                       → align speakers to words → fuse audio+text emotion
```

## What makes this different

- **Speakers are remembered.** Name someone once and every future transcript
  tags them automatically — no re-labelling each meeting.
- **Code-switching works.** A bilingual conversation is transcribed in whichever
  language is actually being spoken, with per-segment language labels.
- **It admits uncertainty.** Low-confidence lines are flagged, and a voice it
  isn't sure about stays "Speaker 2" instead of being given the wrong name.

Built for speed: transcription uses **faster-whisper** (CTranslate2, ~4x faster
than openai-whisper on CPU) with a **VAD silence filter**, the emotion stage
runs **batched**, and models are **cached in-process** so every run after the
first skips loading. See [Performance](#performance) to go faster still.

## Install

Requires Python 3.9+ and **ffmpeg** on your PATH
(`sudo apt install ffmpeg` / `brew install ffmpeg` / `choco install ffmpeg`).

```sh
cd transcriber
pip install -r requirements.txt
```

The first run downloads the Whisper and emotion models (a few hundred MB),
then caches them.

## Use it — GUI (recommended)

```sh
# from the repo root
streamlit run transcriber/gui.py
```

Upload a file (or paste a local path), pick your settings in the sidebar, and
click **Transcribe**. You get a color-coded, per-speaker transcript with
emotion tags, plus `.txt` / `.json` / `.srt` downloads.

## Remembering speakers

The first time you transcribe a file, speakers are anonymous:

```
[0:00:02] Speaker 1: Hey, glad you could make it.
[0:00:05] Speaker 2: Thanks for having me.
```

Name them once — their voiceprints are saved:

```sh
python -m transcriber meeting1.wav \
    --name-speaker "Speaker 1=Priya" --name-speaker "Speaker 2=Rahul"
```

Every later recording recognises them with no further input:

```sh
python -m transcriber standup.wav
# [0:00:01] Priya: Morning everyone.
# [0:00:04] Rahul: Morning.
```

You can also enroll from a clean clip of one person talking:

```sh
python -m transcriber speakers enroll "Priya" priya-intro.wav
```

Manage the store:

```sh
python -m transcriber speakers list
python -m transcriber speakers rename "Priya" "Priya Sharma"
python -m transcriber speakers forget "Priya"      # deletes their voiceprints
```

In the GUI, unnamed speakers get a **"Name these speakers"** box under the
transcript, and the sidebar lists everyone you have remembered.

### How recognition decides

Each diarized voice is embedded into a 256-d voiceprint and compared against
every saved speaker's centroid by cosine similarity. A name is applied only when
**both** tests pass:

- similarity ≥ `--match-threshold` (default `0.72`), **and**
- it beats the runner-up by ≥ `--match-margin` (default `0.05`).

The margin is the important one: two similar voices can both clear the
threshold, and picking the higher would silently mislabel someone. When it is
ambiguous the speaker stays anonymous — a missing name is obvious, a wrong name
is not. A known speaker is also never assigned to two voices in one recording.

Naming someone again **adds** a voiceprint rather than replacing it, so
recognition improves with every recording (capped at the 20 most recent).
Speakers with under 6s of speech are not enrolled at all — a voiceprint built
from a few seconds degrades every future match.

> **Recognition is a labelling convenience, not authentication.** It is tuned to
> fail safe (leave people unnamed), and must not be used as a security control.

### Your voiceprints stay yours

Voiceprints are biometric data, so:

- They live in a local SQLite file at `~/.transcriber/speakers.db` (override
  with `--speaker-db` or the `TRANSCRIBER_HOME` env var). `*.db` is gitignored.
- Nothing is ever uploaded — no network call carries audio or embeddings.
- `speakers forget` really deletes the rows, so "forget me" means it.
- Exported transcripts (`json`/`txt`/`srt`/`vtt`) contain names, never vectors.

Recording and enrolling other people is your call to make lawfully; the tool
does not and cannot check consent for you.

## Multiple languages

By default the language is auto-detected **and allowed to change mid-recording**,
so a Hindi/English conversation transcribes correctly throughout instead of
being force-decoded into whichever language came first.

```sh
python -m transcriber bilingual-call.m4a
# Languages: hi (142s), en (96s)
# [0:00:03] Priya [hi]: नमस्ते, कैसे हैं आप?
# [0:00:07] Rahul [en]: Doing well, thanks — shall we start?
```

Language tags only appear when a recording actually contains more than one
language. To pin a single language (slightly faster, and correct if you know
there is only one), pass `--language en`. To auto-detect once for the whole file
rather than continuously, pass `--no-multilingual`.

**How it works:** faster-whisper's `multilingual=True` re-detects the language on
every 30s decode window, which is what makes the decode correct. It does not
report *which* language each segment used, so a separate detection pass builds a
language timeline and labels every segment. A switch must be confirmed by two
consecutive windows before it is accepted, so a loanword or a name does not
register as a language change.

> The text emotion model is English-only. Non-English segments are scored on
> **voice tone alone** rather than being fed to a model that would return a
> confident wrong answer.

## Confidence

Whisper's per-word probabilities are averaged per segment and surfaced, so you
know which lines to double-check:

```
[0:01:12] Rahul [low confidence 43%]: something something quarterly
```

The GUI shows a ⚠ badge on those lines; JSON carries `confidence` on every
segment.

## Use it — command line

```sh
# from the repo root
python -m transcriber meeting.mp4                      # → stdout
python -m transcriber call.wav -o out.srt -f srt       # → subtitles
python -m transcriber pod.mp3 --model small --speakers 3 -f json -o out.json
```

Output (txt):

```
[0:00:02] Speaker 1 [happy 82%]: Hey, so glad you could make it!
[0:00:05] Speaker 2 [neutral 64%]: Thanks for having me.
[0:00:11] Speaker 1 [angry 71%]: Wait — you did WHAT with the budget?
```

### Key options

| Flag | Meaning | Default |
|------|---------|---------|
| `--model` | Whisper size: tiny/base/small/medium/large-v3, or `distil-large-v3` | `base` |
| `--language` | Pin one language (ISO code) for the whole file | auto-detect |
| `--no-multilingual` | Detect the language once instead of per 30s window | off |
| `--diarization` | `cluster` (offline) or `pyannote` (best, needs token) | `cluster` |
| `--speakers N` | Number of speakers if known | auto-detect |
| `--hf-token` | HF token for pyannote (or set `HF_TOKEN`) | — |
| `--name-speaker` | `"Speaker 1=Priya"` — name and remember a voice (repeatable) | — |
| `--no-identify` | Skip matching against remembered speakers | off |
| `--speaker-db` | Path to the speaker store | `~/.transcriber/speakers.db` |
| `--match-threshold` | Minimum voice similarity to accept a match | `0.72` |
| `--match-margin` | How far the best match must beat the runner-up | `0.05` |
| `--emotion-source` | `both` / `audio` / `text` | `both` |
| `--emotion-audio-weight` | Tone vs. words, 0..1 | `0.5` |
| `--no-emotion` | Skip emotion detection (faster) | off |
| `-f, --format` | `txt` / `json` / `srt` / `vtt` | `txt` |
| `-o, --output` | Write to a file instead of stdout | stdout |

## How speaker diarization works

Two interchangeable backends — both return the same `(start, end, speaker)`
turns, so the rest of the pipeline doesn't care which ran:

- **`cluster` (default, offline):** [Resemblyzer](https://github.com/resemble-ai/Resemblyzer)
  embeds short overlapping windows; agglomerative clustering groups them by
  voice. The speaker count is auto-detected via silhouette score (or set it
  with `--speakers`). No token, no license, works offline.
- **`pyannote`:** [pyannote.audio](https://github.com/pyannote/pyannote-audio)'s
  pretrained `speaker-diarization-3.1` — best accuracy. Needs a free
  [Hugging Face token](https://hf.co/settings/tokens) and a one-time license
  acceptance at
  [hf.co/pyannote/speaker-diarization-3.1](https://hf.co/pyannote/speaker-diarization-3.1).
  Enable by uncommenting `pyannote.audio` in `requirements.txt`.

Whisper's word-level timestamps are used to **split a transcript segment when
the speaker changes mid-sentence**, so rapid back-and-forth still separates
cleanly.

Diarization only says *"these turns are the same person"*. Turning that into
*"that person is Priya"* is the separate recognition step described in
[Remembering speakers](#remembering-speakers).

## How emotion works

Each segment is scored two ways and combined into one probability distribution
over `angry / happy / sad / fear / disgust / surprise / neutral`:

- **Audio (tone):** [`superb/hubert-large-superb-er`](https://hf.co/superb/hubert-large-superb-er)
  — HuggingFace's reference model for the audio-classification pipeline, so it
  loads cleanly. Trained on IEMOCAP, it emits four classes: **neutral / happy /
  angry / sad**. (Fear, disgust, and surprise come from the text channel.)
- **Text (content):** [`j-hartmann/emotion-english-distilroberta-base`](https://hf.co/j-hartmann/emotion-english-distilroberta-base)
  — seven classes.

Model labels are canonicalized by meaning, not exact string match, so different
naming conventions (e.g. SUPERB's `ang`/`hap` vs. `anger`/`joy`) all line up.

Tune the balance with `--emotion-audio-weight` (0 = trust words, 1 = trust
voice, 0.5 = both). The JSON output and GUI keep the per-channel labels too,
so you can see when tone and words disagree (e.g. *tone: angry · words: joy*).

**Debugging emotion:** pass `--debug-emotion` to print each segment's *raw*
per-channel model output, so you can see exactly what the audio vs. text model
predicted and which channel is driving the result:

```
[   2.4s] Speaker 1: fused=angry | audio_raw=ang 0.88 | text_raw=anger 0.79
```

> **Why not the older `ehcalabres/wav2vec2` model?** It ships a custom
> classification head that the generic `audio-classification` pipeline
> mis-loads, which made every segment collapse to "neutral" when audio was the
> only source. `superb/hubert-large-superb-er` avoids that.

> The text emotion model is English. For other languages, lean on audio
> (`--emotion-source audio`) or raise `--emotion-audio-weight`.

## Performance

The pipeline is tuned for turnaround time:

- **faster-whisper + VAD** — CTranslate2 runs Whisper ~4x faster than
  openai-whisper on CPU (int8), and `vad_filter` skips silence so dead air
  costs nothing.
- **Batched emotion** — both emotion models score all segments in mini-batches
  (one dispatch per batch) instead of one segment at a time.
- **Warm models** — loaded Whisper/emotion models are cached at module scope,
  shared across CLI files in a run *and* across Streamlit reruns, so only the
  first run pays the load cost.
- **Per-stage timing** — every run reports where the time went (CLI prints it
  to stderr; the GUI shows a metric per stage), so you can tune with data.

Going faster still:

- **GPU:** with a CUDA card, transcription and the emotion models switch to
  float16 automatically — typically 10-30x on transcription.
- **Model size:** `--model distil-large-v3` is near-large accuracy at a
  fraction of the cost; `tiny`/`base` are fastest on CPU.
- **Skip emotion:** `--no-emotion` drops the emotion stage entirely.

Example timing line (CPU, `base`, ~2 min clip):

```
Timing: extract=0.4s transcribe=18.2s diarize=6.1s emotion=3.4s  (total 28.1s)
```

## Library use

```python
from transcriber import transcribe_file

result = transcribe_file("call.wav", whisper_model="small")
print(result.languages)     # {"hi": 142.0, "en": 96.0}
print(result.identified)    # {"Speaker 1": "Priya"}

for seg in result.segments:
    print(seg.start, seg.speaker, seg.language, seg.confidence, seg.text)
```

Remember a speaker straight from a result, without re-processing the audio:

```python
from transcriber import SpeakerStore

with SpeakerStore() as store:
    store.enroll("Rahul", result.voiceprints["Speaker 2"].vector)
```

## Files

```
transcriber/
  audio.py        # ffmpeg extraction + waveform slicing
  transcribe.py   # Whisper (segments, words, confidence, multilingual decode)
  language.py     # language timeline for code-switching
  diarize.py      # both diarization backends -> unified Turns
  identify.py     # voiceprint extraction + matching against known speakers
  speakerdb.py    # persistent SQLite speaker/voiceprint store
  emotion.py      # audio + text emotion, fused, language-aware
  core.py         # pipeline + speaker/word alignment
  output.py       # txt / json / srt / vtt renderers
  cli.py          # `python -m transcriber`
  gui.py          # `streamlit run transcriber/gui.py`
  tests/          # pure-logic tests (no models or ffmpeg needed)
  SPEC.md         # what this does and why — read before changing behaviour
```

## Tests

The test suite covers matching, language smoothing, alignment, and rendering
without needing models, audio, or ffmpeg:

```sh
pip install pytest
python -m pytest transcriber/tests -q
```
