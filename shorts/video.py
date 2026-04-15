"""Visual scoring.

Two signals, computed on the low-res proxy:

  1. Scene cuts per window  -- more cuts = more visually dynamic.
  2. Per-frame motion (mean absolute diff between consecutive frames) --
     raw movement energy on screen.

Also exposed: `scene_start_times` so the ranker can snap clip starts to the
first frame of a shot instead of chopping mid-shot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class VideoFeatures:
    times: np.ndarray           # 1Hz grid (seconds)
    score: np.ndarray           # 0..1-ish per-second interestingness
    scene_start_times: np.ndarray  # seconds where a new scene begins
    duration: float


def _detect_scenes(proxy_path: Path) -> list[tuple[float, float]]:
    """Return list of (start_sec, end_sec) scene intervals."""
    from scenedetect import open_video, SceneManager, ContentDetector

    video = open_video(str(proxy_path))
    manager = SceneManager()
    # threshold=27 is the PySceneDetect default -- works well for music videos
    # which tend to have distinct cuts.
    manager.add_detector(ContentDetector(threshold=27.0))
    manager.detect_scenes(video=video, show_progress=False)
    scenes = manager.get_scene_list()
    return [(s.get_seconds(), e.get_seconds()) for s, e in scenes]


def _motion_per_second(proxy_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Mean absolute frame-difference, aggregated to 1Hz."""
    import cv2

    cap = cv2.VideoCapture(str(proxy_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 5.0
    prev_gray = None
    times: list[float] = []
    diffs: list[float] = []
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            d = float(np.mean(cv2.absdiff(gray, prev_gray)))
            times.append(frame_idx / fps)
            diffs.append(d)
        prev_gray = gray
        frame_idx += 1
    cap.release()

    if not times:
        return np.array([]), np.array([])
    return np.array(times), np.array(diffs)


def _normalize(x: np.ndarray) -> np.ndarray:
    if x.size == 0:
        return x
    lo, hi = np.percentile(x, 2), np.percentile(x, 98)
    if hi - lo < 1e-9:
        return np.zeros_like(x)
    return np.clip((x - lo) / (hi - lo), 0.0, 1.0)


def analyze_video(proxy_path: Path, duration: float) -> VideoFeatures:
    """Return per-second visual interestingness plus scene boundaries."""
    scenes = _detect_scenes(proxy_path)
    scene_starts = np.array([s for s, _ in scenes]) if scenes else np.array([])

    motion_t, motion_v = _motion_per_second(proxy_path)

    grid = np.arange(0.0, duration, 1.0)

    # Motion resampled to 1Hz.
    if motion_t.size:
        motion_1hz = np.interp(grid, motion_t, motion_v)
    else:
        motion_1hz = np.zeros_like(grid)

    # Scene-cut density: number of cuts within a +/-5s window.
    cut_density = np.zeros_like(grid)
    for t in scene_starts:
        mask = (grid >= t - 5) & (grid <= t + 5)
        cut_density[mask] += 1

    motion_n = _normalize(motion_1hz)
    cuts_n = _normalize(cut_density)

    score = 0.6 * motion_n + 0.4 * cuts_n

    return VideoFeatures(
        times=grid,
        score=score,
        scene_start_times=scene_starts,
        duration=duration,
    )
