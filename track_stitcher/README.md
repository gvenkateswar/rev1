# Track Stitcher

A local Streamlit app that combines a folder of ambient music tracks into one
continuous, beat-matched, crossfaded mix, exported as a single 24-bit / 48 kHz
WAV. Everything runs locally — no cloud services, no external APIs.

## What it does

1. Point it at a folder of `.wav` / `.mp3` / `.flac` / `.aiff` / `.m4a`
   files (m4a/AAC decodes via CoreAudio on macOS — no extra install needed).
2. It analyzes each track (duration, BPM via librosa, RMS envelope) — results
   are cached, so analysis runs exactly once per file.
3. Set the mix order with the ▲▼ buttons on each track card — or let
   **✨ Recommend order** arrange the tracks so similar-sounding ones (by
   timbre fingerprint) never sit back to back, or **🎲 Shuffle** for a random
   order. Both respect the optional "anchor first/last track" checkboxes.
   Deselect any tracks you want to leave out, audition tracks inline, correct BPM
   detections (`×2` / `÷2` quick-fix buttons), and pick an output BPM
   (pre-filled with the median of your tracks). Detections that land at half
   or double the folder's median tempo are auto-corrected to the right
   octave (badged in the UI; filename BPMs and manual edits are never
   overridden).
4. Every crossover preview renders automatically (a progress counter shows
   "Loaded k / N"); open any transition in **Transitions — preview & manual
   alignment** to hear it and see both tracks' waveforms stacked with beat
   ticks, zoom in for precision, and adjust two independent controls: where
   the fade starts in the outgoing track, and where the incoming track
   enters (skip its intro). Both are used in the final render. Previews use
   short segments around the transition, so they're fast even on long tracks.
5. Optional: **Fade out the ending** — smoothly fades the last seconds of
   the mix to silence, for final tracks that end abruptly (length
   configurable, default 15 s).
6. Click **Render**: each track is pitch-preserving time-stretched to the
   output BPM (rubberband), gain-matched to −18 LUFS, joined with equal-power
   crossfades anchored where the outgoing track's energy is already decaying
   and beat-aligned so both tracks' beats coincide exactly through the
   overlap, then the whole mix is mastered to −14 LUFS integrated with a
   −1 dBTP true-peak ceiling and written into the source folder.

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

### Troubleshooting: `ModuleNotFoundError` on launch

Macs often have several Pythons (Homebrew, python.org, Xcode). The
dependencies must go into the **same** Python that the `streamlit` command
runs from. Check which one that is with `pip --version` — if its path matches
the `site-packages` path shown in the error traceback, a plain
`pip install -r requirements.txt` from this directory is correct. (Don't
assume `python3 -m pip` is right: on Homebrew systems `python3` is often a
different, PEP 668-locked interpreter than the one running streamlit.)

## Notes

- BPM in the filename (e.g. `raga_72bpm.wav`, `72 bpm`) overrides detection
  and is badged "BPM from filename"; the detected value stays visible for
  reference.
- If detection fails on a track, the row is flagged and Render stays disabled
  until you set a BPM manually.
- Stretch percentages are color-coded (amber beyond ±8%, red beyond ±15%) —
  large stretches degrade sustained/ambient textures.
- Tracks with a reliable beat grid are **beat-mapped**: rubberband warps
  them so every detected beat lands exactly on the output tempo grid (like
  DAW warp markers), correcting tempo drift *within* a track — with the
  grid extrapolated at the local tempo through quiet intros/outros where
  the tracker loses the pulse. Beat positions are refined to a few ms via
  onset-peak interpolation. Tracks without a trustworthy grid fall back to
  a uniform stretch at the tempo measured from their beats. Mono files are
  converted to stereo. Single-track folders skip crossfading. Transitions
  involving tracks shorter than 2× the crossfade length are automatically
  shortened (noted in the render log).
- The render log (expandable after a render) lists the stretch ratio, gain,
  and fade anchor chosen for every track.

## Files

```
app.py            # Streamlit UI
audio_engine.py   # All DSP (testable, UI-independent)
tests/            # Engine tests (pytest)
```
