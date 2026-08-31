"""Monophonic pitch tracking (YIN) in pure NumPy.

Why not librosa? The rest of this repo keeps its dependency list short and
pinned (see `streamlit_tool/requirements.txt` for the numpy<2 saga), and pitch
tracking is the one piece we genuinely need from a DSP library. YIN is ~80
lines of array math, so we own it here instead of pulling a large dependency
that would re-open the numpy pin question.

The tracker returns one estimate per hop:

    f0[i]          fundamental in Hz (0.0 where unvoiced)
    confidence[i]  1 - YIN's normalized difference at the chosen lag
    rms[i]         frame energy, used to tell a held note from a tanpura drone

Everything downstream (tonic detection, swara segmentation, sung-vs-spoken
classification) works off this one track, so it is computed once per file.

Reference: de Cheveigné & Kawahara (2002), "YIN, a fundamental frequency
estimator for speech and music".
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np

# A trained voice plus a tanpura sits comfortably inside 60-1000 Hz. The bounds
# are deliberately generous: mandra-saptak Sa for a male vocalist can sit near
# 110 Hz and taar-saptak Sa for a female vocalist near 600 Hz.
F0_MIN = 60.0
F0_MAX = 1000.0

# YIN's absolute threshold. Below this, the lag is accepted as periodic.
YIN_THRESHOLD = 0.15

# Frames per FFT batch. Bounds peak memory on hour-long lessons: a 90-minute
# recording at a 10 ms hop is ~540k frames, which we refuse to hold at once.
_CHUNK = 1024


@dataclass
class PitchTrack:
    """Frame-synchronous pitch, confidence and energy for one recording."""

    f0: np.ndarray           # Hz, 0.0 where unvoiced
    confidence: np.ndarray   # 0..1
    rms: np.ndarray          # linear RMS per frame
    times: np.ndarray        # frame centre, seconds
    hop_s: float
    sample_rate: int

    def __len__(self) -> int:
        return len(self.f0)

    @property
    def voiced(self) -> np.ndarray:
        return self.f0 > 0

    def index_at(self, t: float) -> int:
        """Frame index nearest to time *t* (clamped to the track)."""
        if len(self.times) == 0:
            return 0
        return int(np.clip(round(t / self.hop_s), 0, len(self.times) - 1))

    def slice(self, start: float, end: float) -> "PitchTrack":
        """The sub-track covering [start, end] seconds."""
        a = self.index_at(start)
        b = max(a + 1, self.index_at(end) + 1)
        return PitchTrack(
            f0=self.f0[a:b], confidence=self.confidence[a:b], rms=self.rms[a:b],
            times=self.times[a:b], hop_s=self.hop_s, sample_rate=self.sample_rate,
        )


def track_pitch(
    samples: np.ndarray,
    sample_rate: int,
    hop_s: float = 0.01,
    frame_s: float = 0.064,
    f0_min: float = F0_MIN,
    f0_max: float = F0_MAX,
    threshold: float = YIN_THRESHOLD,
    min_confidence: float = 0.55,
) -> PitchTrack:
    """Run YIN over *samples* and return a :class:`PitchTrack`.

    *frame_s* is the analysis window; the read buffer is that plus the longest
    lag we search, so a 64 ms window at a 60 Hz floor reads ~81 ms per frame.
    """
    samples = np.asarray(samples, dtype=np.float64).ravel()
    tau_min = max(2, int(sample_rate / f0_max))
    tau_max = min(int(sample_rate / f0_min) + 1, max(3, len(samples) // 2))
    win = max(int(frame_s * sample_rate), 2 * tau_max)
    buf = win + tau_max
    hop = max(1, int(round(hop_s * sample_rate)))

    if len(samples) < buf or tau_max <= tau_min:
        empty = np.zeros(0)
        return PitchTrack(empty, empty, empty, empty, hop_s, sample_rate)

    frames = np.lib.stride_tricks.sliding_window_view(samples, buf)[::hop]
    n = len(frames)
    fft_size = 1 << int(buf - 1).bit_length()

    f0 = np.zeros(n)
    conf = np.zeros(n)
    rms = np.zeros(n)

    for lo in range(0, n, _CHUNK):
        block = np.array(frames[lo:lo + _CHUNK], dtype=np.float64)
        block -= block.mean(axis=1, keepdims=True)   # kill DC before differencing
        rms[lo:lo + len(block)] = np.sqrt(np.mean(block[:, :win] ** 2, axis=1))

        dprime = _cumulative_mean_normalized_difference(block, win, tau_max, fft_size)
        lag, quality = _pick_lag(dprime, tau_min, tau_max, threshold)

        block_f0 = np.where(lag > 0, sample_rate / np.maximum(lag, 1e-9), 0.0)
        block_conf = np.clip(1.0 - quality, 0.0, 1.0)
        voiced = (lag > 0) & (block_conf >= min_confidence)
        f0[lo:lo + len(block)] = np.where(voiced, block_f0, 0.0)
        conf[lo:lo + len(block)] = block_conf

    times = np.arange(n) * hop / sample_rate + (win / 2) / sample_rate
    return PitchTrack(f0, conf, rms, times, hop / sample_rate, sample_rate)


# --------------------------------------------------------------------------- #
# YIN internals
# --------------------------------------------------------------------------- #
def _cumulative_mean_normalized_difference(
    block: np.ndarray, win: int, tau_max: int, fft_size: int
) -> np.ndarray:
    """YIN steps 1-3 for a block of frames: d(tau), then d'(tau).

    d(tau) = sum_j (x[j] - x[j+tau])^2 is expanded into two running-power terms
    and one correlation, so the whole block costs two FFTs instead of a loop
    over lags.
    """
    power = np.concatenate(
        [np.zeros((len(block), 1)), np.cumsum(block ** 2, axis=1)], axis=1
    )
    head = power[:, win:win + 1] - power[:, :1]                     # sum x[0:win]^2
    tail = power[:, win:win + tau_max + 1] - power[:, :tau_max + 1]  # sliding window

    spec_win = np.fft.rfft(block[:, :win], fft_size, axis=1)
    spec_all = np.fft.rfft(block, fft_size, axis=1)
    corr = np.fft.irfft(np.conj(spec_win) * spec_all, fft_size, axis=1)
    corr = corr[:, :tau_max + 1]

    diff = np.maximum(head + tail - 2.0 * corr, 0.0)

    # Cumulative mean normalization: d'(0) = 1, else d(tau) / mean(d(1..tau)).
    running = np.cumsum(diff[:, 1:], axis=1)
    denom = running / np.arange(1, tau_max + 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        dprime = np.where(denom > 0, diff[:, 1:] / denom, 1.0)
    return np.concatenate([np.ones((len(block), 1)), dprime], axis=1)


def _pick_lag(
    dprime: np.ndarray, tau_min: int, tau_max: int, threshold: float
) -> tuple[np.ndarray, np.ndarray]:
    """Absolute-threshold lag selection with parabolic refinement.

    Returns (lag_in_samples, d'(lag)); lag is 0.0 for frames with no periodic
    candidate at all.
    """
    window = dprime[:, tau_min:tau_max + 1]
    below = window < threshold
    has_hit = below.any(axis=1)
    first = np.argmax(below, axis=1)                 # first True, else 0
    # Where nothing crossed the threshold, fall back to the global minimum:
    # noisy but harmless, because the confidence gate rejects it anyway.
    idx = np.where(has_hit, first, np.argmin(window, axis=1))

    # YIN wants the local minimum, not merely the first dip below threshold.
    # Descend while the next lag is still lower (a bounded, vectorized walk).
    rows = np.arange(len(dprime))
    for _ in range(32):
        nxt = np.minimum(idx + 1, window.shape[1] - 1)
        descending = (nxt != idx) & (window[rows, nxt] < window[rows, idx])
        if not descending.any():
            break
        idx = np.where(descending, nxt, idx)

    tau = idx + tau_min
    tau = _guard_subharmonic(dprime, tau, tau_min, threshold, rows)
    quality = dprime[rows, tau]

    # Parabolic interpolation over the three points around the minimum, so the
    # estimate is not quantized to whole samples (worth ~10 cents at 400 Hz).
    left = dprime[rows, np.maximum(tau - 1, 0)]
    right = dprime[rows, np.minimum(tau + 1, tau_max)]
    denom = left + right - 2.0 * quality
    with np.errstate(divide="ignore", invalid="ignore"):
        shift = np.where(np.abs(denom) > 1e-12, 0.5 * (left - right) / denom, 0.0)
    shift = np.clip(np.nan_to_num(shift), -1.0, 1.0)

    lag = np.where(np.isfinite(quality), tau + shift, 0.0)
    return lag, np.nan_to_num(quality, nan=1.0)


def _guard_subharmonic(
    dprime: np.ndarray, tau: np.ndarray, tau_min: int, threshold: float,
    rows: np.ndarray,
) -> np.ndarray:
    """Prefer tau/2 or tau/3 when they are *also* clearly periodic.

    A voice singing over a tanpura is two periodic sounds at a simple ratio, so
    the mixture has a true period at their common subharmonic and YIN is right
    to find it — but we want the voice, not the mixture. If a half or third of
    the chosen lag also passes the threshold, that shorter lag is the melody.
    Requiring the full threshold (not a relaxed one) keeps this from inventing
    octave-up errors on ordinary speech.
    """
    for divisor in (2, 3):
        candidate = np.maximum(np.round(tau / divisor).astype(int), tau_min)
        take = (candidate < tau) & (dprime[rows, candidate] < threshold)
        tau = np.where(take, candidate, tau)
    return tau


# --------------------------------------------------------------------------- #
# Pitch helpers
# --------------------------------------------------------------------------- #
def hz_to_cents(f0: np.ndarray | float, reference_hz: float) -> np.ndarray:
    """Cents above *reference_hz*. Unvoiced (0 Hz) frames come back as NaN."""
    f0 = np.asarray(f0, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        cents = 1200.0 * np.log2(np.where(f0 > 0, f0, np.nan) / reference_hz)
    return cents


def cents_to_hz(cents: float, reference_hz: float) -> float:
    return reference_hz * (2.0 ** (cents / 1200.0))


def median_filter(values: np.ndarray, size: int) -> np.ndarray:
    """NaN-aware median filter; used to smooth octave jumps out of the track."""
    values = np.asarray(values, dtype=np.float64)
    if size <= 1 or len(values) == 0:
        return values.copy()
    half = size // 2
    padded = np.pad(values, half, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, 2 * half + 1)
    with warnings.catch_warnings():
        # An all-unvoiced window is normal (silence); NaN is the right answer.
        warnings.simplefilter("ignore", RuntimeWarning)
        out = np.nanmedian(windows, axis=1)
    return out[:len(values)]
