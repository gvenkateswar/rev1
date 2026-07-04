#!/usr/bin/env python3
"""
Visual analysis for clip ordering.

Samples a handful of frames from each clip and summarizes its look:
color palette (hue/saturation histogram), brightness, and motion. The
recommended order follows two rules: near-duplicate clips (slight
variations of the same shot) are spread as far apart as possible and
never adjacent, and the fastest-moving third of clips is interspersed
evenly between the calmer ones — with a calm clip opening the sequence
unless an anchor says otherwise.
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


def _calmness(features: dict, i) -> float:
    """Lower = calmer/darker — the clip that eases the viewer in."""
    return 0.5 * features[i]["brightness"] + 0.5 * features[i]["motion"]


def _cluster_variations(ids: list, features: dict) -> dict:
    """Group near-duplicate clips (slight variations of the same shot).

    Returns {id: cluster_label}. Two clips are variations when their
    visual distance is far below the typical pairwise distance in the
    set (relative threshold, with absolute floor/ceiling so it behaves
    on both very uniform and very diverse folders).
    """
    labels = {i: i for i in ids}
    if len(ids) < 2:
        return labels

    def find(i):
        while labels[i] != i:
            labels[i] = labels[labels[i]]
            i = labels[i]
        return i

    pairs = [
        (clip_distance(features[a], features[b]), a, b)
        for k, a in enumerate(ids) for b in ids[k + 1:]
    ]
    dists = sorted(d for d, _, _ in pairs)
    median = dists[len(dists) // 2]
    threshold = min(max(0.05, 0.35 * median), 0.30)

    for d, a, b in pairs:
        if d < threshold:
            labels[find(a)] = find(b)
    return {i: find(i) for i in ids}


def _spread_deal(groups: list[list], avoid_cluster_of=None, cluster=None) -> list:
    """Deal members round-robin across groups — members of the same group
    end up as far apart as the group count allows."""
    groups = [list(g) for g in groups if g]
    if avoid_cluster_of is not None and cluster and len(groups) > 1:
        # Don't open with a variation of the anchored-first clip.
        if cluster.get(groups[0][0]) == cluster.get(avoid_cluster_of):
            groups.append(groups.pop(0))
    out = []
    while any(groups):
        for g in groups:
            if g:
                out.append(g.pop(0))
    return out


def _adjacency_violations(seq: list, cluster: dict) -> int:
    return sum(1 for a, b in zip(seq, seq[1:]) if cluster[a] == cluster[b])


def _repair_adjacency(seq: list, cluster: dict, n_fixed_head: int,
                      n_fixed_tail: int) -> list:
    """Swap clips until no two same-cluster variations sit next to each
    other (or no swap improves things — only possible when variations
    outnumber everything else). Anchored ends stay put."""
    seq = list(seq)
    lo, hi = n_fixed_head, len(seq) - n_fixed_tail
    improved = True
    while improved and _adjacency_violations(seq, cluster) > 0:
        improved = False
        current = _adjacency_violations(seq, cluster)
        for i in range(lo, hi):
            for j in range(i + 1, hi):
                seq[i], seq[j] = seq[j], seq[i]
                if _adjacency_violations(seq, cluster) < current:
                    improved = True
                    break
                seq[i], seq[j] = seq[j], seq[i]
            if improved:
                break
    return seq


def recommend_order(
    ids: list,
    features: dict,
    first: Optional[object] = None,
    last: Optional[object] = None,
) -> list:
    """Visual ordering of `ids` (keys into `features`) built on two rules:

    1. **Variations never touch.** Near-duplicate clips (slight
       variations of the same shot) are detected by visual distance and
       spread as far apart as possible — never adjacent.
    2. **Fast clips are punctuation.** The fastest third of clips is
       interspersed evenly between the calmer ones instead of clumping,
       and the sequence opens on a calm clip.

    Anchors are honored: `first`/`last` stay pinned, and a variation of
    the first anchor won't directly follow it.
    """
    ids = list(ids)
    if len(ids) <= 2:
        return ids

    middle = [i for i in ids if i not in (first, last)]
    cluster = _cluster_variations(
        middle + [a for a in (first, last) if a is not None], features,
    )

    n_dyn = max(1, len(middle) // 3) if len(middle) > 2 else 0
    by_motion = sorted(middle, key=lambda i: features[i]["motion"], reverse=True)
    dynamic = list(by_motion[:n_dyn])
    calm = [i for i in middle if i not in set(dynamic)]
    if not calm:
        calm, dynamic = dynamic, []

    # Backbone: calm clips dealt round-robin across variation clusters,
    # calmest clips leading, so same-shot variations sit maximally apart.
    calm_groups: dict = {}
    for i in sorted(calm, key=lambda i: _calmness(features, i)):
        calm_groups.setdefault(cluster[i], []).append(i)
    groups = sorted(calm_groups.values(), key=len, reverse=True)
    backbone = _spread_deal(groups, avoid_cluster_of=first, cluster=cluster)

    # Intersperse the dynamic clips at evenly spaced marks, preferring the
    # candidate most visually different from its neighbor (and never a
    # variation of it, when avoidable).
    m = len(dynamic)
    marks = [(k + 1) * len(backbone) / (m + 1) for k in range(m)]
    dyn_left = list(dynamic)
    chain: list = []
    mi = 0
    for i, c in enumerate(backbone):
        chain.append(c)
        while mi < m and (i + 1) >= marks[mi] and dyn_left:
            allowed = [d for d in dyn_left if cluster[d] != cluster[c]] or dyn_left
            pick = max(allowed,
                       key=lambda d: clip_distance(features[c], features[d]))
            dyn_left.remove(pick)
            chain.append(pick)
            mi += 1
    chain.extend(dyn_left)

    if first is not None:
        chain.insert(0, first)
    if last is not None:
        chain.append(last)

    return _repair_adjacency(
        chain, cluster,
        n_fixed_head=1 if first is not None else 0,
        n_fixed_tail=1 if last is not None else 0,
    )


# Speed suggestions, gentlest to strongest. A clip must be meaningfully
# faster than the set's typical motion (and above an absolute floor, so a
# folder of all-calm footage never triggers) before a slow-down is suggested.
SPEED_LADDER = [
    (3.0, 0.75),   # motion >= 3x the median -> 0.75x
    (2.0, 0.8),
    (1.5, 0.9),
]
MOTION_FLOOR = 0.02


def recommend_speeds(ids: list, features: dict) -> dict:
    """Suggest a slow-down for clips that move much faster than the rest.

    Returns {id: speed} for every id (1.0 = leave alone). Slow-downs stay
    in the 0.75-0.9x "slight" range — taming frantic footage for an
    ambient edit, not turning it into slow motion.
    """
    ids = list(ids)
    if not ids:
        return {}
    motions = sorted(features[i]["motion"] for i in ids)
    median = motions[len(motions) // 2]
    baseline = max(median, 1e-6)

    out = {}
    for i in ids:
        motion = features[i]["motion"]
        speed = 1.0
        if motion > max(1.5 * baseline, MOTION_FLOOR):
            ratio = motion / baseline
            for threshold, s in SPEED_LADDER:
                if ratio >= threshold:
                    speed = s
                    break
        out[i] = speed
    return out


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
