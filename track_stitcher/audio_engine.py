"""Audio processing engine for Track Stitcher.

All DSP lives here, independent of the Streamlit UI, so it can be tested
headlessly. The pipeline (see `render_mix`):

    load -> time-stretch (pyrubberband, pitch-preserving)
         -> per-track loudness normalization (pyloudnorm, -18 LUFS working level)
         -> equal-power crossfades anchored on the outgoing track's energy decay
         -> final master to -14 LUFS integrated / -1 dBTP true peak
         -> 24-bit / 48 kHz WAV

Memory notes: tracks are processed strictly one at a time; only the current
track plus the already-committed mix (float32) are held. The final loudness
and true-peak measurements run blockwise so no full float64 copy of a long
mix is ever materialized.
"""

from __future__ import annotations

import math
import os
import re
import shutil
from pathlib import Path
from typing import Callable, Optional, Sequence, Union

import numpy as np
import soundfile as sf

# Heavy imports (librosa pulls in numba) are deferred where practical, but
# analysis and rendering both need librosa, so import it at module level.
import librosa
import pyloudnorm as pyln

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_RATE = 48000                 # common rate everything is resampled to
WORKING_LUFS = -18.0                # per-track gain-match level before mixing
TARGET_LUFS = -14.0                 # final integrated loudness of the mix
TRUE_PEAK_CEILING_DBTP = -1.0       # final true-peak ceiling
# Skip stretching only when the ratio is essentially 1. This must be tight:
# a skipped stretch leaves the track at its true tempo, and even 0.5% of
# tempo error drifts ~100 ms across a 20 s crossfade — an audible flam.
STRETCH_SKIP_TOLERANCE = 0.0005     # skip stretching within +/-0.05%

ANALYSIS_SR = 22050                 # sample rate used for BPM/RMS analysis
RMS_FRAME_LENGTH = 2048
RMS_HOP_LENGTH = 512
DECAY_SEARCH_SECONDS = 45.0         # tail window searched for energy decay

# .wav/.mp3/.flac/.aiff decode via libsndfile; .m4a (AAC) falls back to
# audioread, which uses CoreAudio on macOS — no ffmpeg needed there.
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".aiff", ".aif", ".m4a"}

# Filename BPM patterns like "72bpm", "_72bpm", "72 bpm", "72-BPM".
_FILENAME_BPM_RE = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*[-_ ]?bpm", re.IGNORECASE)


class RenderError(Exception):
    """A pipeline failure that knows which track and stage it happened in."""

    def __init__(self, track_name: str, stage: str, original: Exception):
        self.track_name = track_name
        self.stage = stage
        self.original = original
        super().__init__(f"Failed at stage '{stage}' for track '{track_name}': {original}")


# ---------------------------------------------------------------------------
# Environment / folder helpers
# ---------------------------------------------------------------------------

def rubberband_available() -> bool:
    """True if the rubberband CLI (required by pyrubberband) is on PATH."""
    return shutil.which("rubberband") is not None


def scan_folder(folder: Union[str, Path]) -> list[Path]:
    """Return supported audio files in *folder* (non-recursive), alphabetical.

    Skips this app's own rendered mixes (stitched_mix_*.wav) — the output is
    written into the source folder, and it must not become an input track on
    the next scan.
    """
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        raise NotADirectoryError(str(folder))
    files = [
        p for p in folder.iterdir()
        if p.is_file()
        and p.suffix.lower() in AUDIO_EXTENSIONS
        and not p.name.lower().startswith("stitched_mix")
    ]
    return sorted(files, key=lambda p: p.name.lower())


def parse_filename_bpm(filename: str) -> Optional[float]:
    """Extract a BPM embedded in a filename ("72bpm", "72 bpm", ...) if any."""
    match = _FILENAME_BPM_RE.search(filename)
    if not match:
        return None
    bpm = float(match.group(1))
    return bpm if 20.0 <= bpm <= 300.0 else None


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def suggest_output_bpm(bpms: Sequence[float]) -> Optional[int]:
    """Median of the effective track BPMs, rounded — minimizes total stretching."""
    values = [b for b in bpms if b]
    if not values:
        return None
    return int(round(float(np.median(values))))


def order_for_max_variety(
    fingerprints: Sequence[np.ndarray],
    fix_first: bool = False,
    fix_last: bool = False,
) -> list[int]:
    """Order tracks so adjacent ones sound least similar.

    fingerprints: one timbre vector per track (input order). Returns a
    permutation of input indices maximizing the total timbre distance between
    consecutive tracks — similar-sounding tracks get pushed apart. Features
    are z-scored per dimension; distance is euclidean. A greedy
    farthest-neighbor chain seeds the order, then pairwise-swap hill climbing
    refines it (deterministic; n is small, so this is instant).

    fix_first / fix_last pin the tracks currently in those input positions.
    """
    n = len(fingerprints)
    if n <= 2:
        return list(range(n))
    X = np.asarray([np.asarray(f, dtype=np.float64) for f in fingerprints])
    X = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-9)
    diff = X[:, None, :] - X[None, :, :]
    D = np.sqrt((diff ** 2).sum(axis=2))

    last_idx = n - 1 if fix_last else None
    start = 0 if fix_first else int(np.argmax(D.sum(axis=1)))
    if start == last_idx:
        start = 0 if last_idx != 0 else 1
    remaining = [i for i in range(n) if i != start]
    chain = [start]
    while remaining:
        candidates = [i for i in remaining if i != last_idx] or remaining
        nxt = max(candidates, key=lambda i: D[chain[-1], i])
        chain.append(nxt)
        remaining.remove(nxt)
    if last_idx is not None and chain[-1] != last_idx:
        chain.remove(last_idx)
        chain.append(last_idx)

    def score(order):
        return float(sum(D[order[k], order[k + 1]] for k in range(n - 1)))

    lo = 1 if fix_first else 0
    hi = n - 1 if fix_last else n
    best = score(chain)
    improved = True
    while improved:
        improved = False
        for i in range(lo, hi):
            for j in range(i + 1, hi):
                chain[i], chain[j] = chain[j], chain[i]
                s = score(chain)
                if s > best + 1e-12:
                    best = s
                    improved = True
                else:
                    chain[i], chain[j] = chain[j], chain[i]
    return chain


def refine_bpm_from_beats(
    nominal_bpm: Optional[float],
    beats: Sequence[float],
    tolerance: float = 0.04,
) -> Optional[float]:
    """Measure a track's true tempo from its beat grid, guarded by the label.

    Tempo labels (detection rounded to 0.1, filename tags, manual entries)
    are often slightly off — a track called 152 BPM whose real pulse is 151.6
    ends up 0.3% off-tempo after stretching, which audibly drifts across a
    long crossfade. The beat grid measures the actual pulse: total elapsed
    time divided by total beat count (gaps from skipped beats are counted as
    whole multiples of the median interval, and quantization noise averages
    out over the track). The result is folded to the label's tempo octave and
    used only when it confirms the label within *tolerance* — otherwise the
    label wins.
    """
    if not nominal_bpm:
        return nominal_bpm
    nominal = float(nominal_bpm)
    beats = np.asarray(beats, dtype=np.float64)
    if len(beats) < 8:
        return nominal
    ibis = np.diff(beats)
    ibis = ibis[ibis > 1e-3]
    if len(ibis) < 4:
        return nominal
    med = float(np.median(ibis))
    counts = np.round(ibis / med)
    valid = counts >= 1
    if not np.any(valid):
        return nominal
    ibi = float(np.sum(ibis[valid]) / np.sum(counts[valid]))
    raw = 60.0 / ibi
    octave = 2.0 ** round(math.log2(nominal / raw))
    refined = raw * octave
    if abs(refined / nominal - 1.0) <= tolerance:
        return refined
    return nominal


def beat_grid_trusted(nominal_bpm: Optional[float], beats: Sequence[float]) -> bool:
    """True when a beat grid is dense and consistent enough to warp against.

    Beat-mapped stretching pins every detected beat to the output grid, so a
    sparse or erratic grid (tracker losing the pulse) would warp the audio
    audibly wrong. Require: enough beats, mostly single-beat steps, and an
    implied tempo that confirms the labeled BPM (within an octave fold).
    """
    beats = np.asarray(beats, dtype=np.float64)
    if not nominal_bpm or len(beats) < 16:
        return False
    ibis = np.diff(beats)
    ibis = ibis[ibis > 1e-3]
    if len(ibis) < 8:
        return False
    med = float(np.median(ibis))
    counts = np.round(ibis / med)
    if float(np.mean(counts == 1)) < 0.8:
        return False
    valid = counts >= 1
    ibi = float(np.sum(ibis[valid]) / np.sum(counts[valid]))
    raw = 60.0 / ibi
    octave = 2.0 ** round(math.log2(float(nominal_bpm) / raw))
    return abs(raw * octave / float(nominal_bpm) - 1.0) <= 0.04


def build_beat_timemap(
    beats: Sequence[float],
    nominal_bpm: float,
    output_bpm: float,
    n_src_samples: int,
    sr: int,
) -> tuple[list, np.ndarray]:
    """Pins mapping every detected beat onto the exact output tempo grid.

    Returns (pins, beat_targets_seconds): pins are (source_sample,
    target_sample) pairs for pyrubberband.timemap_stretch — every beat lands
    at first_beat + k * (60 / output_bpm), with skipped detections counted as
    whole beats, and the head/tail scaled at the track's average rate. This
    corrects tempo drift *within* a track, which a uniform stretch cannot.
    """
    beats = np.asarray(beats, dtype=np.float64)
    refined = refine_bpm_from_beats(float(nominal_bpm), beats)
    rate = float(output_bpm) / refined
    period = 60.0 / float(output_bpm)
    ibis = np.diff(beats)
    med = float(np.median(ibis))
    # The tracker may tick at half/double the labeled tempo (e.g. a track
    # auto-folded to 152 whose beats were detected at 76): one detected-beat
    # step then spans `octave` output beats. Targets must be spaced by
    # period * octave, or the warp would play the track at 2x / 0.5x speed.
    raw = 60.0 / med
    octave = 2.0 ** round(math.log2(float(nominal_bpm) / raw))
    step = period * octave
    k = np.concatenate([[0.0], np.cumsum(np.maximum(1.0, np.round(ibis / med)))])
    targets = beats[0] / rate + k * step

    # The tracker loses the pulse in quiet intros/outros, but the music
    # usually keeps time there — and outros are exactly where crossfades
    # live. Extend the grid past the detected beats at the LOCAL tempo
    # (median of the nearest single-beat intervals), so drift correction
    # holds through the head and tail instead of reverting to the average
    # rate the moment detection stops.
    singles = ibis[np.round(ibis / med) == 1]
    ibi_head = float(np.median(singles[:8])) if len(singles) >= 3 else None
    ibi_tail = float(np.median(singles[-8:])) if len(singles) >= 3 else None
    src_list, tgt_list = list(beats), list(targets)
    if ibi_head:
        j = 1
        while (beats[0] - j * ibi_head > 0.02
               and targets[0] - j * step > 0.02):
            src_list.insert(0, beats[0] - j * ibi_head)
            tgt_list.insert(0, targets[0] - j * step)
            j += 1
    dur_src = n_src_samples / sr
    if ibi_tail:
        j = 1
        while beats[-1] + j * ibi_tail < dur_src - 0.02:
            src_list.append(beats[-1] + j * ibi_tail)
            tgt_list.append(targets[-1] + j * step)
            j += 1

    pins = [(0, 0)]
    for b_src, b_tgt in zip(src_list, tgt_list):
        s, t = int(round(b_src * sr)), int(round(b_tgt * sr))
        if s > pins[-1][0] and t > pins[-1][1] and s < n_src_samples:
            pins.append((s, t))
    tail_src = n_src_samples - pins[-1][0]
    tail_rate = (ibi_tail / step) if ibi_tail else rate
    pins.append((n_src_samples,
                 pins[-1][1] + max(1, int(round(tail_src / tail_rate)))))
    # Report only DETECTED beats as beat positions — the extrapolated pins
    # shape the warp but should not count as audible beats (e.g. a silent
    # intro must still read as beatless to alignment and preview logic).
    beat_targets = np.asarray(
        [t for s, t in zip(beats, targets) if 0 < s * sr < n_src_samples],
        dtype=np.float64,
    )
    return pins, beat_targets


def _segment_pins(pins: list, s0: float, s1: float, seg_len: int) -> list:
    """Restrict a full-track timemap to a source segment [s0, s1).

    Returns pins relative to the segment start (source) and to the warped
    segment start (target), ending exactly at (seg_len, warped_seg_len) as
    pyrubberband requires.
    """
    src = np.asarray([p[0] for p in pins], dtype=np.float64)
    tgt = np.asarray([p[1] for p in pins], dtype=np.float64)
    t0 = float(np.interp(s0, src, tgt))
    t1 = float(np.interp(s1, src, tgt))
    seg = [(0, 0)]
    for s, t in zip(src, tgt):
        if s0 < s < s1:
            rs, rt = int(round(s - s0)), int(round(t - t0))
            if 0 < rs < seg_len and rt > seg[-1][1]:
                seg.append((rs, rt))
    seg.append((seg_len, max(seg[-1][1] + 1, int(round(t1 - t0)))))
    return seg


def stretch_track_beatmapped(
    audio: np.ndarray,
    sr: int,
    beats: Sequence[float],
    nominal_bpm: float,
    output_bpm: float,
) -> tuple[np.ndarray, Optional[np.ndarray], bool]:
    """Warp a track so every beat lands exactly on the output grid.

    Returns (audio, beat_positions_seconds, True) when the beat grid is
    trusted; otherwise falls back to the uniform pitch-preserving stretch and
    returns (audio, None, False) so the caller can map beats by the average
    rate instead.
    """
    if not beat_grid_trusted(nominal_bpm, beats):
        rate = float(output_bpm) / refine_bpm_from_beats(float(nominal_bpm), beats)
        stretched, _ = stretch_track(audio, rate, sr)
        return stretched, None, False
    import pyrubberband

    pins, beat_targets = build_beat_timemap(
        beats, nominal_bpm, output_bpm, len(audio), sr)
    warped = pyrubberband.timemap_stretch(audio, sr, pins)
    return np.ascontiguousarray(warped, dtype=np.float32), beat_targets, True


def fold_bpm_to_reference(bpm: Optional[float], reference: Optional[float]):
    """Fold a detected BPM into the tempo octave nearest *reference*.

    librosa frequently hears ambient material at half or double the true
    tempo. Given the folder's median BPM as reference, return
    (folded_bpm, multiplier) where multiplier ∈ {0.5, 1, 2} minimizes the
    log-tempo distance to the reference. multiplier == 1 means no change.
    """
    if not bpm or not reference:
        return bpm, 1.0
    best = min((1.0, 2.0, 0.5), key=lambda m: abs(math.log2(bpm * m / reference)))
    return round(bpm * best, 1), best


# ---------------------------------------------------------------------------
# Per-track analysis
# ---------------------------------------------------------------------------

def analyze_track(path: Union[str, Path]) -> dict:
    """Analyze one file: duration, detected BPM, filename BPM, RMS envelope.

    Returns a plain dict (picklable, so it plays well with st.cache_data):
        duration      float seconds
        detected_bpm  float rounded to 1 decimal, or None if detection failed
        filename_bpm  float or None
        rms_env       1-D np.ndarray of frame RMS values
        rms_hop, rms_sr  frame geometry for converting frames -> seconds
        error         str, only present if the file could not be read
    """
    path = Path(path)
    try:
        y, sr = librosa.load(str(path), sr=ANALYSIS_SR, mono=True)
    except Exception as exc:  # unreadable/corrupt file
        return {"error": f"could not read file: {exc}"}

    duration = len(y) / sr

    detected_bpm: Optional[float] = None
    beat_times = np.zeros(0, dtype=np.float32)
    try:
        onset_env = librosa.onset.onset_strength(
            y=y, sr=sr, hop_length=RMS_HOP_LENGTH)
        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_env, sr=sr, hop_length=RMS_HOP_LENGTH)
        tempo = float(np.atleast_1d(tempo)[0])
        if math.isfinite(tempo) and tempo > 10.0:
            detected_bpm = round(tempo, 1)
        # Beat positions (seconds, source-time) — used at render time to
        # phase-align crossfades and beat-map tracks onto the output grid.
        # Snapped to the local onset peak with sub-frame precision: the raw
        # frame grid quantizes to ~23 ms, which would become the accuracy
        # floor of every beat-aligned transition.
        beat_times = _snap_beats_to_onsets(
            onset_env, beat_frames, sr, RMS_HOP_LENGTH).astype(np.float32)
    except Exception:
        detected_bpm = None

    rms = librosa.feature.rms(
        y=y, frame_length=RMS_FRAME_LENGTH, hop_length=RMS_HOP_LENGTH
    )[0].astype(np.float32)

    # Timbre fingerprint (MFCC mean + std) for audio-similarity ordering.
    try:
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        fingerprint = np.concatenate(
            [mfcc.mean(axis=1), mfcc.std(axis=1)]
        ).astype(np.float32)
    except Exception:
        fingerprint = None

    return {
        "duration": duration,
        "detected_bpm": detected_bpm,
        "filename_bpm": parse_filename_bpm(path.name),
        "beats": beat_times,
        "rms_env": rms,
        "rms_hop": RMS_HOP_LENGTH,
        "rms_sr": ANALYSIS_SR,
        "fingerprint": fingerprint,
    }


def _snap_beats_to_onsets(
    onset_env: np.ndarray, beat_frames: np.ndarray, sr: int, hop: int
) -> np.ndarray:
    """Refine beat frames to sub-frame times via the onset-strength peak.

    Looks for the local onset maximum within ±2 frames of each tracked beat
    and interpolates the peak parabolically, reducing the ~23 ms frame
    quantization to a few ms — the difference between a tight and a flammy
    beat-aligned crossfade.
    """
    env = np.asarray(onset_env, dtype=np.float64)
    times = []
    for f in np.asarray(beat_frames, dtype=int):
        lo = max(1, f - 2)
        hi = min(len(env) - 1, f + 3)
        if hi - lo < 1:
            times.append(float(f))
            continue
        p = lo + int(np.argmax(env[lo:hi]))
        a, b, c = env[p - 1], env[p], env[p + 1]
        denom = a - 2.0 * b + c
        delta = 0.5 * (a - c) / denom if denom < -1e-12 else 0.0
        times.append(p + float(np.clip(delta, -0.5, 0.5)))
    return np.asarray(times, dtype=np.float64) * hop / sr


# ---------------------------------------------------------------------------
# Crossfade anchor placement
# ---------------------------------------------------------------------------

def find_decay_onset_seconds(
    env: np.ndarray,
    hop: int,
    sr: int,
    search_seconds: float = DECAY_SEARCH_SECONDS,
) -> Optional[float]:
    """Find where sustained energy decline begins near the end of a track.

    Looks at the last *search_seconds* of the (smoothed) RMS envelope for a
    peak followed by a mostly-monotonic decline that ends clearly quieter.
    Returns the onset time in seconds (source-time), or None if no clear
    decay is found (caller falls back to an end-aligned fade).
    """
    env = np.asarray(env, dtype=np.float64).ravel()
    frames_per_second = sr / hop
    smooth_win = max(1, int(round(frames_per_second)))  # ~1 s moving average
    if len(env) < smooth_win * 4:
        return None
    kernel = np.ones(smooth_win) / smooth_win
    smoothed = np.convolve(env, kernel, mode="same")

    tail_frames = min(len(smoothed), int(round(search_seconds * frames_per_second)))
    tail = smoothed[-tail_frames:]
    offset = len(smoothed) - tail_frames

    # The decay onset is the LAST frame still at (essentially) peak level —
    # np.argmax alone would return the start of a sustained plateau instead
    # of the point where decline actually begins.
    peak_val = float(np.max(tail))
    near_peak = np.flatnonzero(tail >= 0.995 * peak_val)
    peak_rel = int(near_peak[-1])
    after = tail[peak_rel:]
    if peak_val <= 1e-8 or len(after) < smooth_win * 2:
        return None

    # "Sustained decline": nearly all frame-to-frame steps after the peak are
    # non-increasing (tiny wobble allowed), and the end is clearly quieter.
    diffs = np.diff(after)
    declining_fraction = float(np.mean(diffs <= peak_val * 1e-3))
    ends_quiet = after[-1] < 0.75 * peak_val
    if declining_fraction >= 0.7 and ends_quiet:
        return (offset + peak_rel) * hop / sr
    return None


def beat_aligned_anchor(
    desired_anchor: int,
    out_beats: np.ndarray,
    in_first_beat: Optional[float],
    lo: int,
    hi: int,
) -> tuple[int, Optional[int]]:
    """Snap a crossfade anchor so the tracks' beat grids coincide.

    All positions are in samples of the (stretched) audio. The incoming track
    starts playing at the anchor, so its first beat lands at
    ``anchor + in_first_beat`` on the outgoing track's timeline. Pick the
    outgoing beat closest to where the decay heuristic wanted the fade and
    place the anchor so the incoming first beat hits it exactly — both tracks
    are at the same BPM, so aligning one beat aligns the whole grid.

    Returns (anchor, shift_in_samples), or (desired_anchor, None) when either
    track has no usable beat grid or no aligned position fits in [lo, hi].
    """
    if in_first_beat is None or len(out_beats) == 0:
        return desired_anchor, None
    candidates = np.round(out_beats - in_first_beat)
    candidates = candidates[(candidates >= lo) & (candidates <= hi)]
    if len(candidates) == 0:
        return desired_anchor, None
    anchor = int(candidates[np.argmin(np.abs(candidates - desired_anchor))])
    return anchor, anchor - desired_anchor


def equal_power_curves(n: int) -> tuple[np.ndarray, np.ndarray]:
    """(fade_out, fade_in) equal-power (cos/sin) curves, shaped (n, 1)."""
    t = np.linspace(0.0, np.pi / 2.0, n, endpoint=True)
    return np.cos(t)[:, None], np.sin(t)[:, None]


def choose_fade_anchor(
    out_spec: dict,
    in_spec: dict,
    out_rate: float,
    in_rate: float,
    out_len_samples: int,
    fade_n: int,
    sample_rate: int,
    manual_offset_s: float = 0.0,
    out_beats_stretched: Optional[np.ndarray] = None,
    in_beats_stretched: Optional[np.ndarray] = None,
    out_head_trim_s: float = 0.0,
) -> tuple[int, str]:
    """Pick where the outgoing track's fade begins (samples, stretched time).

    Shared by render_mix and render_transition_preview so the preview always
    matches the final render. Pipeline: energy-decay heuristic -> beat-grid
    alignment -> optional manual nudge (applied last, so a nudge deliberately
    overrides the automatic alignment). Every step is clamped so the fade
    stays inside the outgoing track. Returns (anchor, human-readable note).

    out_beats_stretched / in_beats_stretched: exact beat positions in
    stretched-track seconds (e.g. from beat-mapped warping); when omitted the
    analysis beats are mapped by the average rate. out_head_trim_s: seconds
    already trimmed from the head of the outgoing (stretched) track — all
    positions are shifted accordingly. out_len_samples is the length AFTER
    that trim. Incoming beats must already be relative to its entry point.
    """
    hi = max(0, out_len_samples - fade_n)
    decay_t = find_decay_onset_seconds(
        out_spec["rms_env"], out_spec["rms_hop"], out_spec["rms_sr"]
    )
    if decay_t is not None:
        anchor = int(round((decay_t / out_rate - out_head_trim_s) * sample_rate))
        kind = "energy decay"
    else:
        anchor = hi
        kind = "end-aligned (no clear decay)"
    anchor = max(0, min(anchor, hi))

    if out_beats_stretched is None:
        out_beats_stretched = (
            np.asarray(out_spec.get("beats", []), dtype=np.float64) / out_rate
        )
    if in_beats_stretched is None:
        in_beats_stretched = (
            np.asarray(in_spec.get("beats", []), dtype=np.float64) / in_rate
        )
    out_beats = (
        np.asarray(out_beats_stretched, dtype=np.float64) - out_head_trim_s
    ) * sample_rate
    out_beats = out_beats[out_beats >= 0]
    in_beats = np.asarray(in_beats_stretched, dtype=np.float64) * sample_rate
    in_beats = in_beats[in_beats >= 0]
    in_first_beat = float(in_beats[0]) if len(in_beats) else None
    anchor, beat_shift = beat_aligned_anchor(anchor, out_beats, in_first_beat, 0, hi)
    if beat_shift is None:
        note = f"{kind}, not beat-aligned — no beat grid detected"
    else:
        note = (
            f"{kind}, beat-aligned (anchor shifted "
            f"{beat_shift / sample_rate * 1000:+.0f} ms)"
        )
    if manual_offset_s:
        anchor = max(0, min(anchor + int(round(manual_offset_s * sample_rate)), hi))
        note += f", manual nudge {manual_offset_s:+.2f} s"
    return anchor, note


# ---------------------------------------------------------------------------
# Per-track processing stages
# ---------------------------------------------------------------------------

def load_track_stereo(
    path: Union[str, Path],
    sr: int = SAMPLE_RATE,
    offset: float = 0.0,
    duration: Optional[float] = None,
) -> np.ndarray:
    """Load at the common rate as float32 stereo, shape (n_samples, 2).

    offset/duration (seconds) allow loading just a segment — used by the
    transition preview so long tracks don't have to be read in full.
    """
    y, _ = librosa.load(str(path), sr=sr, mono=False, offset=offset, duration=duration)
    if y.ndim == 1:
        y = np.stack([y, y])
    elif y.shape[0] == 1:
        y = np.vstack([y, y])
    elif y.shape[0] > 2:
        y = y[:2]
    return np.ascontiguousarray(y.T, dtype=np.float32)


def stretch_track(
    audio: np.ndarray, rate: float, sr: int = SAMPLE_RATE
) -> tuple[np.ndarray, bool]:
    """Pitch-preserving time stretch. rate > 1 speeds up (shorter output).

    Skips processing entirely when the ratio is within STRETCH_SKIP_TOLERANCE.
    """
    if abs(rate - 1.0) <= STRETCH_SKIP_TOLERANCE:
        return audio, False
    import pyrubberband  # deferred: import fails loudly only when stretching

    stretched = pyrubberband.time_stretch(audio, sr, rate)
    return np.ascontiguousarray(stretched, dtype=np.float32), True


def normalize_track(
    audio: np.ndarray, sr: int = SAMPLE_RATE, target_lufs: float = WORKING_LUFS
) -> tuple[np.ndarray, float]:
    """Gain-match a track to the working loudness. Returns (audio, gain_db)."""
    try:
        meter = pyln.Meter(sr)
        lufs = meter.integrated_loudness(audio.astype(np.float64))
    except ValueError:  # shorter than one 400 ms measurement block
        return audio, 0.0
    if not math.isfinite(lufs):  # silence
        return audio, 0.0
    gain_db = target_lufs - lufs
    return (audio * (10.0 ** (gain_db / 20.0))).astype(np.float32), gain_db


# ---------------------------------------------------------------------------
# Transition preview (for the manual-alignment UI)
# ---------------------------------------------------------------------------

def _track_grid(spec: dict, output_bpm: float, sample_rate: int):
    """Per-track stretch geometry shared by preview and render.

    Returns (rate, pins, beats_stretched, len_stretched_s): pins is the full
    beat timemap when the grid is trusted (else None), beats_stretched are
    beat positions in stretched-track seconds.
    """
    beats = np.asarray(spec.get("beats", []), dtype=np.float64)
    rate = float(output_bpm) / refine_bpm_from_beats(float(spec["bpm"]), beats)
    n_src = int(round(float(spec["duration"]) * sample_rate))
    if beat_grid_trusted(spec["bpm"], beats):
        pins, beat_tgts = build_beat_timemap(
            beats, spec["bpm"], output_bpm, n_src, sample_rate)
        return rate, pins, beat_tgts, pins[-1][1] / sample_rate
    return rate, None, beats / rate, float(spec["duration"]) / rate


def _load_warped_segment(
    spec: dict,
    rate: float,
    pins,
    st_start: float,
    st_end: float,
    sample_rate: int,
) -> np.ndarray:
    """Load and stretch just the audio for stretched-time [st_start, st_end).

    Uses the same beat timemap as the full render (restricted to the
    segment) when available, otherwise a uniform stretch.
    """
    if pins is not None:
        src = np.asarray([p[0] for p in pins], dtype=np.float64)
        tgt = np.asarray([p[1] for p in pins], dtype=np.float64)
        s0 = float(np.interp(st_start * sample_rate, tgt, src))
        s1 = float(np.interp(st_end * sample_rate, tgt, src))
    else:
        s0, s1 = st_start * rate * sample_rate, st_end * rate * sample_rate
    y = load_track_stereo(
        spec["path"], sample_rate,
        offset=max(0.0, s0 / sample_rate),
        duration=max(0.1, (s1 - s0) / sample_rate),
    )
    if pins is not None:
        import pyrubberband

        seg_pins = _segment_pins(pins, s0, s1, len(y))
        y = np.ascontiguousarray(
            pyrubberband.timemap_stretch(y, sample_rate, seg_pins),
            dtype=np.float32,
        )
    else:
        y, _ = stretch_track(y, rate, sample_rate)
    return y


def render_transition_preview(
    out_spec: dict,
    in_spec: dict,
    output_bpm: float,
    fade_seconds: float,
    manual_offset_s: float = 0.0,
    in_start_s: float = 0.0,
    out_head_trim_s: float = 0.0,
    context_seconds: float = 10.0,
    sample_rate: int = SAMPLE_RATE,
) -> dict:
    """Render just the crossover between two tracks, for audition and display.

    Loads and stretches only the audio around the transition (context_seconds
    on each side), so it is fast even for long tracks. Uses the same
    choose_fade_anchor, tempo refinement, and beat-mapped warping as the full
    render, so what you hear is what you get. Specs need the analyze_track
    fields plus "path", "bpm", and "duration". Per-track gain is approximated
    by normalizing the loaded segments.

    in_start_s: seconds (stretched-time) into the incoming track where it
    enters the mix. out_head_trim_s: the previous transition's in_start for
    the OUTGOING track, so its positions match the final render.

    Returns a dict with:
        audio          float32 (n, 2) preview
        sample_rate    int
        fade_start     seconds into the preview where the crossfade begins
        fade_seconds   effective fade length (short-track rule applied)
        anchor_seconds fade start position within the stretched outgoing track
        note           human-readable anchor description
        out_env, in_env, env_rate   coarse amplitude envelopes with the
            crossfade gains applied (so the taper is visible); the incoming
            envelope starts at fade_start on the preview timeline.
        out_beats, in_beats   beat positions on the preview timeline, for
            beat tick marks in the waveform display.
    """
    out_rate, out_pins, out_beats_st, out_len_st = _track_grid(
        out_spec, output_bpm, sample_rate)
    in_rate, in_pins, in_beats_st, in_len_st = _track_grid(
        in_spec, output_bpm, sample_rate)

    out_head_trim_s = min(max(0.0, out_head_trim_s), max(0.0, out_len_st - 1.0))
    in_start_s = min(max(0.0, in_start_s), max(0.0, in_len_st - 1.0))
    out_len_eff = out_len_st - out_head_trim_s
    in_len_eff = in_len_st - in_start_s

    fade_s = float(fade_seconds)
    shorter = min(out_len_eff, in_len_eff)
    if shorter < 2.0 * fade_s:
        fade_s = 0.4 * shorter
    fade_n = max(1, int(round(fade_s * sample_rate)))

    anchor, note = choose_fade_anchor(
        out_spec, in_spec, out_rate, in_rate,
        int(round(out_len_eff * sample_rate)), fade_n, sample_rate,
        manual_offset_s=manual_offset_s,
        out_beats_stretched=out_beats_st,
        in_beats_stretched=np.asarray(in_beats_st) - in_start_s,
        out_head_trim_s=out_head_trim_s,
    )

    # Outgoing: the segment ends exactly where the fade ends (anchor + fade),
    # so after stretching, the fade occupies its final fade_n samples.
    # Positions here are in the UNTRIMMED stretched timeline.
    fade_end_abs = out_head_trim_s + anchor / sample_rate + fade_s
    seg_start_abs = max(out_head_trim_s, fade_end_abs - fade_s - context_seconds)
    y_out = _load_warped_segment(
        out_spec, out_rate, out_pins, seg_start_abs, fade_end_abs, sample_rate)
    y_out, _ = normalize_track(y_out, sample_rate)

    # Incoming: at least fade + context past its entry point, but always long
    # enough to reach its first beat after entry — ambient tracks often open
    # with a long quiet intro, and a preview of pure silence looks broken.
    in_needed = fade_s + context_seconds
    beats_after_entry = np.asarray(in_beats_st, dtype=np.float64) - in_start_s
    beats_after_entry = beats_after_entry[beats_after_entry >= 0]
    if len(beats_after_entry):
        in_needed = max(in_needed, min(beats_after_entry[0] + 5.0, fade_s + 60.0))
    in_end_abs = min(in_len_st, in_start_s + in_needed)
    y_in = _load_warped_segment(
        in_spec, in_rate, in_pins, in_start_s, in_end_abs, sample_rate)
    y_in, _ = normalize_track(y_in, sample_rate)

    fade_n = min(fade_n, len(y_out), len(y_in))
    fade_out, fade_in = equal_power_curves(fade_n)
    head = y_out[:len(y_out) - fade_n]
    overlap = (y_out[len(y_out) - fade_n:] * fade_out + y_in[:fade_n] * fade_in)
    audio = np.concatenate([head, overlap.astype(np.float32), y_in[fade_n:]])
    fade_start_s = len(head) / sample_rate

    def coarse_env(y: np.ndarray, block: int) -> np.ndarray:
        mono = np.abs(y).mean(axis=1)
        pad = (-len(mono)) % block
        if pad:
            mono = np.concatenate([mono, np.zeros(pad, dtype=mono.dtype)])
        return mono.reshape(-1, block).max(axis=1)

    # Envelopes for display are post-fade so the crossfade taper is visible.
    y_out_faded = y_out.copy()
    y_out_faded[len(y_out) - fade_n:] *= fade_out
    y_in_faded = y_in.copy()
    y_in_faded[:fade_n] *= fade_in

    # Beat positions mapped onto the preview timeline (t=0 = preview start;
    # the incoming track enters at fade_start_s), for tick marks in the UI.
    ob = np.asarray(out_beats_st, dtype=np.float64)
    out_beats_pv = ob[
        (ob >= seg_start_abs) & (ob <= seg_start_abs + len(y_out) / sample_rate)
    ] - seg_start_abs
    ib = beats_after_entry
    in_beats_pv = ib[ib <= len(y_in) / sample_rate] + fade_start_s

    env_block = max(1, sample_rate // 200)  # ~200 envelope points/s (zoomable)
    return {
        "audio": audio,
        "sample_rate": sample_rate,
        "fade_start": fade_start_s,
        "fade_seconds": fade_n / sample_rate,
        "anchor_seconds": anchor / sample_rate,
        "note": note,
        "out_env": coarse_env(y_out_faded, env_block),
        "in_env": coarse_env(y_in_faded, env_block),
        "out_beats": out_beats_pv,
        "in_beats": in_beats_pv,
        "env_rate": sample_rate / env_block,
    }


# ---------------------------------------------------------------------------
# Blockwise loudness / true peak (bounded memory for long mixes)
# ---------------------------------------------------------------------------

def integrated_loudness_blockwise(audio: np.ndarray, sr: int) -> float:
    """ITU-R BS.1770-4 integrated loudness, computed in bounded memory.

    Equivalent to pyloudnorm's Meter.integrated_loudness (validated against it
    in tests), but filters and accumulates in chunks so a long float32 mix is
    never copied wholesale to float64. Uses pyloudnorm's own K-weighting
    coefficients. Requires sr * 0.1 to be an integer (true for 48 kHz).
    """
    from scipy.signal import lfilter

    n_samples, n_channels = audio.shape
    bin_len = int(round(sr * 0.1))          # 100 ms bins; 400 ms gating blocks
    n_bins = n_samples // bin_len
    if n_bins < 4:
        raise ValueError("signal too short to measure integrated loudness")

    filters = list(pyln.Meter(sr)._filters.values())
    # Per-channel filter state so we can process in chunks.
    zis = [[np.zeros(max(len(f.b), len(f.a)) - 1) for f in filters]
           for _ in range(n_channels)]

    bin_energy = np.zeros(n_bins)           # channel-summed sum of squares
    chunk_bins = max(1, (2 ** 20) // bin_len)
    for start_bin in range(0, n_bins, chunk_bins):
        end_bin = min(n_bins, start_bin + chunk_bins)
        seg = audio[start_bin * bin_len:end_bin * bin_len]
        for ch in range(n_channels):
            x = seg[:, ch].astype(np.float64)
            for fi, f in enumerate(filters):
                x, zis[ch][fi] = lfilter(f.b, f.a, x, zi=zis[ch][fi])
            sq = (x * x).reshape(end_bin - start_bin, bin_len)
            bin_energy[start_bin:end_bin] += sq.sum(axis=1)

    # 400 ms gating blocks with 75% overlap = every 100 ms bin starts one.
    block_energy = bin_energy[:-3] + bin_energy[1:-2] + bin_energy[2:-1] + bin_energy[3:]
    z = block_energy / (4 * bin_len)        # mean square per block (chs summed)
    with np.errstate(divide="ignore"):
        l_blocks = -0.691 + 10.0 * np.log10(z)

    abs_gated = z[l_blocks > -70.0]
    if abs_gated.size == 0:
        return -float("inf")
    rel_threshold = -0.691 + 10.0 * np.log10(abs_gated.mean()) - 10.0
    gated = z[(l_blocks > -70.0) & (l_blocks > rel_threshold)]
    if gated.size == 0:
        return -float("inf")
    return -0.691 + 10.0 * np.log10(gated.mean())


def highpass_inplace(mix: np.ndarray, sr: int, cutoff_hz: float = 20.0) -> None:
    """Remove DC offset and subsonic rumble in place (2nd-order Butterworth).

    Inaudible content below ~20 Hz eats limiter headroom and can wobble
    speaker cones; stripping it is the standard first step of a master chain.
    Processes blockwise with filter state carried across chunks.
    """
    from scipy.signal import butter, sosfilt, sosfilt_zi

    sos = butter(2, cutoff_hz, btype="highpass", fs=sr, output="sos")
    for ch in range(mix.shape[1]):
        zi = sosfilt_zi(sos) * float(mix[0, ch])
        chunk = 1 << 20
        for s in range(0, len(mix), chunk):
            seg = mix[s:s + chunk, ch].astype(np.float64)
            out, zi = sosfilt(sos, seg, zi=zi)
            mix[s:s + chunk, ch] = out.astype(np.float32)


def true_peak_limiter(
    mix: np.ndarray,
    sr: int,
    ceiling_db: float = TRUE_PEAK_CEILING_DBTP,
    lookahead_ms: float = 40.0,
    hold_ms: float = 250.0,
    smooth_ms: float = 40.0,
) -> float:
    """Transparent brickwall true-peak limiter, applied in place.

    Offline design (no latency constraint): a 4x-oversampled true-peak
    envelope drives a gain curve built from a windowed minimum (looking
    lookahead_ms ahead and holding hold_ms behind) smoothed with a
    triangular window — so gain dips just before each peak, holds, and
    recovers gently, only where the ceiling would be exceeded. Everything
    below the ceiling passes bit-transparent (gain 1). Returns the maximum
    gain reduction in dB (0.0 if the limiter never engaged).

    The gain envelope runs at sr/4 (the triangular smoothing makes it far
    smoother than that resolution) and is linearly interpolated to full
    rate, keeping memory bounded for hour-long mixes.
    """
    from scipy.ndimage import minimum_filter1d, uniform_filter1d
    from scipy.signal import resample_poly

    # Small margin so envelope-interpolation error never breaches the ceiling.
    ceiling = 10.0 ** ((ceiling_db - 0.05) / 20.0)
    dec = 16                      # envelope decimation (of the 4x stream)
    env_rate = sr * 4 // dec

    n = len(mix)
    env_len = (n * 4 + dec - 1) // dec
    env = np.zeros(env_len, dtype=np.float32)
    chunk = 1 << 20
    pad = 256
    for s in range(0, n, chunk):
        lo, hi = max(0, s - pad), min(n, s + chunk + pad)
        up = resample_poly(mix[lo:hi].astype(np.float64), 4, 1, axis=0)
        core = np.abs(up[(s - lo) * 4:(s - lo) * 4 + chunk * 4]).max(axis=1)
        if len(core) % dec:
            core = np.concatenate([core, np.zeros(dec - len(core) % dec)])
        blocks = core.reshape(-1, dec).max(axis=1).astype(np.float32)
        env[s * 4 // dec:s * 4 // dec + len(blocks)] = blocks

    gain = np.minimum(1.0, ceiling / np.maximum(env, 1e-12)).astype(np.float32)
    max_reduction_db = float(-20.0 * math.log10(max(float(gain.min()), 1e-6)))
    if max_reduction_db < 0.01:
        return 0.0  # nothing over the ceiling — bit-transparent

    ahead = max(1, int(lookahead_ms / 1000.0 * env_rate))
    hold = max(1, int(hold_ms / 1000.0 * env_rate))
    smooth = max(1, int(smooth_ms / 1000.0 * env_rate))
    # Windowed minimum over [n - hold, n + ahead] ...
    gain = minimum_filter1d(gain, size=ahead + hold + 1,
                            origin=(ahead - hold) // 2, mode="nearest")
    # ... then triangular smoothing (two box passes). ahead >= smooth keeps
    # the smoothed value at each peak equal to the true minimum there.
    gain = uniform_filter1d(gain, size=smooth, mode="nearest")
    gain = uniform_filter1d(gain, size=smooth, mode="nearest")

    env_idx = np.arange(env_len, dtype=np.float64) * (dec / 4.0)  # in samples
    for s in range(0, n, chunk):
        hi = min(n, s + chunk)
        lo_e = max(0, int(s / (dec / 4.0)) - 2)
        hi_e = min(env_len, int(hi / (dec / 4.0)) + 3)
        g = np.interp(np.arange(s, hi, dtype=np.float64),
                      env_idx[lo_e:hi_e], gain[lo_e:hi_e])
        mix[s:hi] *= g[:, None].astype(np.float32)
    return max_reduction_db


def tpdf_dither_inplace(mix: np.ndarray, bits: int = 24) -> None:
    """Add 1-LSB TPDF dither before bit-depth reduction (standard practice
    when quantizing float masters to fixed point)."""
    lsb = 2.0 ** -(bits - 1)
    rng = np.random.default_rng(0)  # deterministic renders
    chunk = 1 << 20
    for s in range(0, len(mix), chunk):
        hi = min(len(mix), s + chunk)
        noise = (rng.random((hi - s, mix.shape[1]), dtype=np.float32)
                 + rng.random((hi - s, mix.shape[1]), dtype=np.float32) - 1.0)
        mix[s:hi] += noise * lsb


def true_peak_dbtp(audio: np.ndarray, sr: int, oversample: int = 4) -> float:
    """True peak in dBTP via 4x oversampling, processed in chunks."""
    from scipy.signal import resample_poly

    peak = 0.0
    chunk = 1 << 20
    pad = 256  # context so the polyphase filter has clean edges
    for start in range(0, len(audio), chunk):
        lo = max(0, start - pad)
        hi = min(len(audio), start + chunk + pad)
        up = resample_poly(audio[lo:hi].astype(np.float64), oversample, 1, axis=0)
        core = up[(start - lo) * oversample:(start - lo + chunk) * oversample]
        if core.size:
            peak = max(peak, float(np.max(np.abs(core))))
    return 20.0 * math.log10(peak) if peak > 0 else -float("inf")


# ---------------------------------------------------------------------------
# Render pipeline
# ---------------------------------------------------------------------------

def render_mix(
    tracks: Sequence[dict],
    output_bpm: float,
    crossfade_seconds: Union[float, Sequence[float]],
    output_path: Union[str, Path],
    sample_rate: int = SAMPLE_RATE,
    progress: Optional[Callable[[float, str], None]] = None,
    anchor_offsets: Optional[Sequence[float]] = None,
    in_offsets: Optional[Sequence[float]] = None,
    final_fade_seconds: float = 0.0,
    mastering: bool = True,
) -> dict:
    """Render the full mix and write a 24-bit WAV.

    tracks: ordered list of dicts, each with:
        path      absolute file path
        name      display name (for progress/log/errors)
        bpm       effective BPM (after filename/manual overrides)
        rms_env, rms_hop, rms_sr   analysis envelope for fade anchoring
        beats     beat times in seconds (source-time) for beat-phase alignment

    crossfade_seconds: a single global length, or a per-transition sequence of
    length len(tracks) - 1 (v1 UI passes one global value; the per-transition
    form is the extension point for future per-transition overrides).

    anchor_offsets: optional per-transition manual nudges in seconds, applied
    to each fade anchor after the automatic decay/beat placement.

    in_offsets: optional per-transition start offsets in seconds
    (stretched-time): how far into the incoming track it enters the mix —
    everything before the offset is skipped (e.g. to jump past a long intro).

    final_fade_seconds: when > 0, fade the end of the mix smoothly to
    silence over this many seconds (for final tracks that end abruptly).

    mastering: when True (default), run the studio mastering chain —
    20 Hz high-pass, loudness normalize, oversampled lookahead true-peak
    brickwall limiter with loudness convergence, and TPDF dither at the
    24-bit write. When False, fall back to a simple normalize +
    whole-mix peak protection (no filtering, limiting, or dither).

    Returns {output_path, duration, integrated_lufs, true_peak_dbtp, log}.
    """
    if not tracks:
        raise ValueError("no tracks to render")
    output_path = Path(output_path)

    n = len(tracks)
    if isinstance(crossfade_seconds, (int, float)):
        fade_lengths = [float(crossfade_seconds)] * (n - 1)
    else:
        fade_lengths = [float(f) for f in crossfade_seconds]
        if len(fade_lengths) != n - 1:
            raise ValueError("need one crossfade length per transition")
    offsets = [float(o) for o in anchor_offsets] if anchor_offsets else [0.0] * (n - 1)
    if len(offsets) != n - 1:
        raise ValueError("need one anchor offset per transition")
    starts = [float(o) for o in in_offsets] if in_offsets else [0.0] * (n - 1)
    if len(starts) != n - 1:
        raise ValueError("need one incoming start offset per transition")

    def report(frac: float, msg: str) -> None:
        if progress is not None:
            progress(min(1.0, frac), msg)

    log: list[str] = []
    chunks: list[np.ndarray] = []   # committed mix audio
    pending: Optional[np.ndarray] = None  # last processed track, not yet committed
    prev_rate = 1.0
    prev_spec: Optional[dict] = None
    prev_beat_pos: Optional[np.ndarray] = None  # stretched beat positions (s)
    prev_head_trim = 0.0
    per_track_budget = 0.9 / n      # progress: 90% tracks, 10% mastering

    for i, spec in enumerate(tracks):
        name = spec["name"]
        base = i * per_track_budget

        stage = "load"
        report(base, f"Loading track {i + 1} of {n}: {name}")
        try:
            audio = load_track_stereo(spec["path"], sample_rate)
            if len(audio) == 0:
                raise ValueError("file contains no audio")
        except Exception as exc:
            raise RenderError(name, stage, exc) from exc

        stage = "stretch"
        # Stretch by the tempo measured from the beat grid (guarded by the
        # labeled BPM) — labels are rarely exact, and a fraction of a percent
        # of tempo error audibly drifts across a long crossfade. When the
        # grid is trusted, go further and beat-map: warp so every beat lands
        # exactly on the output grid, correcting drift *within* the track.
        nominal_bpm = float(spec["bpm"])
        beats_src = spec.get("beats", [])
        refined_bpm = refine_bpm_from_beats(nominal_bpm, beats_src)
        rate = float(output_bpm) / refined_bpm
        if abs(refined_bpm - nominal_bpm) > 0.005:
            log.append(
                f"{name}: tempo refined {nominal_bpm:g} -> {refined_bpm:.2f} BPM "
                f"(measured from its beat grid)"
            )
        report(base + 0.3 * per_track_budget, f"Stretching track {i + 1} of {n}: {name}")
        try:
            audio, beat_pos, mapped = stretch_track_beatmapped(
                audio, sample_rate, beats_src, nominal_bpm, output_bpm)
        except Exception as exc:
            raise RenderError(name, stage, exc) from exc
        if mapped:
            log.append(
                f"{name}: beat-mapped — {len(beat_pos)} beats pinned exactly "
                f"onto the {output_bpm:g} BPM grid (pitch preserved)"
            )
        else:
            beat_pos = np.asarray(beats_src, dtype=np.float64) / rate
            log.append(
                f"{name}: uniform stretch {refined_bpm:.2f} -> {output_bpm:g} BPM "
                f"(x{1 / rate:.3f} duration, pitch preserved; beat grid not "
                f"dense enough to beat-map)"
            )

        stage = "normalize"
        report(base + 0.7 * per_track_budget, f"Normalizing track {i + 1} of {n}: {name}")
        try:
            audio, gain_db = normalize_track(audio, sample_rate)
        except Exception as exc:
            raise RenderError(name, stage, exc) from exc
        log.append(f"{name}: gain {gain_db:+.1f} dB to reach {WORKING_LUFS:g} LUFS")

        stage = "crossfade"
        report(base + 0.85 * per_track_budget, f"Blending track {i + 1} of {n}: {name}")
        try:
            # Optional per-transition entry point: skip the incoming track's
            # head (e.g. a long intro) so it enters mid-stream. Keep >= 1 s.
            head_trim_s = 0.0
            if pending is not None and starts[i - 1] > 0:
                trim_n = min(int(round(starts[i - 1] * sample_rate)),
                             max(0, len(audio) - sample_rate))
                if trim_n > 0:
                    head_trim_s = trim_n / sample_rate
                    audio = audio[trim_n:]
                    log.append(
                        f"{name}: enters {head_trim_s:.1f} s into the track "
                        f"(head skipped)"
                    )
            if pending is None:
                pending = audio
            else:
                fade_s = fade_lengths[i - 1]
                dur_prev = len(pending) / sample_rate
                dur_cur = len(audio) / sample_rate
                shorter = min(dur_prev, dur_cur)
                if shorter < 2.0 * fade_s:
                    fade_s = 0.4 * shorter
                    log.append(
                        f"{prev_spec['name']} -> {name}: crossfade shortened to "
                        f"{fade_s:.1f} s (short track)"
                    )
                fade_n = max(1, int(round(fade_s * sample_rate)))

                # Anchor: energy decay -> beat alignment -> manual nudge (see
                # choose_fade_anchor, shared with the transition preview).
                anchor, anchor_note = choose_fade_anchor(
                    prev_spec, spec, prev_rate, rate,
                    len(pending), fade_n, sample_rate,
                    manual_offset_s=offsets[i - 1],
                    out_beats_stretched=prev_beat_pos,
                    in_beats_stretched=np.asarray(beat_pos) - head_trim_s,
                    out_head_trim_s=prev_head_trim,
                )

                dropped_s = (len(pending) - (anchor + fade_n)) / sample_rate
                fade_out, fade_in = equal_power_curves(fade_n)
                overlap = (
                    pending[anchor:anchor + fade_n] * fade_out
                    + audio[:fade_n] * fade_in
                ).astype(np.float32)
                chunks.append(pending[:anchor])
                chunks.append(overlap)
                pending = audio[fade_n:]

                msg = (
                    f"{prev_spec['name']} -> {name}: {fade_s:.1f} s equal-power "
                    f"fade anchored at {format_duration(anchor / sample_rate)} "
                    f"({anchor_note})"
                )
                if dropped_s > 0.05:
                    msg += f", trimmed {dropped_s:.1f} s of quiet tail"
                log.append(msg)
        except Exception as exc:
            raise RenderError(name, stage, exc) from exc

        prev_rate = rate
        prev_spec = spec
        prev_beat_pos = np.asarray(beat_pos, dtype=np.float64)
        prev_head_trim = head_trim_s

    chunks.append(pending)
    mix = np.concatenate(chunks, axis=0)
    del chunks, pending

    # Optional fade-out on the ending, applied before mastering so the
    # loudness/true-peak targets are measured on the final audio.
    if final_fade_seconds and final_fade_seconds > 0:
        n_fade = min(len(mix), int(round(float(final_fade_seconds) * sample_rate)))
        if n_fade > 1:
            curve = np.cos(np.linspace(0.0, np.pi / 2.0, n_fade)) ** 2
            mix[-n_fade:] *= curve[:, None].astype(np.float32)
            log.append(
                f"Final fade-out: last {n_fade / sample_rate:.1f} s of the mix "
                f"faded smoothly to silence"
            )

    stage = "master"
    report(0.92, "Mastering: measuring loudness…")
    try:
        if mastering:
            # Studio chain: subsonic high-pass -> loudness normalize ->
            # oversampled lookahead true-peak brickwall limiter (touches
            # only the peaks, instead of scaling the whole mix down) ->
            # loudness convergence -> TPDF dither at the 24-bit write.
            highpass_inplace(mix, sample_rate)
            log.append("Master: 20 Hz high-pass (DC/subsonic rumble removed)")
            lufs = integrated_loudness_blockwise(mix, sample_rate)
            if math.isfinite(lufs):
                master_gain_db = TARGET_LUFS - lufs
                mix *= np.float32(10.0 ** (master_gain_db / 20.0))
                log.append(
                    f"Master: {master_gain_db:+.1f} dB to reach {TARGET_LUFS:g} "
                    f"LUFS integrated (was {lufs:.1f})"
                )
            report(0.94, "Mastering: true-peak limiting…")
            reduction_db = true_peak_limiter(mix, sample_rate)
            if reduction_db > 0:
                log.append(
                    f"Master: true-peak limiter engaged (max "
                    f"{reduction_db:.1f} dB gain reduction at "
                    f"{TRUE_PEAK_CEILING_DBTP:g} dBTP ceiling)"
                )
            else:
                log.append("Master: true-peak limiter transparent (no peaks "
                           "over the ceiling)")
            # Limiting shaves a little loudness on peaky mixes — converge.
            lufs_after = integrated_loudness_blockwise(mix, sample_rate)
            if math.isfinite(lufs_after) and lufs_after < TARGET_LUFS - 0.2:
                makeup = min(2.0, TARGET_LUFS - lufs_after)
                mix *= np.float32(10.0 ** (makeup / 20.0))
                true_peak_limiter(mix, sample_rate)
                log.append(
                    f"Master: +{makeup:.1f} dB makeup after limiting, "
                    f"re-limited (loudness convergence)"
                )
        else:
            log.append("Master: studio mastering chain OFF — simple "
                       "normalize + peak protection only")
            lufs = integrated_loudness_blockwise(mix, sample_rate)
            if math.isfinite(lufs):
                master_gain_db = TARGET_LUFS - lufs
                mix *= np.float32(10.0 ** (master_gain_db / 20.0))
                log.append(
                    f"Master: {master_gain_db:+.1f} dB to reach {TARGET_LUFS:g} "
                    f"LUFS integrated (was {lufs:.1f})"
                )
        report(0.955, "Mastering: checking true peak…")
        peak_db = true_peak_dbtp(mix, sample_rate)
        if peak_db > TRUE_PEAK_CEILING_DBTP:
            mix *= np.float32(10.0 ** ((TRUE_PEAK_CEILING_DBTP - peak_db) / 20.0))
            log.append(
                f"Master: true peak {peak_db:.2f} dBTP over ceiling, "
                f"scaled down to {TRUE_PEAK_CEILING_DBTP:g} dBTP"
            )
            peak_db = TRUE_PEAK_CEILING_DBTP
        final_lufs = integrated_loudness_blockwise(mix, sample_rate)
    except Exception as exc:
        raise RenderError("(full mix)", stage, exc) from exc

    stage = "write"
    report(0.97, "Writing 24-bit WAV…")
    try:
        if mastering:
            tpdf_dither_inplace(mix, bits=24)
            log.append("Master: TPDF dither applied at 24-bit quantization")
        sf.write(str(output_path), mix, sample_rate, subtype="PCM_24")
    except Exception as exc:
        raise RenderError("(full mix)", stage, exc) from exc

    duration = len(mix) / sample_rate
    log.append(
        f"Wrote {output_path.name}: {format_duration(duration)}, "
        f"{final_lufs:.1f} LUFS integrated, true peak {peak_db:.2f} dBTP"
    )
    report(1.0, "Done")

    return {
        "output_path": str(output_path),
        "duration": duration,
        "integrated_lufs": final_lufs,
        "true_peak_dbtp": peak_db,
        "log": log,
    }
