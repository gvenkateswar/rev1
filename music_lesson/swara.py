"""Tonic (Sa) detection and swara segmentation.

Hindustani pitch is *relative*: every swara is an interval above whatever Sa
the singer chose that day. So the pipeline has two jobs here, in order:

1. **Find Sa.** Fold every voiced frame into a one-octave cents histogram and
   correlate it with a template of how a Hindustani performance actually
   distributes its time (heavy on Sa and Pa — the tanpura sits there and every
   phrase resolves there — and light on the tritone). The peak of that
   correlation is the tonic.
2. **Cut the pitch curve into notes.** A note is a run of frames that stays
   inside a narrow cents band; the runs are labelled with the nearest swara
   and the leftover cents deviation is kept, because that deviation is the
   musically interesting part (meend, andolan, a deliberately flat komal Ga).

Both steps work off :class:`~music_lesson.pitch.PitchTrack` and nothing else,
so they are testable with synthesized tones and carry no ML dependency.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .pitch import PitchTrack, cents_to_hz, hz_to_cents, median_filter

# Two display notations for the same (swara, octave) facts.
#
# BHATKHANDE matches the conventions of the user's handwritten-notes corpus
# (see the correction rules that project accumulated): komal is the letter
# underlined (combining low line), taar saptak is a dot above (precomposed
# forms where Unicode has them), mandra saptak is a dot below, and teevra Ma
# is M with an apostrophe. Shuddha letters are plain S R G M P D N.
#
# ASCII is the compact fallback: lowercase = komal, M = teevra Ma,
# .S = mandra, S' = taar.
BHATKHANDE = "bhatkhande"
ASCII = "ascii"

_KOMAL_LINE = "\u0332"      # combining low line (underline)
_TARA_DOT = "\u0307"        # combining dot above
_MANDRA_DOT = "\u0323"      # combining dot below

# Precomposed dot-above / dot-below letters, used where Unicode has them so
# the marks render identically everywhere. Note U+1E56 is TARA P by that
# corpus's convention, and no precomposed mandra P exists (rule: use P + dot).
_PRECOMPOSED_TARA = {
    "S": "\u1e60", "R": "\u1e58", "G": "\u0120", "M": "\u1e40",
    "P": "\u1e56", "D": "\u1e0a", "N": "\u1e44",
}
_PRECOMPOSED_MANDRA = {"S": "\u1e62", "R": "\u1e5a", "D": "\u1e0c", "N": "\u1e46"}

# Per semitone above Sa: (letter, is_komal, is_teevra).
_BHATKHANDE_BASE = [
    ("S", False, False), ("R", True, False), ("R", False, False),
    ("G", True, False), ("G", False, False), ("M", False, False),
    ("M", False, True), ("P", False, False), ("D", True, False),
    ("D", False, False), ("N", True, False), ("N", False, False),
]


def swara_label(swara: int, octave: int, style: str = BHATKHANDE) -> str:
    """Render one swara+octave in the requested notation."""
    if style == ASCII:
        base = SWARA_SHORT[swara]
        if octave < 0:
            return "." * (-octave) + base
        return base + "'" * octave

    letter, komal, teevra = _BHATKHANDE_BASE[swara]
    if octave == 1 and not komal and letter in _PRECOMPOSED_TARA:
        out = _PRECOMPOSED_TARA[letter]
    elif octave == -1 and not komal and letter in _PRECOMPOSED_MANDRA:
        out = _PRECOMPOSED_MANDRA[letter]
    elif octave > 0:
        out = letter + _TARA_DOT * octave
    elif octave < 0:
        out = letter + _MANDRA_DOT * (-octave)
    else:
        out = letter
    if komal:
        out += _KOMAL_LINE
    if teevra:
        out += "'"
    return out


# Swara names in Bhatkhande roman shorthand: lowercase = komal, uppercase =
# shuddha, M = teevra Ma. Index is semitones above Sa.
SWARA_SHORT = ["S", "r", "R", "g", "G", "m", "M", "P", "d", "D", "n", "N"]
SWARA_FULL = [
    "Sa", "komal Re", "Re", "komal Ga", "Ga", "Ma", "teevra Ma",
    "Pa", "komal Dha", "Dha", "komal Ni", "Ni",
]

# Relative time a typical Hindustani performance spends on each scale degree.
# Sa and Pa dominate (drone plus resolution), the tritone is rare in most
# ragas, so this template discriminates a real tonic from its fifth.
_TONIC_TEMPLATE = np.array(
    [3.0, 0.8, 1.4, 1.0, 1.4, 1.2, 0.5, 2.2, 0.8, 1.2, 0.9, 1.1]
)

# Western pitch-class names, only ever used to *report* the detected tonic in
# a form a harmonium or a tuner app understands.
_PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_A4_HZ = 440.0


@dataclass
class Note:
    """One held pitch: where it is, which swara it is, and how far off it sits."""

    start: float
    end: float
    swara: int              # semitones above Sa, 0..11
    octave: int             # -1 mandra, 0 madhya, +1 taar (and beyond)
    cents: float            # median cents above Sa, un-rounded
    deviation: float        # cents away from the 12-TET swara position
    confidence: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    def overlap_seconds(self, start: float, end: float) -> float:
        """Seconds this note shares with [start, end]."""
        return max(0.0, min(self.end, end) - max(self.start, start))

    @property
    def name(self) -> str:
        """Short ASCII name with register: `.S` mandra, `S` madhya, `S'` taar."""
        return swara_label(self.swara, self.octave, ASCII)

    def label(self, style: str = BHATKHANDE) -> str:
        return swara_label(self.swara, self.octave, style)

    @property
    def full_name(self) -> str:
        register = {-1: "mandra ", 0: "", 1: "taar "}.get(self.octave, "")
        return register + SWARA_FULL[self.swara]

    def to_dict(self) -> dict:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "swara": self.name,
            "swara_bhatkhande": swara_label(self.swara, self.octave),
            "swara_full": self.full_name,
            "cents": round(self.cents, 1),
            "deviation_cents": round(self.deviation, 1),
            "duration": round(self.duration, 3),
        }


@dataclass
class TonicEstimate:
    hz: float
    confidence: float       # 0..1, how sharply the template matched
    western: str            # e.g. "C#4 (+12c)"

    def to_dict(self) -> dict:
        return {
            "hz": round(self.hz, 2),
            "western": self.western,
            "confidence": round(self.confidence, 3),
        }


# --------------------------------------------------------------------------- #
# Tonic
# --------------------------------------------------------------------------- #
def detect_tonic(
    track: PitchTrack,
    notes: list["Note"] | None = None,
    search_low_hz: float = 100.0,
    search_high_hz: float = 320.0,
    bin_cents: float = 5.0,
) -> TonicEstimate:
    """Estimate Sa from the pitch distribution of the whole recording.

    Two musical facts do the work. First, time on a swara is not uniform: Sa
    and Pa carry the tanpura and every phrase resolves onto them, while the
    tritone is rare — that is the template we correlate against. Second,
    phrases *end* on nyas swaras, most often Sa, so the last note of each
    phrase is weighted double. Pauses between phrases help rather than hurt:
    with the singer silent, the tracker locks onto the drone, and those long
    steady runs land on Sa with a large duration weight.

    Pass *notes* from :func:`segment_notes` (run against any reference pitch —
    segmentation is tonic-independent) to use the note-based histogram; without
    it we fall back to a per-frame histogram.

    The search range covers the usual vocal Sa, roughly G2 to E4. The octave is
    cosmetic: everything downstream uses the tonic modulo 1200 cents.
    """
    hist, centres = (
        _note_histogram(notes, bin_cents) if notes
        else _frame_histogram(track, bin_cents)
    )
    if hist.sum() <= 0:
        return TonicEstimate(0.0, 0.0, "unknown")

    scores = np.zeros(len(hist))
    for k, weight in enumerate(_TONIC_TEMPLATE):
        shift = int(round(k * 100.0 / bin_cents))
        scores += weight * np.roll(hist, -shift)

    best = int(np.argmax(scores))
    confidence = _peak_confidence(scores, best, bin_cents)

    hz = cents_to_hz(centres[best], _HIST_REF_HZ)
    while hz < search_low_hz:
        hz *= 2.0
    while hz > search_high_hz:
        hz /= 2.0
    return TonicEstimate(float(hz), confidence, describe_hz(hz))


_HIST_REF_HZ = 55.0   # A1: an arbitrary but fixed anchor for cent folding


def _peak_confidence(scores: np.ndarray, best: int, bin_cents: float) -> float:
    """How clear the winner is versus the best *other* candidate.

    Rival peaks within a semitone are the same answer slightly detuned, so they
    are excluded; a genuine rival a fourth away is what should cost confidence.
    """
    exclude = int(round(80.0 / bin_cents))
    mask = np.ones(len(scores), dtype=bool)
    for offset in range(-exclude, exclude + 1):
        mask[(best + offset) % len(scores)] = False
    rival = scores[mask].max() if mask.any() else 0.0
    top = scores[best]
    if top <= 0:
        return 0.0
    return float(np.clip(1.0 - rival / top, 0.0, 1.0))


def _note_histogram(
    notes: list["Note"], bin_cents: float, phrase_gap: float = 0.25
) -> tuple[np.ndarray, np.ndarray]:
    """Octave-folded histogram of note durations, with a nyas (phrase-end) bonus."""
    n_bins = int(round(1200.0 / bin_cents))
    hist = np.zeros(n_bins)
    for i, note in enumerate(notes):
        is_last = i == len(notes) - 1 or notes[i + 1].start - note.end > phrase_gap
        weight = note.duration * (2.0 if is_last else 1.0)
        idx = int((note.cents % 1200.0) / bin_cents) % n_bins
        hist[idx] += weight
    return _circular_smooth(hist, 15.0 / bin_cents), np.arange(n_bins) * bin_cents


def _frame_histogram(
    track: PitchTrack, bin_cents: float
) -> tuple[np.ndarray, np.ndarray]:
    """Fallback: per-frame pitch-class histogram weighted by frame energy."""
    n_bins = int(round(1200.0 / bin_cents))
    hist = np.zeros(n_bins)
    if len(track) == 0 or not track.voiced.any():
        return hist, np.arange(n_bins) * bin_cents

    voiced = track.voiced
    cents = hz_to_cents(track.f0[voiced], _HIST_REF_HZ) % 1200.0
    weights = track.rms[voiced]
    weights = weights / (weights.max() + 1e-12)
    idx = np.clip((cents / bin_cents).astype(int), 0, n_bins - 1)
    np.add.at(hist, idx, weights)
    return _circular_smooth(hist, 15.0 / bin_cents), np.arange(n_bins) * bin_cents


def _circular_smooth(hist: np.ndarray, sigma_bins: float) -> np.ndarray:
    """Gaussian smoothing that wraps at the octave (a histogram of a circle)."""
    if sigma_bins <= 0:
        return hist
    radius = max(1, int(round(3 * sigma_bins)))
    x = np.arange(-radius, radius + 1)
    kernel = np.exp(-0.5 * (x / sigma_bins) ** 2)
    kernel /= kernel.sum()
    padded = np.concatenate([hist[-radius:], hist, hist[:radius]])
    return np.convolve(padded, kernel, mode="same")[radius:radius + len(hist)]


def describe_hz(hz: float) -> str:
    """Render a frequency as the nearest western note plus cents offset."""
    if hz <= 0:
        return "unknown"
    semitones = 12.0 * np.log2(hz / _A4_HZ)
    nearest = int(round(semitones))
    offset = (semitones - nearest) * 100.0
    name = _PITCH_CLASSES[(nearest + 9) % 12]
    octave = 4 + (nearest + 9) // 12
    return f"{name}{octave} ({offset:+.0f}c)"


def parse_tonic(value: str) -> float:
    """Parse a user-supplied tonic: `146.8`, `D3`, `C#4`, `Db3`.

    Musicians know their Sa (it is written on the harmonium), so an override
    is usually more reliable than any detector.
    """
    text = value.strip()
    try:
        hz = float(text)
        if hz > 0:
            return hz
        raise ValueError
    except ValueError:
        pass

    note = text[0].upper()
    if note not in "CDEFGAB":
        raise ValueError(f"Cannot parse tonic {value!r} (try 'C#3' or '138.6')")
    rest = text[1:]
    accidental = 0
    while rest[:1] in ("#", "b", "♯", "♭"):
        accidental += 1 if rest[0] in "#♯" else -1
        rest = rest[1:]
    try:
        octave = int(rest) if rest else 3
    except ValueError as exc:
        raise ValueError(f"Cannot parse tonic {value!r} (try 'C#3' or '138.6')") from exc

    base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[note]
    semitones_from_a4 = base + accidental + (octave - 4) * 12 - 9
    return float(_A4_HZ * 2.0 ** (semitones_from_a4 / 12.0))


# --------------------------------------------------------------------------- #
# Note segmentation
# --------------------------------------------------------------------------- #
def segment_notes(
    track: PitchTrack,
    tonic_hz: float,
    stability_cents: float = 45.0,
    min_duration: float = 0.08,
    smooth_frames: int = 5,
) -> list[Note]:
    """Cut a pitch curve into held notes.

    A note ends when the pitch leaves a *stability_cents* band around the run's
    running median — which is what separates a held Ga from a taan running past
    it. Runs shorter than *min_duration* are dropped: at speech tempo they are
    coarticulation, not notes.
    """
    if len(track) == 0 or tonic_hz <= 0:
        return []

    cents = hz_to_cents(track.f0, tonic_hz)
    cents = median_filter(cents, smooth_frames)
    notes: list[Note] = []

    run_start = -1
    run_values: list[float] = []
    run_conf: list[float] = []

    def close(end_idx: int) -> None:
        if run_start < 0 or not run_values:
            return
        start_t = float(track.times[run_start])
        end_t = float(track.times[min(end_idx, len(track.times) - 1)])
        if end_t - start_t < min_duration:
            return
        median_cents = float(np.median(run_values))
        swara, octave, deviation = classify_cents(median_cents)
        notes.append(
            Note(
                start=start_t, end=end_t, swara=swara, octave=octave,
                cents=median_cents, deviation=deviation,
                confidence=float(np.mean(run_conf)),
            )
        )

    for i, value in enumerate(cents):
        if np.isnan(value):
            close(i - 1)
            run_start, run_values, run_conf = -1, [], []
            continue
        if run_start < 0:
            run_start, run_values = i, [value]
            run_conf = [float(track.confidence[i])]
            continue
        if abs(value - float(np.median(run_values))) <= stability_cents:
            run_values.append(value)
            run_conf.append(float(track.confidence[i]))
        else:
            close(i - 1)
            run_start, run_values = i, [value]
            run_conf = [float(track.confidence[i])]
    close(len(cents) - 1)

    return _merge_repeated(notes)


def classify_cents(cents: float) -> tuple[int, int, float]:
    """Map cents-above-Sa to (swara index, octave, deviation in cents)."""
    semitone = int(np.floor(cents / 100.0 + 0.5))
    octave = int(np.floor(semitone / 12.0))
    swara = semitone - octave * 12
    deviation = cents - semitone * 100.0
    return swara, octave, float(deviation)


def _merge_repeated(notes: list[Note], gap: float = 0.06) -> list[Note]:
    """Join adjacent runs that landed on the same swara across a brief wobble."""
    merged: list[Note] = []
    for note in notes:
        prev = merged[-1] if merged else None
        same = (
            prev is not None
            and prev.swara == note.swara
            and prev.octave == note.octave
            and note.start - prev.end <= gap
        )
        if same:
            span = prev.duration + note.duration
            prev.cents = (prev.cents * prev.duration + note.cents * note.duration) / max(span, 1e-9)
            prev.deviation = prev.cents - (prev.octave * 12 + prev.swara) * 100.0
            prev.confidence = max(prev.confidence, note.confidence)
            prev.end = note.end
        else:
            merged.append(note)
    return merged


def sargam_line(
    notes: list[Note], max_notes: int = 64, style: str = BHATKHANDE
) -> str:
    """Render notes as a readable sargam phrase, e.g. ``N\u0332 R G M' D Ṡ``."""
    if not notes:
        return ""
    names = [n.label(style) for n in notes[:max_notes]]
    tail = " …" if len(notes) > max_notes else ""
    return " ".join(names) + tail


def swara_weights(notes: list[Note]) -> dict[int, float]:
    """Seconds spent on each swara (octave-folded) — the input to raga matching."""
    weights: dict[int, float] = {}
    for note in notes:
        weights[note.swara] = weights.get(note.swara, 0.0) + note.duration
    return weights
