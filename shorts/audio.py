"""Audio scoring.

We compute a per-second "interestingness" signal intended to spike on
choruses, drops, and other high-energy moments. Three components:

  1. RMS energy  -- loud = more likely to be the hook.
  2. Onset strength  -- busy/percussive = more dynamic.
  3. "Lift"  -- current window is loud AND the preceding ~6s was quieter.
                This catches the classic quiet-then-drop structure that a lot
                of music-video highlight moments sit on.

We also return beat times so the ranker can snap clip starts to a downbeat
instead of chopping mid-phrase.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class AudioFeatures:
    times: np.ndarray       # shape (T,), seconds, 1Hz grid
    score: np.ndarray       # shape (T,), 0..1-ish, higher = more interesting
    beats: np.ndarray       # beat times in seconds
    downbeats: np.ndarray   # approximate downbeat times (every 4th beat)
    duration: float


def _normalize(x: np.ndarray) -> np.ndarray:
    """Robust min-max to [0, 1] using 2nd/98th percentiles to ignore outliers."""
    if x.size == 0:
        return x
    lo, hi = np.percentile(x, 2), np.percentile(x, 98)
    if hi - lo < 1e-9:
        return np.zeros_like(x)
    return np.clip((x - lo) / (hi - lo), 0.0, 1.0)


def analyze_audio(wav_path, sr: int = 22050) -> AudioFeatures:
    """Return a 1Hz audio-interestingness curve plus beat grid."""
    # Local import so `python -m shorts --help` works without librosa installed.
    import librosa

    y, sr = librosa.load(str(wav_path), sr=sr, mono=True)
    duration = len(y) / sr

    hop = 512
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)

    # Resample both features to a 1Hz grid for easy windowing downstream.
    frame_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    grid = np.arange(0.0, duration, 1.0)
    rms_1hz = np.interp(grid, frame_times, rms)
    # onset may be a different length than rms -- rebuild its frame times.
    onset_times = librosa.frames_to_time(np.arange(len(onset)), sr=sr, hop_length=hop)
    onset_1hz = np.interp(grid, onset_times, onset)

    rms_n = _normalize(rms_1hz)
    onset_n = _normalize(onset_1hz)

    # "Lift": how much louder the current moment is vs. the ~6s before it.
    # Positive values mark the entry into a loud section (drop/chorus).
    lookback = 6
    padded = np.concatenate([np.full(lookback, rms_n[0]), rms_n])
    prior = np.array([padded[i:i + lookback].mean() for i in range(len(rms_n))])
    lift = np.clip(rms_n - prior, 0.0, None)
    lift_n = _normalize(lift)

    score = 0.5 * rms_n + 0.3 * onset_n + 0.2 * lift_n

    # Beat tracking for cut-snapping. Keep it loose -- PLP is more forgiving
    # than beat_track on songs with tempo drift.
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop)
    beats = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop)
    # Assume 4/4 (most popular music); every 4th beat ~ downbeat.
    downbeats = beats[::4] if len(beats) else beats

    return AudioFeatures(
        times=grid,
        score=score,
        beats=beats,
        downbeats=downbeats,
        duration=duration,
    )
