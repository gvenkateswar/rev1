# 🎼 Hindustani Music Lesson Transcriber

Transcribe a recorded lesson from your guru. It **separates the singing from
the talking**, writes the singing as **sargam against your Sa**, transcribes the
**Hindi/English code-switched** explanation around it, and hands you a
**practice sheet** you can actually work from six weeks later.

Runs **entirely on your machine**. Recordings of your gurus never leave it.

```
extract audio (ffmpeg) → track pitch (YIN) → find Sa → cut into swaras
                       → label each stretch sung / spoken
                       → Whisper on the SPOKEN parts only
                       → guru vs. student → repair the vocabulary
```

## Why this is not just the [speaker transcriber](../transcriber/README.md) with a different prompt

The ordering is inverted. In `transcriber/`, Whisper leads and everything else
annotates what it found. Here **pitch analysis runs first and gates speech
recognition**, because on a music lesson Whisper alone fails in four specific
ways:

| What Whisper does to a lesson | What this does instead |
|---|---|
| Hallucinates sentences over alaap — it is a speech model, and singing is not silence, so it invents words to fill it | Classifies sung stretches from pitch first and only decodes the spoken ones |
| Throws away the actual musical content: the notes | Writes every sung phrase as sargam (`N R G m D N S'`) against your Sa, with the cents each swara was held off equal temperament |
| Picks one language for the file, so a Hindi/English sentence comes out half-wrong | Re-detects the language per window, and romanizes the Devanagari so you can read it while singing |
| Has barely heard the vocabulary: "bandish" → "band dish", "teentaal" → "tea total", "Raag Yaman" → "raga man" | Injects the domain glossary into *every* decoding window (`hotwords`, not `initial_prompt` — that one only conditions the first 30 seconds), then repairs what still came out wrong, auditably |

## Install

Requires Python 3.9+ and **ffmpeg** on your PATH
(`sudo apt install ffmpeg` / `brew install ffmpeg` / `choco install ffmpeg`).

```sh
cd music_lesson
pip install -r requirements.txt
```

The first run downloads the Whisper model. Pitch analysis needs no model at
all — it is plain NumPy in `pitch.py`.

## Use it — command line

On macOS use `python3` — the python.org install does not create a `python`
alias, so plain `python` is "command not found".

Comments go on their own line below — an interactive `zsh` does not treat a
trailing `#` as a comment and will pass it to the program as an argument.

```sh
# from the repo root; writes a practice sheet to stdout
python3 -m music_lesson lesson.m4a

# tell it your Sa
python3 -m music_lesson lesson.m4a --tonic C#3

# subtitles with sargam
python3 -m music_lesson lesson.m4a -f srt -o lesson.srt

# everything, including every note
python3 -m music_lesson lesson.m4a -f json -o lesson.json

# fastest useful first pass on a long lesson
python3 -m music_lesson lesson.m4a --tonic C#3 --beam-size 1 --no-speakers
```

**Set `--tonic`.** You know what your tanpura is tuned to; the detector is
guessing. Everything musical downstream — every swara name, the scale, the raag
cross-check — is relative to Sa, so this one flag matters more than the model
size.

## Use it — GUI

```sh
# from the repo root
streamlit run music_lesson/gui.py
```

Point it at a local path (no upload limit), set your Sa in the sidebar, and
read the practice sheet, the colour-coded transcript, or download any format.

## How long it takes, and how to tell a slow run from a stuck one

Everything except speech recognition is fast: pitch tracking runs about 70x
faster than realtime, so a 40-minute lesson is analysed for Sa, swaras and
sung/spoken in well under a minute. **Whisper is the whole cost.** On a laptop
CPU, `small` decodes at roughly 0.5-1.5x realtime, so 20 minutes of *talking*
(the singing is skipped) takes somewhere between 15 and 40 minutes. `medium` is
about 3x slower again.

The progress bar reports the percentage through the speech while it decodes,
and the label says how many minutes it has to get through — so a run that is
working looks like `Transcribing 18 min of talking — 34%`. Two things can
still look like a hang:

- **The first run downloads the model** (~460 MB for `small`, ~1.5 GB for
  `medium`) before any progress appears. Check with `du -sh ~/.cache/huggingface`.
- **A stuck run uses no CPU.** `top` will show the process pinned near 100% of
  a core if it is decoding. If it is at 0% for minutes with the model already
  downloaded, something is genuinely wrong.

To go faster: `--beam-size 1` (roughly 1.5-2x), `--no-speakers` (skips
diarization entirely), and a smaller model. On Apple silicon, plain CPU
inference is already what faster-whisper uses; there is no MPS path.

## What comes out

```markdown
# Lesson notes — 2024-03-12-yaman.m4a

## At a glance
- **Sa (tonic):** C#3 (+4c) — 138.9 Hz · set by you
- **Scale:** S R G M P D N — Kalyan thaat (100% fit); could be Yaman, Yaman Kalyan, Kedar
- **Raags named out loud:** Yaman
- **Cross-check:** the sung notes fit Kalyan thaat, which is where Yaman lives — consistent
- **Time:** 18:22 sung, 24:06 spoken

## Demonstrations to copy
- **4:31** (Guru · 22s) `N R G M D N S' N D P M G R S`
  - held off equal temperament: Ga +18c, teevra Ma +22c

## Call and response
- **4:31** guru `N R G M D N S'` → **4:58** you `N R G M D N S'`

## Terms used in this lesson
- **meend** — a continuous glide between two swaras
- **nyas** — a resting note a phrase is allowed to settle on

## Transcript
**0:14** Guru: Aaj hum Raag Yaman karenge, alaap se shuru.
**4:31** Guru *sings* — `N R G M D N S'`
```

### Key options

| Flag | Meaning | Default |
|------|---------|---------|
| `--tonic` | Your Sa: `C#3`, `D3`, `138.6` | detect it |
| `--model` | Whisper size: tiny/base/small/medium/large-v3 | `small` |
| `--beam-size` | Whisper beam width; 1 is ~1.5-2x faster | `5` |
| `--language` | Force `hi` or `en` | detect per window |
| `--term WORD` | Extra vocabulary to prime the decoder (repeatable) | — |
| `--sung-threshold` | How readily a stretch counts as singing, 0..1 | `0.50` |
| `--keep-sung-text` | Keep Whisper's words over singing (bandish lyrics) | off |
| `--no-vocabulary-fix` | Skip the Hindustani vocabulary repair | off |
| `--no-speakers` | Skip diarization (faster, no Guru/Student labels) | off |
| `--guru LABEL` | Which raw speaker is the guru, e.g. `'Speaker 2'` | whoever talks most |
| `-f, --format` | `md` / `txt` / `json` / `srt` | `md` |

## How the music side works

**Pitch** (`pitch.py`) — YIN, hand-rolled on NumPy: cumulative mean normalized
difference over FFT-computed correlation, parabolic interpolation, and a
subharmonic guard (a voice over a tanpura is two periodic sounds at a simple
ratio, so the *mixture* has a real period an octave or a fifth below the voice,
and YIN is right to find it — we want the voice). Runs ~70× faster than
realtime on a laptop CPU.

**Finding Sa** (`swara.py`) — every voiced frame folds into a one-octave cents
histogram, weighted by how long each note was held, with phrase-final notes
weighted double because phrases resolve onto nyas swaras and most often onto Sa
itself. That histogram is correlated against a template of how a Hindustani
performance actually spends its time — heavy on Sa and Pa, light on the
tritone. The pauses between phrases help rather than hurt: with the singer
silent, the tracker locks onto the tanpura, and those long steady runs land
on Sa.

**Swaras** (`swara.py`) — a note is a run of frames that stays inside a ±45
cent band. Each run is labelled with the nearest of the twelve swaras, and the
leftover cents are kept, because that deviation is the musically interesting
part: a komal Ga sung 30 cents flat is usually the raag being sung *correctly*.

**Sung vs. spoken** (`segmentation.py`) — four features per one-second window:
held-note coverage weighted by how long each note is held, the longest single
sustain, how continuously the voice is on, and how close the held pitches sit
to actual swara positions. Speech pitch moves constantly and rarely parks;
singing parks on a swara and stays. On synthetic material the score separates
roughly 0.45 (speech) from 0.95 (singing). Regions are then snapped to the
notes actually held inside them, because a one-second window can only place a
boundary to within half its own length.

**Scale** (`raga.py`) — reports the **thaat**, which is a set of swaras and
therefore decidable from pitch, and flags exact matches against the distinctive
pentatonic and hexatonic raags. It does **not** claim to name a raag from
pitch: Bhimpalasi and Kafi share every note, and no amount of counting pitch
classes will separate them. What separates them is phrase shape — and the
guru saying the name out loud, which `lexicon.py` catches and the practice
sheet cross-references against the notes.

## macOS notes

- **"OMP: Error #15 … libiomp5.dylib already initialized" / `zsh: abort`** —
  two native wheels (CTranslate2 and torch) each bundle their own OpenMP
  runtime, and loading both into one process aborts it. Fixed twice over as of
  this version: the transcription path no longer imports torch at all, and
  when diarization legitimately loads it, the package sets Intel's documented
  escape hatch (`KMP_DUPLICATE_LIB_OK=TRUE`) before either library
  initializes, noting it in the run's output. Export the variable yourself
  (either value) and your setting wins. `--no-speakers` avoids torch entirely.
- **`zsh: command not found: python`** — use `python3`.

## Known limits — read this before you trust it

- **Sa detection can land on the wrong scale degree** on a recording with
  little sustained singing, or where the student's Sa differs from the guru's.
  The practice sheet prints the detector's confidence, and the CLI warns below
  25%. Use `--tonic`.
- **A loud tanpura confuses the pitch tracker** during phrase gaps, where the
  voice-plus-drone mixture is genuinely periodic an octave below. The
  subharmonic guard handles the common case; a drone mixed nearly as loud as
  the voice will still produce the odd octave-displaced note.
- **Raag identification is a hint, not an answer** — see `raga.py` above.
  Treat "could be Yaman, Kedar, Hamir" as the candidate list it says it is.
- **Whisper's Hindi is mediocre**, and its Hinglish is worse. `--model small`
  is the floor; `medium` is noticeably better on code-switching. Expect to fix
  names by hand.
- **Vocabulary repair can over-fire.** Ambiguous English words ("mind", "tan",
  "sum") are only repaired in a sentence that is already talking about music,
  but a sentence about music that also says "I don't mind" will get it wrong.
  Every repair is listed in the JSON export under `corrections`, and
  `--no-vocabulary-fix` turns the whole pass off.
- **Bengali is not specially handled.** Whisper will detect and transcribe it,
  the vocabulary and romanization passes are Hindi-only, so a Bengali stretch
  comes out as a plain Whisper transcript in Bengali script.
- **Tala is not detected.** Sam, matra and laya are picked up only when
  somebody says them. Detecting the cycle from tabla would be a real addition
  and is not here.
- **Two voices, singing, is hard for diarization.** Resemblyzer embeds a sung
  voice poorly; if the guru/student labels look wrong, use `--guru 'Speaker 2'`
  or `--no-speakers`.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

47 tests, no model downloads and no network: everything runs against
synthesized audio whose correct answer is known by construction — a phrase sung
at a known Sa must come back as the sargam that was synthesized, speech must
not be labelled as singing, and the whole pipeline is exercised end to end with
only Whisper and the diarizer stubbed.

## File layout

```
music_lesson/
  pitch.py           # YIN pitch tracking on NumPy
  swara.py           # tonic detection, note segmentation, swara naming
  segmentation.py    # sung / spoken / drone / silent
  raga.py            # thaat and raag candidates from a swara set
  lexicon.py         # Hindustani vocabulary, Whisper prompt, repairs
  translit.py        # Devanagari to readable Roman
  transcribe.py      # Whisper wrapper: domain prompt, per-window language
  core.py            # pipeline orchestration
  output.py          # txt / json / srt / practice sheet
  cli.py, gui.py     # front ends
```

`transcriber/` is reused for audio extraction, the Whisper model cache, and
speaker diarization rather than forked.

## One non-obvious thing about talking to Whisper

Every clip you hand faster-whisper via `clip_timestamps` is padded to a full
30-second window before the encoder runs — so a 2-second clip costs exactly
what a 30-second one does. A lesson that alternates "listen — *sings* — now
you" every few seconds would be chopped into hundreds of clips and take longer
than transcribing the whole recording twice.

So `speech_spans()` decodes *through* sung interjections shorter than 12
seconds and discards their output afterwards, and only splits the clip list
around sustained singing, where both the saving and the hallucination risk are
real.
