"""Lay a metered sung phrase onto a matra grid.

Hindustani notation is rhythm-first: the handwritten notes this project's
correction rules come from write every bandish as a grid, one cell per matra,
vibhag bars between beat groups, an em-dash for a matra that sustains the
previous swara, and two letters in one cell when two notes share a matra.
A transcript that shows `S R G M P` flat has thrown that structure away.

But most of a lesson is *unmetered* — alaap by definition has no matra — and
laying an alaap on a grid would be inventing rhythm that is not there. So this
module first asks whether a phrase is metered at all: note onsets are tested
for a common pulse (vector strength of onset phases against a candidate
period), and only a phrase that locks confidently onto one gets a grid.

What is deliberately NOT claimed: where sam is. Finding beat one needs the
tabla theka, which we do not analyze. When a tala was named out loud in the
lesson we group the matras by that tala's vibhag pattern so the row *shape*
matches the notebook, and say the grouping is by mention, not by detection.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .swara import BHATKHANDE, Note, swara_label

# Matra counts and vibhag patterns, from the correction-rules tala table.
TALAS: dict[str, tuple[int, list[int]]] = {
    "Teentaal": (16, [4, 4, 4, 4]),
    "Tilwada": (16, [4, 4, 4, 4]),
    "Addha": (16, [4, 4, 4, 4]),
    "Ektaal": (12, [2, 2, 2, 2, 2, 2]),
    "Chautaal": (12, [2, 2, 2, 2, 2, 2]),
    "Jhaptaal": (10, [2, 3, 2, 3]),
    "Sooltaal": (10, [2, 2, 2, 2, 2]),
    "Rupak": (7, [3, 2, 2]),
    "Keherwa": (8, [4, 4]),
    "Dadra": (6, [3, 3]),
    "Dhamar": (14, [5, 2, 3, 4]),
    "Deepchandi": (14, [3, 4, 3, 4]),
    "Jhoomra": (14, [3, 4, 3, 4]),
}

SUSTAIN = "—"                # their notation: attack + held matras (N — — —)

_MIN_ONSETS = 6
_MIN_SPAN = 2.5              # seconds of phrase before a pulse claim
_PERIOD_LOW = 0.18           # 333 BPM: faster than any matra worth writing
_PERIOD_HIGH = 1.25          # 48 BPM: ati-vilambit territory
_CONFIDENCE_FLOOR = 0.70     # below this, the phrase is treated as unmetered


@dataclass
class Pulse:
    period: float            # seconds per matra
    offset: float            # time of a matra boundary
    confidence: float        # 0..1 vector strength of onsets against the grid

    @property
    def bpm(self) -> float:
        return 60.0 / self.period

    def to_dict(self) -> dict:
        return {
            "matra_seconds": round(self.period, 3),
            "bpm": round(self.bpm, 1),
            "confidence": round(self.confidence, 3),
        }


def detect_pulse(notes: list[Note]) -> Pulse | None:
    """Find the common pulse of a phrase's note onsets, if one exists.

    For each candidate period, every onset is mapped to its phase on that
    period and the phases are averaged as unit vectors: onsets that all land
    on the grid line up and the mean vector is long (strength near 1), while
    an alaap's free onsets point every way and cancel out. Harmonics of the
    true period also score high (onsets on every beat also lie on every half
    beat), so among near-tied candidates the *longest* period wins — the
    actual matra, not its subdivision.
    """
    onsets = np.array([n.start for n in notes], dtype=float)
    if len(onsets) < _MIN_ONSETS or onsets[-1] - onsets[0] < _MIN_SPAN:
        return None

    periods = np.geomspace(_PERIOD_LOW, _PERIOD_HIGH, 160)
    phases = np.exp(2j * np.pi * onsets[None, :] / periods[:, None])
    strengths = np.abs(phases.mean(axis=1))

    best = float(strengths.max())
    if best < _CONFIDENCE_FLOOR:
        return None
    near = strengths >= 0.92 * best
    period = float(periods[np.nonzero(near)[0][-1]])
    strength = float(strengths[np.nonzero(near)[0][-1]])

    mean_phase = np.angle(np.exp(2j * np.pi * onsets / period).mean())
    offset = float(mean_phase / (2 * np.pi) * period)
    return Pulse(period=period, offset=offset, confidence=strength)


def to_matra_grid(
    notes: list[Note],
    pulse: Pulse,
    tala: str | None = None,
    style: str = BHATKHANDE,
) -> list[str]:
    """Render notes on the pulse's grid, one avartan (or 16 matras) per row.

    Cell rules follow the notebook conventions: the swara goes in the matra
    its onset falls on, a matra the note is still sounding through gets the
    sustain dash, two onsets in one matra render together as a doublet, and
    a silent matra also gets the dash (the notation does not distinguish
    rest from sustain).
    """
    if not notes:
        return []

    def matra_of(t: float) -> int:
        return int(round((t - pulse.offset) / pulse.period))

    first = matra_of(notes[0].start)
    last = first
    cells: dict[int, list[str]] = {}
    held: dict[int, bool] = {}

    for note in notes:
        k = matra_of(note.start)
        cells.setdefault(k, []).append(swara_label(note.swara, note.octave, style))
        # A note is held through every further matra whose boundary it crosses.
        span = max(1, int(round(note.duration / pulse.period)))
        for extra in range(1, span):
            held.setdefault(k + extra, True)
        last = max(last, k + span - 1)

    row_len, vibhags = _row_shape(tala)
    rows: list[str] = []
    for row_start in range(first, last + 1, row_len):
        parts: list[str] = ["|"]
        filled = 0
        for boundary in vibhags:
            for i in range(boundary):
                k = row_start + filled + i
                if k in cells:
                    parts.append("".join(cells[k]))
                elif k in held or k <= last:
                    parts.append(SUSTAIN)
                else:
                    parts.append(SUSTAIN)
            parts.append("|")
            filled += boundary
        rows.append(" ".join(parts))
    return rows


def _row_shape(tala: str | None) -> tuple[int, list[int]]:
    if tala:
        for name, (matras, vibhags) in TALAS.items():
            if name.lower() == tala.lower():
                return matras, vibhags
    return 16, [4, 4, 4, 4]


def describe(pulse: Pulse, tala: str | None) -> str:
    """One line saying what the grid is and is not claiming."""
    line = (
        f"steady pulse ≈ {pulse.bpm:.0f} BPM "
        f"({pulse.period:.2f}s/matra, {pulse.confidence:.0%} lock)"
    )
    if tala and tala in TALAS:
        matras, _ = TALAS[tala]
        line += (
            f"; grouped as {tala} ({matras} matras) from the spoken mention — "
            f"sam not located, bars show grouping only"
        )
    return line
