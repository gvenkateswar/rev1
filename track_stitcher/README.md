# Track Stitcher

A local Streamlit app that combines a folder of ambient music tracks into one
continuous, beat-matched, crossfaded mix, exported as a single 24-bit / 48 kHz
WAV. Everything runs locally — no cloud services, no external APIs.

## What it does

1. Point it at a folder of `.wav` / `.mp3` / `.flac` / `.aiff` files.
2. It analyzes each track (duration, BPM via librosa, RMS envelope) — results
   are cached, so analysis runs exactly once per file.
3. Drag-and-drop to set the mix order, audition tracks inline, correct BPM
   detections (`×2` / `÷2` quick-fix buttons for half/double-time errors),
   and pick an output BPM (pre-filled with the median of your tracks).
4. Click **Render**: each track is pitch-preserving time-stretched to the
   output BPM (rubberband), gain-matched to −18 LUFS, joined with equal-power
   crossfades anchored where the outgoing track's energy is already decaying,
   then the whole mix is mastered to −14 LUFS integrated with a −1 dBTP
   true-peak ceiling and written into the source folder.

## Setup (macOS)

```sh
# 1. The rubberband CLI is required for time-stretching
brew install rubberband

# 2. Python dependencies
cd track_stitcher
pip install -r requirements.txt
```

## Launch

```sh
streamlit run app.py
```

The last-used folder path is remembered across sessions
(`~/.track_stitcher_config.json`).

## Notes

- BPM in the filename (e.g. `raga_72bpm.wav`, `72 bpm`) overrides detection
  and is badged "BPM from filename"; the detected value stays visible for
  reference.
- If detection fails on a track, the row is flagged and Render stays disabled
  until you set a BPM manually.
- Stretch percentages are color-coded (amber beyond ±8%, red beyond ±15%) —
  large stretches degrade sustained/ambient textures.
- Stretching is skipped when a track is already within ±0.5% of the output
  BPM. Mono files are converted to stereo. Single-track folders skip
  crossfading. Transitions involving tracks shorter than 2× the crossfade
  length are automatically shortened (noted in the render log).
- The render log (expandable after a render) lists the stretch ratio, gain,
  and fade anchor chosen for every track.

## Files

```
app.py            # Streamlit UI
audio_engine.py   # All DSP (testable, UI-independent)
tests/            # Engine tests (pytest)
```
