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
STRETCH_SKIP_TOLERANCE = 0.005      # skip stretching within +/-0.5%

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
    """Return supported audio files in *folder* (non-recursive), alphabetical."""
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        raise NotADirectoryError(str(folder))
    files = [
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
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
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        tempo = float(np.atleast_1d(tempo)[0])
        if math.isfinite(tempo) and tempo > 10.0:
            detected_bpm = round(tempo, 1)
        # Beat positions (seconds, source-time) — used at render time to
        # phase-align crossfades so both tracks' beats coincide.
        beat_times = librosa.frames_to_time(beat_frames, sr=sr).astype(np.float32)
    except Exception:
        detected_bpm = None

    rms = librosa.feature.rms(
        y=y, frame_length=RMS_FRAME_LENGTH, hop_length=RMS_HOP_LENGTH
    )[0].astype(np.float32)

    return {
        "duration": duration,
        "detected_bpm": detected_bpm,
        "filename_bpm": parse_filename_bpm(path.name),
        "beats": beat_times,
        "rms_env": rms,
        "rms_hop": RMS_HOP_LENGTH,
        "rms_sr": ANALYSIS_SR,
    }


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


# ---------------------------------------------------------------------------
# Per-track processing stages
# ---------------------------------------------------------------------------

def load_track_stereo(path: Union[str, Path], sr: int = SAMPLE_RATE) -> np.ndarray:
    """Load at the common rate as float32 stereo, shape (n_samples, 2)."""
    y, _ = librosa.load(str(path), sr=sr, mono=False)
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

    def report(frac: float, msg: str) -> None:
        if progress is not None:
            progress(min(1.0, frac), msg)

    log: list[str] = []
    chunks: list[np.ndarray] = []   # committed mix audio
    pending: Optional[np.ndarray] = None  # last processed track, not yet committed
    prev_rate = 1.0
    prev_spec: Optional[dict] = None
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
        rate = float(output_bpm) / float(spec["bpm"])
        report(base + 0.3 * per_track_budget, f"Stretching track {i + 1} of {n}: {name}")
        try:
            audio, stretched = stretch_track(audio, rate, sample_rate)
        except Exception as exc:
            raise RenderError(name, stage, exc) from exc
        if stretched:
            log.append(
                f"{name}: stretched {spec['bpm']:g} -> {output_bpm:g} BPM "
                f"(x{1 / rate:.3f} duration, pitch preserved)"
            )
        else:
            log.append(f"{name}: stretch skipped (ratio within ±0.5%)")

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

                # Anchor: start the fade where the outgoing track's energy is
                # already in sustained decline (searched in its final ~45 s).
                # The decay time is found in source-time and mapped to
                # stretched-time by dividing by the stretch rate.
                decay_t = find_decay_onset_seconds(
                    prev_spec["rms_env"], prev_spec["rms_hop"], prev_spec["rms_sr"]
                )
                if decay_t is not None:
                    anchor = int(round(decay_t / prev_rate * sample_rate))
                    anchor_kind = "energy decay"
                else:
                    anchor = len(pending) - fade_n
                    anchor_kind = "end-aligned (no clear decay)"
                anchor = max(0, min(anchor, len(pending) - fade_n))

                # Snap the anchor onto the beat grid: both tracks are at the
                # output BPM, so shifting by at most half a beat makes their
                # beats coincide for the whole overlap. Beat times were
                # measured in source-time; divide by the stretch rate to get
                # positions in the stretched audio.
                out_beats = (
                    np.asarray(prev_spec.get("beats", []), dtype=np.float64)
                    / prev_rate * sample_rate
                )
                in_beats = (
                    np.asarray(spec.get("beats", []), dtype=np.float64)
                    / rate * sample_rate
                )
                in_first_beat = float(in_beats[0]) if len(in_beats) else None
                anchor, beat_shift = beat_aligned_anchor(
                    anchor, out_beats, in_first_beat, 0, len(pending) - fade_n
                )
                if beat_shift is None:
                    align_note = "not beat-aligned — no beat grid detected"
                else:
                    align_note = (
                        f"beat-aligned (anchor shifted "
                        f"{beat_shift / sample_rate * 1000:+.0f} ms)"
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
                    f"({anchor_kind}, {align_note})"
                )
                if dropped_s > 0.05:
                    msg += f", trimmed {dropped_s:.1f} s of quiet tail"
                log.append(msg)
        except Exception as exc:
            raise RenderError(name, stage, exc) from exc

        prev_rate = rate
        prev_spec = spec

    chunks.append(pending)
    mix = np.concatenate(chunks, axis=0)
    del chunks, pending

    stage = "master"
    report(0.92, "Mastering: measuring loudness…")
    try:
        lufs = integrated_loudness_blockwise(mix, sample_rate)
        if math.isfinite(lufs):
            master_gain_db = TARGET_LUFS - lufs
            mix *= np.float32(10.0 ** (master_gain_db / 20.0))
            log.append(
                f"Master: {master_gain_db:+.1f} dB to reach {TARGET_LUFS:g} LUFS "
                f"integrated (was {lufs:.1f})"
            )
        report(0.95, "Mastering: checking true peak…")
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
