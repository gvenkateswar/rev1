"""Salience-based melody tracking for accompanied singing.

YIN answers "what is the pitch of this instant" — and on a mixture of voice,
harmonium and tanpura the honest answer changes owner every few frames, which
is exactly the fragmented, hopping contour the analysis view exposes. What a
listener does instead is follow a LINE: the melody is the trajectory that is
strong *and continuous*, not the strongest instant.

This module does the listener's version, the way melody extractors in music
information retrieval do (Salamon & Gómez's Melodia is the reference point):

1. **Salience.** Short-time spectra are sampled at the first harmonics of
   every candidate f0 on a log grid, so a pitch scores by the energy of its
   whole harmonic stack — a voice with strong harmonics outscores a drone
   fundamental even when the drone's own bin is hotter.
2. **Continuity (Viterbi).** The best path through the salience map is found
   with a per-step cost on pitch movement, so the track rides through a few
   frames where the harmonium is momentarily louder instead of leaping to it
   and back. The transition cost uses the classic distance-transform trick,
   which keeps the whole pass O(frames x candidates).
3. **Voicing.** Frames whose chosen candidate is weak relative to the frame's
   own spectral energy are unvoiced after the fact.

Returns the same :class:`~music_lesson.pitch.PitchTrack` the YIN tracker
returns, so everything downstream — tonic, swaras, regions, the chart — works
unchanged with either tracker.
"""
from __future__ import annotations

import numpy as np

from .pitch import PitchTrack

F0_MIN = 80.0
F0_MAX = 1000.0
BINS_PER_SEMITONE = 5
N_HARMONICS = 8
HARMONIC_DECAY = 0.85

# Movement cost per grid bin, and the cap that makes an octave leap no more
# expensive than a fifth (a real melody does occasionally leap).
_STEP_COST = 0.9
_STEP_CAP_BINS = 30 * BINS_PER_SEMITONE // 10   # ~3 semitones at full price

_CHUNK = 2048


def track_melody(
    samples: np.ndarray,
    sample_rate: int,
    hop_s: float = 0.01,
    frame_s: float = 0.064,
    min_salience: float = 0.60,
) -> PitchTrack:
    """Track the dominant melodic line of *samples*; PitchTrack out.

    *min_salience* is the voicing gate: how close the chosen candidate must
    sit to the frame's salience peak. Below it, the continuity cost is
    dragging the path through a valley and the frame is called unvoiced.
    """
    samples = np.asarray(samples, dtype=np.float64).ravel()
    hop = max(1, int(round(hop_s * sample_rate)))
    win = int(frame_s * sample_rate)
    fft_size = 1 << (win - 1).bit_length()

    if len(samples) < win:
        empty = np.zeros(0)
        return PitchTrack(empty, empty, empty, empty, hop_s, sample_rate,
                          raw_f0=empty)

    grid_hz = _candidate_grid()
    window = np.hanning(win)
    frames = np.lib.stride_tricks.sliding_window_view(samples, win)[::hop]
    n = len(frames)

    # float32 on purpose: an hour of lesson is ~360k frames x ~220 candidates,
    # and this map (plus the Viterbi backpointers) is the peak memory of the
    # whole pipeline.
    salience = np.zeros((n, len(grid_hz)), dtype=np.float32)
    rms = np.zeros(n)
    bin_hz = sample_rate / fft_size
    # Harmonic sampling positions, in (fractional) FFT bins, per candidate.
    harmonic_bins = np.outer(
        np.arange(1, N_HARMONICS + 1), grid_hz
    ) / bin_hz                                        # (H, K)
    weights = HARMONIC_DECAY ** np.arange(N_HARMONICS)
    max_bin = fft_size // 2 - 1
    lo_bins = np.clip(harmonic_bins.astype(int), 0, max_bin)
    frac = np.clip(harmonic_bins - lo_bins, 0.0, 1.0)
    hi_bins = np.clip(lo_bins + 1, 0, max_bin)
    valid = harmonic_bins < max_bin

    for lo in range(0, n, _CHUNK):
        block = frames[lo:lo + _CHUNK] * window
        rms[lo:lo + len(block)] = np.sqrt(np.mean(block ** 2, axis=1))
        mags = np.abs(np.fft.rfft(block, fft_size, axis=1))
        mags = np.log1p(mags)
        # Linear interpolation of the spectrum at every harmonic of every
        # candidate, summed with decaying weights: (T, H, K) -> (T, K).
        sampled = (
            mags[:, lo_bins] * (1.0 - frac) + mags[:, hi_bins] * frac
        ) * valid
        salience[lo:lo + len(block)] = np.tensordot(
            weights, sampled.transpose(1, 0, 2), axes=1
        )

    path = _viterbi(salience)
    f0 = grid_hz[path]

    # Voicing. On accompanied audio nearly every frame IS pitched — the drone
    # never stops — so the useful tests are: the path is actually riding a
    # salience peak (not dragged through a valley by the continuity cost),
    # and the frame is not near-silent.
    chosen = salience[np.arange(n), path]
    peak = salience.max(axis=1) + 1e-12
    rel = chosen / peak
    floor = max(np.percentile(rms, 90) * 0.05, 1e-4)
    voiced = (rel >= min_salience) & (rms > floor)

    times = np.arange(n) * hop / sample_rate + (win / 2) / sample_rate
    return PitchTrack(
        f0=np.where(voiced, f0, 0.0),
        confidence=np.clip(rel, 0.0, 1.0),
        rms=rms,
        times=times,
        hop_s=hop / sample_rate,
        sample_rate=sample_rate,
        raw_f0=f0.astype(float),
    )


def _candidate_grid() -> np.ndarray:
    n_bins = int(np.round(
        12 * BINS_PER_SEMITONE * np.log2(F0_MAX / F0_MIN)
    )) + 1
    return F0_MIN * 2 ** (np.arange(n_bins) / (12 * BINS_PER_SEMITONE))


def _viterbi(salience: np.ndarray) -> np.ndarray:
    """Max-score path with capped-linear movement cost, O(T·K).

    The per-frame minimization min_j(cost[j] + w·|i-j|) is a 1D distance
    transform. Under a *linear* cost it splits into a prefix problem
    (min over j<=i of cost[j] - w·j, plus w·i) and the mirrored suffix
    problem, both of which are `minimum.accumulate` — so each frame is a
    handful of vectorized passes, no Python loop over candidates. The cap is
    one extra comparison against the frame's global minimum plus the cap
    price.
    """
    n, k = salience.shape
    norm = salience / (salience.max(axis=1, keepdims=True) + 1e-12)
    emission = -np.log(norm + 1e-6, dtype=np.float64)

    cost = emission[0].copy()
    back = np.zeros((n, k), dtype=np.int16)     # k is a few hundred: it fits
    idx = np.arange(k)
    w = _STEP_COST
    cap = _STEP_COST * _STEP_CAP_BINS

    for t in range(1, n):
        # Prefix half: best origin at-or-left of each bin.
        a = cost - w * idx
        run = np.minimum.accumulate(a)
        fw_origin = np.maximum.accumulate(np.where(a <= run, idx, -1))
        fw = run + w * idx
        # Suffix half, as the prefix problem on the reversed array.
        b = (cost + w * idx)[::-1]
        run = np.minimum.accumulate(b)
        rev_origin = np.maximum.accumulate(np.where(b <= run, idx, -1))
        bw_origin = (k - 1) - rev_origin[::-1]
        bw = run[::-1] - w * idx

        take_fw = fw <= bw
        best = np.where(take_fw, fw, bw)
        origin = np.where(take_fw, fw_origin, bw_origin)
        # Capped far jump: never dearer than the global best plus the cap.
        far = cost.min() + cap
        jump = far < best
        best[jump] = far
        origin[jump] = int(cost.argmin())

        back[t] = origin
        cost = best + emission[t]

    path = np.zeros(n, dtype=np.int32)
    path[-1] = int(cost.argmin())
    for t in range(n - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    return path
