# 🎙️ Multilingual Speaker Transcriber

Transcribe an audio or video file, **recognise who is speaking — by name, across
recordings**, handle **conversations that switch language mid-sentence**, and tag
each segment with an **emotion** fused from *how* it was said (voice tone) and
*what* was said (the words).

Runs **entirely on your machine**. The Streamlit GUI just opens in your
browser; nothing is uploaded anywhere.

```
extract audio (ffmpeg) → detect language timeline → transcribe each span
                       → translate non-English spans → speaker diarization
                       → recognise known speakers → align speakers to words
                       → transliterate non-Latin scripts → fuse audio+text emotion
```

## What makes this different

- **Speakers are remembered.** Name someone once and every future transcript
  tags them automatically — no re-labelling each meeting.
- **Code-switching works.** A bilingual conversation is transcribed in whichever
  language is actually being spoken, with per-segment language labels.
- **Non-English stays non-English.** Speech is kept in its own script, and each
  line also gets a Latin transliteration and an English translation — three
  renderings of the same words, not one lossy compromise.
- **It admits uncertainty.** Low-confidence lines are flagged, and a voice it
  isn't sure about stays "Speaker 2" instead of being given the wrong name.

Built for speed: transcription uses **faster-whisper** (CTranslate2, ~4x faster
than openai-whisper on CPU) with a **VAD silence filter**, the emotion stage
runs **batched**, and models are **cached in-process** so every run after the
first skips loading. See [Performance](#performance) to go faster still.

## Install

Requires **Python 3.10+** (uroman, the transliterator, needs it) and **ffmpeg**
on your PATH (`sudo apt install ffmpeg` / `brew install ffmpeg` /
`choco install ffmpeg`).

```sh
pip install -r transcriber/requirements.txt
```

The first run downloads the Whisper and emotion models (a few hundred MB),
then caches them.

On **Apple Silicon**, install a native arm64 Python — a Rosetta x86 build is
several times slower and loads two conflicting copies of the OpenMP runtime.
See [Troubleshooting](#troubleshooting) if you hit `Abort trap: 6`, a segfault
after switching venvs, or `No module named 'pkg_resources'`; each has a
one-line fix there.

## Use it — GUI (recommended)

```sh
# from the repo root
streamlit run transcriber/gui.py
```

Upload a file (or paste a local path), pick your settings in the sidebar, and
click **Transcribe**. You get a color-coded, per-speaker transcript with
emotion tags — and, for non-English lines, the transliteration and translation
underneath — plus `.txt` / `.json` / `.srt` / `.vtt` downloads.

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

Non-English speech stays in the script it was spoken in, and carries two more
renderings of the same words:

```sh
python -m transcriber bilingual-call.m4a
# Languages: hi (142s), en (96s)
# [0:00:03] Priya [hi]: नमस्ते, कैसे हैं आप?
#           [latin] namaste, kaise haim aap?
#           [english] Hello, how are you?
# [0:00:07] Rahul [en]: Doing well, thanks — shall we start?
```

| Rendering | What it is | JSON field |
|---|---|---|
| Native script | What was said, written the way it is written | `text` |
| Latin transliteration | The *same words*, spelled in the Latin alphabet | `latin` |
| English translation | What those words *mean*, in English | `english` |

Both extra lines appear only when they add something. An English segment gets
neither. A segment already written in Latin letters — French, Vietnamese,
Turkish — gets a translation but no transliteration, because romanizing it
would just reprint the line. All four output formats carry them: `txt`, `json`,
`srt` and `vtt`.

- `--no-transliterate` skips the romanization.
- `--no-translate` skips the translation. It is a second Whisper pass, so this
  is the faster option.
- `--language en` pins one language for the whole file.
- `--no-multilingual` auto-detects once instead of building a timeline.

### How it works

The language timeline comes first: overlapping 30s probes, 15s apart, and a
switch is only accepted once **two consecutive probes agree** — so a loanword
or a name does not register as a language change.

Each span is then decoded **with its language pinned**. This is the part that
keeps Hindi in Devanagari. Two things otherwise push Whisper into English:

1. Left to itself, it re-detects on each 30s window in isolation. Our timeline
   sees overlapping windows and requires confirmation, so it is the better
   answer — and once you have it, guessing again during the decode can only
   lose.
2. Whisper conditions each window on the text it produced for the previous
   one. Across a language change that prompt is a block of the *old* language,
   and the model follows it. Spans are decoded independently, so nothing
   prompts the next span in the wrong language.

The English translation is Whisper's own `translate` task — English is the only
target it was trained for — run as a second pass over the non-English spans
only. The transliteration is [uroman](https://pypi.org/project/uroman/), a
rule-driven romanizer: no model, no network, one API for every script.

> **Use `--model small` or better for non-English speech.** `tiny` and `base`
> have high error rates outside English and will drift into English on their
> own, whatever the pipeline pins. This is a model-quality limit, not a
> settings problem.

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
| `--no-multilingual` | Detect the language once instead of building a timeline | off |
| `--no-transliterate` | Skip the Latin transliteration of non-Latin scripts | off |
| `--no-translate` | Skip the English translation (saves a second Whisper pass) | off |
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

## Troubleshooting

### "zsh: command not found: python" — then it segfaults

These are the same problem: **the venv is not activated.**

`python` exists only inside the venv. If the shell cannot find it, you are
outside, and `python3` then resolves to whatever system Python is on PATH —
on this Mac, an x86_64 3.9 under Rosetta, which is the configuration that
crashes.

```bash
cd /path/to/rev1
source .venv/bin/activate
python -m streamlit run transcriber/gui.py    # `python`, not `python3`
```

`python -V` should say 3.12, and `python -c "import platform; print(platform.machine())"`
should say `arm64`. If either is wrong, see
[macOS on Apple Silicon](#macos-on-apple-silicon-use-a-native-arm64-python).

The run gets a fair way in before dying — the terminal shows extract,
language, transcribe and translate all completing — because the crash happens
when diarization loads its models, well after startup. The per-stage log is
what tells you where:

```
transcriber: translate: done in 4.0s
transcriber: diarize: started
zsh: segmentation fault
```

A segfault leaves no Python traceback: the crash is below the interpreter, so
there is nothing to catch and nothing to print. The stage log is the only
record of how far it got.

### The process crashes with "Abort trap: 6" / a Python crash report

If the crash report mentions `__kmp_abort_process` in `libiomp5.dylib`, or you
see this on the terminal:

```
OMP: Error #15: Initializing libiomp5.dylib, but found libiomp5.dylib already
initialized.
```

then two copies of the Intel OpenMP runtime were loaded into one process:
faster-whisper (through ctranslate2) and torch each bundle their own. This
pipeline needs both libraries, so both copies load, and the second one aborts
the process. It is not catchable -- `abort()` produces a crash report, not a
traceback.

**This is handled automatically.** `transcriber/runtime.py` sets
`KMP_DUPLICATE_LIB_OK=TRUE` when the package is imported, before either library
can load. If you still hit it, something imported `torch` *before*
`transcriber` -- import `transcriber` first, or export the variable in your
shell:

```sh
export KMP_DUPLICATE_LIB_OK=TRUE
```

Set `TRANSCRIBER_NO_OMP_FIX=1` to disable the workaround (useful only when
diagnosing a different problem).

### Segfault, or "Intel MKL WARNING", after switching to a venv

```
Intel MKL WARNING: Support of Intel(R) Streaming SIMD Extensions 4.2 ...
zsh: segmentation fault  streamlit run transcriber/gui.py
```

**There is no Intel MKL build for arm64.** If you see that line on an M-series
Mac, the process is running x86 code -- meaning the `streamlit` on your PATH is
not the one in your virtualenv, even though the prompt shows `(.venv)`.

The usual cause is your shell's command cache. `zsh` remembers where it found
`streamlit` the first time you ran it; activating a venv afterwards changes
`PATH` but does not clear that memory, so the old interpreter keeps running with
the old (x86) site-packages.

Check which one is actually running:

```sh
which streamlit          # should be <repo>/.venv/bin/streamlit
python -c "import sys, platform; print(sys.executable, platform.machine())"
```

Fix it by clearing the cache, or just open a new terminal:

```sh
hash -r                  # zsh/bash: forget cached command paths
```

Then prefer the module form, which always uses the interpreter you mean and
cannot be shadowed by a stale PATH entry:

```sh
python -m streamlit run transcriber/gui.py
```

> Note: with `KMP_DUPLICATE_LIB_OK` set (which this package does automatically),
> a mismatched-architecture environment segfaults instead of printing the
> `OMP: Error #15` abort -- the crash is quieter, not absent. Set
> `TRANSCRIBER_NO_OMP_FIX=1` to get the explicit OpenMP error back while
> diagnosing.

### macOS on Apple Silicon: use a native arm64 Python

If `python3 -c "import platform; print(platform.machine())"` prints `x86_64` on
an M-series Mac, you are running under Rosetta. Two consequences: everything is
several times slower than it needs to be, and the x86 wheels are what drag in
the duplicate OpenMP runtimes above. The CLI and GUI both warn when they detect
this.

Fix it with a native interpreter and a fresh virtualenv:

```sh
# Install an arm64 Python (python.org universal2 installer, or Homebrew)
brew install python@3.12

python3.12 -c "import platform; print(platform.machine())"   # -> arm64
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r transcriber/requirements.txt
```

Native arm64 also lets faster-whisper and torch use the Apple accelerators,
which is the single biggest speedup available on these machines.

### "Pipeline.from_pretrained() got an unexpected keyword argument 'use_auth_token'"

pyannote.audio 4.x renamed that argument to `token`. The diarizer now reads the
installed version's signature and passes whichever name it expects, so both 3.x
and 4.x work. If you still see this, you are running an older checkout -- pull.

If pyannote instead reports that no pipeline was returned, your token is valid
but has not accepted the model licence. Accept it at
[hf.co/pyannote/speaker-diarization-3.1](https://hf.co/pyannote/speaker-diarization-3.1)
with the **same account** the token belongs to.

The offline `cluster` backend (the default) needs no token and is unaffected.

### "'DiarizeOutput' object has no attribute 'itertracks'"

pyannote.audio 4.x wraps its result in a `DiarizeOutput` dataclass instead of
returning a bare `Annotation`. Handled -- the diarizer unwraps whichever shape
the installed version returns. Pull if you still see it.

On 4.x it takes `exclusive_speaker_diarization` in preference to
`speaker_diarization`. pyannote documents that one as "adapted to downstream
transcription": it drops overlapping speech turns, and this pipeline assigns
each Whisper word to the turn covering it, which is ambiguous when two turns
overlap.

### It has been on one stage for ages — is it stuck?

Almost certainly not, if that stage is **Separating speakers** with the
`pyannote` backend. pyannote runs slower than real time on a CPU: a 20-minute
recording can take well over 20 minutes, and nothing about the old progress
bar distinguished that from a hang.

Both surfaces now answer the question:

- The terminal you launched from prints a line when each stage starts and
  finishes, plus the audio duration and backend up front:

      transcriber: 1183s of audio | model=base diarization=pyannote
      transcriber: extract: started
      transcriber: extract: done in 0.4s
      transcriber: diarize: started
      transcriber: diarize: done in 412.7s

  Set `TRANSCRIBER_QUIET=1` to turn these off.

- The progress bar shows the stage, pyannote's own sub-step, and a running
  clock, so a bar that is not moving still visibly counts up. The offline
  `cluster` backend reports its stages too.

**One thing that used to make this worse:** the results block rendered the
*previous* run's transcript and timings underneath the in-progress bar, so a
finished-looking set of numbers sat under a bar that was still working. The
previous result is now cleared when a run starts.

To make it faster: use the `cluster` backend (seconds rather than minutes, at
some accuracy cost), pass `--speakers N` when you know the count (it skips the
search over 2..8 speakers), or run on a CUDA GPU.

### Non-English speech comes out written in English

Two causes, and they stack.

**The pipeline used to let Whisper pick the language during decoding.** Fixed:
each detected language span is now decoded with its language pinned, and spans
are decoded independently so one cannot prompt the next in the wrong language.
See [How it works](#how-it-works) above for why both halves of that matter.

**The model may simply be too small.** `tiny` and `base` have high error rates
outside English and drift into it on their own — no amount of pinning fixes a
model that does not know the language well. Use `--model small` or better
(`medium`, `large-v3`), or `distil-large-v3` for near-large accuracy at a
fraction of the cost. In the GUI, the model dropdown carries the same note.

If you know the whole recording is in one language, `--language hi` is both
faster and stricter than auto-detection.

### "No module named 'pkg_resources'" from Resemblyzer

Fix:

```bash
pip install "setuptools<82"
```

`pip install setuptools` on its own does **not** work. Chain:

1. Resemblyzer's `audio.py` does `import webrtcvad`.
2. webrtcvad 2.0.10's module does `import pkg_resources`, only to read its
   own version string.
3. `pkg_resources` ships with setuptools -- which venvs stopped creating by
   default on Python 3.12, and which **removed `pkg_resources` in 82.0.0**.
   81.0.0 is the last release that has it, so an unpinned install gets a
   version without it.

`transcriber/requirements.txt` pins the cap, so a fresh
`pip install -r transcriber/requirements.txt` is already correct; this only
bites a venv built before the pin, or one where Resemblyzer was installed by
hand.

The `webrtcvad-wheels` fork fixes the root cause (it reads its version with
`importlib.metadata`) and ships prebuilt wheels, but it installs the same
`webrtcvad.py` and `_webrtcvad.so` as the `webrtcvad` that Resemblyzer
depends on, so pip installs both and install order decides which one wins.
Not worth the coin flip.

### "X is not installed" when you know it is

Fixed. This was our bug, not yours.

`ModuleNotFoundError` is a subclass of `ImportError`, so a guard written as
`except ImportError` around `import resemblyzer` also fires when Resemblyzer
imports fine but *one of its own dependencies* does not. The old message
blamed the package you had and told you to reinstall it, which could never
help.

Every optional dependency now goes through one helper that reads
`ImportError.name` to tell the two cases apart, and reports the module that
actually failed:

    resemblyzer is installed but failed to import (needed to recognise
    speakers): its dependency webrtcvad could not be loaded.
      ModuleNotFoundError: No module named 'webrtcvad'
    Reinstalling resemblyzer will not fix this -- the broken package is
    webrtcvad. Run `python -c "import resemblyzer"` for the full traceback.

The browser only ever shows the message; the GUI now also prints the full
chained traceback to the terminal it was launched from.

If you hit this, run the one-liner it suggests. The traceback names the file
and the line inside the dependency chain, which is what tells you whether to
pin a version, install a missing package, or rebuild a wheel.

### Harmless warnings from pyannote

`std(): degrees of freedom is <= 0` comes from pyannote's pooling layer on a
speech turn too short to have a variance. It does not stop diarization.

### Hundreds of "No module named 'torchvision'" tracebacks in the terminal

Harmless, and silenced by `.streamlit/config.toml` in this repo. Streamlit's
file watcher walks every imported package looking for files to reload on;
transformers 5 exposes ~100 image processors as lazy attributes, and touching
them tries to import torchvision, which an audio pipeline has no reason to
install. Nothing is broken -- the tracebacks just bury the real output.

The config disables the watcher, so source edits no longer live-reload the app;
restart it instead. Set `fileWatcherType = "auto"` if you want reload back.

### "Class AVFFrameReceiver is implemented in both ..." on macOS

Also harmless. PyAV bundles its own ffmpeg libraries and Homebrew's `ffmpeg`
installs another copy; macOS notes the duplicate Objective-C classes. It does
not affect transcription.

### ffmpeg not found

`ffmpeg` is a system dependency, not a pip package:
`brew install ffmpeg` / `sudo apt install ffmpeg` / `choco install ffmpeg`.

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
  Stage start/finish also goes to stderr as it happens, so a long run is
  visibly alive rather than silently pending.

Going faster still:

- **GPU:** with a CUDA card, transcription and the emotion models switch to
  float16 automatically — typically 10-30x on transcription.
- **Model size:** `--model distil-large-v3` is near-large accuracy at a
  fraction of the cost; `tiny`/`base` are fastest on CPU.
- **Skip emotion:** `--no-emotion` drops the emotion stage entirely.
- **Diarization backend:** `cluster` (the default) is seconds where `pyannote`
  is minutes on CPU. pyannote is more accurate; on a long recording it is also
  the entire runtime. `--speakers N` skips its search over speaker counts.
- **Skip translation:** `--no-translate` drops the second Whisper pass. It runs
  over the non-English spans only, so on an English recording there is nothing
  to save; on an all-Hindi one it is close to a second full decode.

Example timing line (CPU, `base`, ~2 min clip):

```
Timing: extract=0.4s language=1.1s transcribe=18.2s translate=9.7s
        diarize=6.1s emotion=3.4s  (total 38.9s)
```

## Library use

```python
from transcriber import transcribe_file

result = transcribe_file("call.wav", whisper_model="small")
print(result.languages)     # {"hi": 142.0, "en": 96.0}
print(result.identified)    # {"Speaker 1": "Priya"}

for seg in result.segments:
    print(seg.start, seg.speaker, seg.language, seg.confidence, seg.text)
    if seg.latin:                       # None when already in Latin script
        print("   latin:  ", seg.latin)
    if seg.english:                     # None when already English
        print("   english:", seg.english)
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
  transcribe.py   # Whisper: per-span decode, translate pass, confidence
  language.py     # language timeline for code-switching
  translit.py     # Latin transliteration of non-Latin scripts (uroman)
  diarize.py      # both diarization backends -> unified Turns
  identify.py     # voiceprint extraction + matching against known speakers
  speakerdb.py    # persistent SQLite speaker/voiceprint store
  emotion.py      # audio + text emotion, fused, language-aware
  core.py         # pipeline + speaker/word alignment
  output.py       # txt / json / srt / vtt renderers
  runtime.py      # OpenMP guard + optional-dependency imports
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
