#!/usr/bin/env python3
"""
Visual analysis for clip ordering.

Samples a handful of frames from each clip and summarizes its look:
color palette (hue/saturation histogram), brightness, and motion. The
recommended order chains clips greedily so that visually similar clips
sit next to each other — which is exactly what makes crossfades and
dissolves read as intentional instead of jarring — starting from the
calmest/darkest clip (a natural opener) unless an anchor says otherwise.
"""

from __future__ import annotations

import random
from typing import Optional

import cv2
import numpy as np

# Feature weights for the pairwise distance between clips.
W_COLOR = 0.55       # palette similarity dominates: it's what the eye sees in a blend
W_BRIGHTNESS = 0.25  # avoid dark->blown-out jumps
W_MOTION = 0.20      # avoid frantic->static jumps

N_SAMPLE_FRAMES = 9
SAMPLE_WIDTH = 160   # analysis frames are downscaled to this width


def extract_features(path: str) -> dict:
    """Sample frames and return a feature dict for one clip."""
    cap = cv2.VideoCapture(path)
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            raise ValueError(f"Could not read frames from {path}")
        indices = np.linspace(0, max(total - 2, 0), N_SAMPLE_FRAMES).astype(int)

        frames = []
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, frame = cap.read()
            if not ok:
                continue
            h = max(int(frame.shape[0] * SAMPLE_WIDTH / frame.shape[1]), 1)
            frames.append(cv2.resize(frame, (SAMPLE_WIDTH, h)))
        if not frames:
            raise ValueError(f"Could not read frames from {path}")
    finally:
        cap.release()

    # Color: 2D hue x saturation histogram, averaged over sampled frames.
    hist = np.zeros((16, 8), dtype=np.float64)
    brightness = []
    for f in frames:
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        h = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
        hist += h.astype(np.float64)
        brightness.append(float(hsv[..., 2].mean()) / 255.0)
    hist /= hist.sum() or 1.0

    # Motion: mean absolute difference between consecutive sampled frames.
    # Coarse (the samples are seconds apart) but enough to tell a locked-off
    # shot from a handheld run-and-gun clip.
    diffs = []
    for a, b in zip(frames, frames[1:]):
        if a.shape == b.shape:
            ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float32)
            gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32)
            diffs.append(float(np.abs(ga - gb).mean()) / 255.0)

    return {
        "hist": hist.flatten(),
        "brightness": float(np.mean(brightness)),
        "motion": float(np.mean(diffs)) if diffs else 0.0,
    }


def clip_distance(f1: dict, f2: dict) -> float:
    """Visual distance between two clips (0 = identical look)."""
    # Bhattacharyya distance between the palette histograms.
    bc = float(np.sqrt(f1["hist"] * f2["hist"]).sum())
    color_dist = float(np.sqrt(max(1.0 - bc, 0.0)))
    return (
        W_COLOR * color_dist
        + W_BRIGHTNESS * abs(f1["brightness"] - f2["brightness"])
        + W_MOTION * abs(f1["motion"] - f2["motion"])
    )


def recommend_order(
    ids: list,
    features: dict,
    first: Optional[object] = None,
    last: Optional[object] = None,
) -> list:
    """Greedy visual-flow ordering of `ids` (keys into `features`).

    Anchors are honored: `first`/`last` stay pinned and the chain is built
    between them. Without a first anchor the chain opens on the calmest,
    darkest clip — the conventional "ease the viewer in" opener.
    """
    ids = list(ids)
    if len(ids) <= 2:
        return ids

    remaining = [i for i in ids if i not in (first, last)]

    if first is not None:
        current = first
    else:
        # Calm opener: lowest brightness+motion blend.
        def opener_score(i):
            f = features[i]
            return 0.5 * f["brightness"] + 0.5 * f["motion"]
        current = min(remaining, key=opener_score)
        remaining.remove(current)

    chain = [current]
    while remaining:
        nxt = min(remaining, key=lambda i: clip_distance(features[current], features[i]))
        remaining.remove(nxt)
        chain.append(nxt)
        current = nxt

    if last is not None:
        chain.append(last)
    return chain


def shuffle_order(
    ids: list,
    first: Optional[object] = None,
    last: Optional[object] = None,
    rng: Optional[random.Random] = None,
) -> list:
    """Random order that keeps the first/last anchors pinned."""
    rng = rng or random.Random()
    middle = [i for i in ids if i not in (first, last)]
    rng.shuffle(middle)
    out = list(middle)
    if first is not None:
        out.insert(0, first)
    if last is not None:
        out.append(last)
    return out


def thumbnail_png(path: str, height: int = 90) -> Optional[bytes]:
    """Grab a mid-clip frame as PNG bytes for the GUI clip list."""
    cap = cv2.VideoCapture(path)
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total > 1:
            cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
        ok, frame = cap.read()
        if not ok:
            return None
        w = max(int(frame.shape[1] * height / frame.shape[0]), 1)
        frame = cv2.resize(frame, (w, height))
        ok, buf = cv2.imencode(".png", frame)
        return buf.tobytes() if ok else None
    finally:
        cap.release()
