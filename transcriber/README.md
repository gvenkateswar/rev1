# 🎙️ Speaker & Emotion Transcriber

Transcribe an audio or video file, **tell the speakers apart**, and tag each
segment with an **emotion** that's fused from *how* it was said (voice tone)
and *what* was said (the words) — because a loud voice could be excitement or
anger, and the words tell them apart.

Runs **entirely on your machine**. The Streamlit GUI just opens in your
browser; nothing is uploaded anywhere.

```
extract audio (ffmpeg) → Whisper transcription → speaker diarization
                       → align speakers to words → fuse audio+text emotion
```

Transcription runs on **openai-whisper** (PyTorch) by default — the most
compatible engine, sharing one runtime with the emotion models. A faster
**faster-whisper** engine is available opt-in (`--whisper-backend faster`) for
machines with a modern CPU. The emotion stage runs **batched** and models are
**cached in-process** so every run after the first skips loading. See
[Performance](#performance) and [Troubleshooting](#troubleshooting).

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
streamlit run transcriber/gui.py   # from the repo root
# or, from inside the transcriber/ folder:
streamlit run gui.py
```

Upload a file (or paste a local path), pick your settings in the sidebar, and
click **Transcribe**. You get a color-coded, per-speaker transcript with
emotion tags, plus `.txt` / `.json` / `.srt` downloads.

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
| `--model` | Whisper size: tiny/base/small/medium/large | `base` |
| `--whisper-backend` | `openai` (compatible) or `faster` (quicker, modern CPU) | `openai` |
| `--language` | Force a language (ISO code) | auto-detect |
| `--diarization` | `cluster` (offline) or `pyannote` (best, needs token) | `cluster` |
| `--speakers N` | Number of speakers if known | auto-detect |
| `--hf-token` | HF token for pyannote (or set `HF_TOKEN`) | — |
| `--emotion-source` | `both` / `audio` / `text` | `both` |
| `--emotion-audio-weight` | Tone vs. words, 0..1 | `0.5` |
| `--no-emotion` | Skip emotion detection (faster) | off |
| `-f, --format` | `txt` / `json` / `srt` | `txt` |
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

- **Batched emotion** — both emotion models score all segments in mini-batches
  (one dispatch per batch) instead of one segment at a time.
- **Warm models** — loaded Whisper/emotion models are cached at module scope,
  shared across CLI files in a run *and* across Streamlit reruns, so only the
  first run pays the load cost.
- **Per-stage timing** — every run reports where the time went (CLI prints it
  to stderr; the GUI shows a metric per stage), so you can tune with data.

Going faster still:

- **Faster engine:** `--whisper-backend faster` (after `pip install
  faster-whisper`) runs Whisper ~4x faster on CPU via CTranslate2, with a
  built-in VAD that skips silence. Needs a modern (AVX) CPU — see
  [Troubleshooting](#troubleshooting) if it crashes.
- **GPU:** with a CUDA card, transcription and the emotion models switch to
  float16 automatically — typically 10-30x on transcription.
- **Model size:** `tiny`/`base` are fastest on CPU; bump up for accuracy.
- **Skip emotion:** `--no-emotion` drops the emotion stage entirely.

Example timing line (CPU, `base`, ~2 min clip):

```
Timing: extract=0.4s transcribe=18.2s diarize=6.1s emotion=3.4s  (total 28.1s)
```

## Troubleshooting

- **`segmentation fault` on launch (often after an `Intel MKL` warning).**
  This is the `faster` engine: CTranslate2 4.x needs a modern (AVX) CPU and
  loads a second OpenMP runtime that clashes with PyTorch on older Intel Macs.
  The default `openai` engine avoids it entirely — just don't pass
  `--whisper-backend faster` (and in the GUI, leave the engine on **openai**).
- **macOS `OMP: Error #15` / app aborts / Streamlit "Connection error".**
  Same root cause (two OpenMP runtimes), seen when the `faster` engine and
  PyTorch coexist. The app sets `KMP_DUPLICATE_LIB_OK=TRUE` automatically; if
  you still hit it, stick to the `openai` engine, or export it yourself:
  ```sh
  export KMP_DUPLICATE_LIB_OK=TRUE
  ```
- **`File does not exist: transcriber/gui.py`.** You're already inside the
  `transcriber/` folder — run `streamlit run gui.py` instead (or `cd ..` first).
- **ffmpeg not found.** Install it: `brew install ffmpeg` (macOS).

## Library use

```python
from transcriber import transcribe_file

result = transcribe_file("call.wav", whisper_model="small")
for seg in result.segments:
    print(seg.start, seg.speaker, seg.emotion, seg.text)
```

## Files

```
transcriber/
  audio.py        # ffmpeg extraction + waveform slicing
  transcribe.py   # Whisper (segment + word timestamps)
  diarize.py      # both diarization backends -> unified Turns
  emotion.py      # audio + text emotion, fused
  core.py         # pipeline + speaker/word alignment
  output.py       # txt / json / srt renderers
  cli.py          # `python -m transcriber`
  gui.py          # `streamlit run transcriber/gui.py`
```
