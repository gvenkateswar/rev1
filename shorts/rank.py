"""Combine audio + video scores into a ranked list of candidate clips.

Pipeline:
  1. Build a per-second combined score.
  2. Slide a 30s window across the timeline; window score = mean(combined).
  3. Snap each candidate's start to the nearest downbeat/scene-cut if one is
     close, so cuts feel intentional instead of mid-phrase.
  4. Greedy non-max suppression: pick the top window, blank out a +/-30s
     neighborhood, repeat until we have N picks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .audio import AudioFeatures
from .video import VideoFeatures


@dataclass
class Clip:
    start: float        # seconds
    end: float          # seconds
    score: float        # combined score, higher = better
    reason: str         # short human-readable explanation


def _nearest(values: np.ndarray, target: float, max_drift: float) -> float | None:
    """Return the closest value within max_drift, or None."""
    if values.size == 0:
        return None
    idx = int(np.argmin(np.abs(values - target)))
    if abs(values[idx] - target) <= max_drift:
        return float(values[idx])
    return None


def rank_clips(
    audio: AudioFeatures,
    video: VideoFeatures,
    n_clips: int = 5,
    clip_len: float = 30.0,
    audio_weight: float = 0.65,
    video_weight: float = 0.35,
    snap_drift: float = 1.5,
) -> list[Clip]:
    """Return up to n_clips non-overlapping Clip picks, best-first."""
    # Align grids (they should both be 1Hz already, but be defensive).
    t = audio.times
    v_score = np.interp(t, video.times, video.score) if video.times.size else np.zeros_like(t)
    combined = audio_weight * audio.score + video_weight * v_score

    # Sliding-window mean. For a 30s clip on a 1Hz grid, that's a 30-sample mean.
    w = int(round(clip_len))
    if len(combined) < w:
        return []
    kernel = np.ones(w) / w
    window_score = np.convolve(combined, kernel, mode="valid")
    # window_score[i] is the mean over seconds [i, i + w)
    start_times = t[: len(window_score)]

    order = np.argsort(-window_score)  # highest first

    picks: list[Clip] = []
    # Suppression mask in window-index space: True = still eligible.
    eligible = np.ones(len(window_score), dtype=bool)
    min_gap_idx = w  # don't let picks overlap

    for idx in order:
        if len(picks) >= n_clips:
            break
        if not eligible[idx]:
            continue

        raw_start = float(start_times[idx])

        # Snap to a nearby downbeat or scene-cut for a cleaner entrance.
        snapped_start = raw_start
        snap_reasons = []
        beat_snap = _nearest(audio.downbeats, raw_start, snap_drift)
        scene_snap = _nearest(video.scene_start_times, raw_start, snap_drift)
        # Prefer scene cuts (stronger visual anchor); fall back to downbeat.
        if scene_snap is not None:
            snapped_start = scene_snap
            snap_reasons.append("scene cut")
        elif beat_snap is not None:
            snapped_start = beat_snap
            snap_reasons.append("downbeat")

        # Build a short "why" string based on which component dominates.
        a_mean = float(audio.score[idx : idx + w].mean())
        v_mean = float(v_score[idx : idx + w].mean())
        dominant = []
        if a_mean > 0.55:
            dominant.append("high audio energy")
        if v_mean > 0.55:
            dominant.append("dynamic visuals")
        if not dominant:
            dominant.append("balanced interest")
        reason = ", ".join(dominant + snap_reasons)

        picks.append(Clip(
            start=snapped_start,
            end=snapped_start + clip_len,
            score=float(window_score[idx]),
            reason=reason,
        ))

        # Suppress a neighborhood so the next pick doesn't overlap.
        lo = max(0, idx - min_gap_idx)
        hi = min(len(eligible), idx + min_gap_idx + 1)
        eligible[lo:hi] = False

    # Return in time order -- easier to review.
    picks.sort(key=lambda c: c.start)
    return picks
