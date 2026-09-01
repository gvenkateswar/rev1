"""Split a lesson into sung, spoken, drone and silent stretches.

This is the module that makes the tool worth building. Whisper is a *speech*
model: point it at two minutes of alaap and it will confidently emit sentences
nobody said — usually a stray line of Hindi film dialogue or a repeated
"thank you". So before transcribing we decide, from pitch alone, which parts of
the recording are singing, and we hand Whisper only the talking.

The discriminator is note-holding. Speech pitch moves constantly and rarely
parks: a syllable's f0 drifts through tens of cents and voiced runs are short.
Singing parks on a swara and stays there. So the feature that separates them is
the fraction of a window covered by *stable held notes*, which we already have
from :func:`~music_lesson.swara.segment_notes`.

The tanpura complicates this, because a drone is the most stable note of all.
It is separated by energy and by the fact that it never leaves Sa (or Pa).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .pitch import PitchTrack
from .swara import Note

SUNG = "sung"
SPOKEN = "spoken"
DRONE = "drone"
SILENT = "silent"

# How long a note must be held to count as a full sustain. Half a second is
# past any speech syllable and short of any sung swara worth naming.
_FULL_HOLD = 0.5

# Notes long enough to anchor the edge of a demonstration, and the shortest
# a trimmed region may become before we leave the original bounds alone.
_TRIM_HOLD = 0.3
_MIN_TRIMMED = 0.8


@dataclass
class Region:
    start: float
    end: float
    kind: str
    score: float = 0.0        # held-note fraction, the sung/spoken evidence

    @property
    def duration(self) -> float:
        return self.end - self.start

    def overlap(self, start: float, end: float) -> float:
        return max(0.0, min(self.end, end) - max(self.start, start))

    def to_dict(self) -> dict:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "kind": self.kind,
            "score": round(self.score, 3),
        }


def classify_regions(
    track: PitchTrack,
    notes: list[Note],
    tonic_hz: float,
    window: float = 1.0,
    hop: float = 0.25,
    sung_threshold: float = 0.50,
    min_sung: float = 1.2,
    min_spoken: float = 0.5,
) -> list[Region]:
    """Label the timeline as sung / spoken / drone / silent.

    *sung_threshold* is the singing score (see :func:`_classify_window`) above
    which a window counts as a demonstration. Raise it if spoken sargam ("sa
    re ga ma", said slowly) is being swallowed into demonstrations; lower it
    if quiet humming is being missed.
    """
    if len(track) == 0:
        return []

    duration = float(track.times[-1] + track.hop_s)
    starts = np.arange(0.0, max(duration - window, 0.0) + hop, hop)
    if len(starts) == 0:
        starts = np.array([0.0])

    silence_floor = _silence_floor(track)
    labels: list[str] = []
    scores: list[float] = []

    for start in starts:
        end = min(start + window, duration)
        label, score = _classify_window(
            track, notes, tonic_hz, float(start), float(end),
            silence_floor, sung_threshold,
        )
        labels.append(label)
        scores.append(score)

    labels = _smooth_labels(labels)
    regions = _merge_regions(labels, scores, starts, window, duration,
                             min_sung, min_spoken)
    return _trim_sung_regions(regions, notes)


def _silence_floor(track: PitchTrack) -> float:
    """An adaptive RMS floor: a fraction of the recording's typical loud frame."""
    if len(track) == 0:
        return 0.0
    loud = np.percentile(track.rms, 90)
    return float(max(loud * 0.06, 1e-4))


def _classify_window(
    track: PitchTrack,
    notes: list[Note],
    tonic_hz: float,
    start: float,
    end: float,
    silence_floor: float,
    sung_threshold: float,
    min_hold: float = 0.18,
) -> tuple[str, float]:
    """Score one window on four features and label it.

    No single feature is safe on its own. Length-weighted held-note coverage is
    the strongest, but a guru explaining slowly and deliberately parks on
    syllables too; the longest sustain in the window is hard to fake in speech
    but vanishes in a fast taan; a continuously voiced window is suggestive,
    but so is a long "aaaa" of thinking out loud; and swara alignment is
    decisive when it fires, yet only as good as the detected tonic. Together
    they separate a demonstration from an explanation with margin to spare —
    on synthetic material, roughly 0.45 for speech against 0.95 for singing.
    """
    sub = track.slice(start, end)
    span = max(end - start, 1e-6)
    if len(sub) == 0 or float(np.median(sub.rms)) < silence_floor:
        return SILENT, 0.0

    voiced_fraction = float(sub.voiced.mean())
    if voiced_fraction < 0.15:
        return SPOKEN, 0.0

    held = [
        n for n in notes
        if n.duration >= min_hold and n.overlap_seconds(start, end) > 0
    ]
    # Coverage, weighted by how long each note is held. Speech does produce
    # quasi-steady syllable nuclei of a quarter-second or so, and counting
    # those the same as a half-second sustain is what makes a lecture look
    # like an alaap. A note only counts fully once it is held _FULL_HOLD long.
    held_fraction = min(
        sum(
            n.overlap_seconds(start, end) * min(n.duration / _FULL_HOLD, 1.0)
            for n in held
        ) / span,
        1.0,
    )
    # The single longest note in the window: singing nearly always parks
    # somewhere, and no syllable of speech lasts as long as a sustained swara.
    longest = max((n.duration for n in held), default=0.0)
    sustain = float(np.clip(longest / _FULL_HOLD, 0.0, 1.0))
    # How continuously the voice is on — singing sustains, speech breathes.
    voiced_score = float(np.clip((voiced_fraction - 0.6) / 0.35, 0.0, 1.0))
    # How close the held pitches sit to actual swara positions. Speech parks
    # wherever it lands; a trained voice parks on the note.
    if held:
        mean_deviation = float(np.mean([abs(n.deviation) for n in held]))
        alignment = float(np.clip(1.0 - mean_deviation / 50.0, 0.0, 1.0))
    else:
        alignment = 0.0

    score = (
        0.50 * held_fraction + 0.20 * sustain
        + 0.15 * voiced_score + 0.15 * alignment
    )
    if score >= sung_threshold:
        if _is_drone(held, sub, track):
            return DRONE, score
        return SUNG, score
    return SPOKEN, score


def _is_drone(
    held: list[Note], window_track: PitchTrack, full_track: PitchTrack
) -> bool:
    """A held pitch that never moves off Sa/Pa and sits well below singing level.

    The tanpura is louder than nothing and quieter than a voice, so the energy
    test is against the recording's own loud percentile rather than an absolute.
    """
    if not held:
        return False
    if any(n.swara not in (0, 7) for n in held):
        return False
    voice_level = float(np.percentile(full_track.rms, 85))
    window_level = float(np.median(window_track.rms))
    return window_level < 0.35 * voice_level


def _smooth_labels(labels: list[str], radius: int = 2) -> list[str]:
    """Majority filter: a single stray window never flips a region on its own."""
    if len(labels) <= 2:
        return labels
    out: list[str] = []
    for i in range(len(labels)):
        lo, hi = max(0, i - radius), min(len(labels), i + radius + 1)
        window = labels[lo:hi]
        out.append(max(set(window), key=window.count))
    return out


def _merge_regions(
    labels: list[str],
    scores: list[float],
    starts: np.ndarray,
    window: float,
    duration: float,
    min_sung: float,
    min_spoken: float,
) -> list[Region]:
    """Collapse per-window labels into contiguous regions, then drop slivers."""
    regions: list[Region] = []
    cur_label = labels[0]
    cur_start = 0.0
    cur_scores = [scores[0]]

    for i in range(1, len(labels)):
        if labels[i] != cur_label:
            boundary = float(starts[i]) + window / 2
            regions.append(
                Region(cur_start, boundary, cur_label, float(np.mean(cur_scores)))
            )
            cur_label, cur_start, cur_scores = labels[i], boundary, [scores[i]]
        else:
            cur_scores.append(scores[i])
    regions.append(Region(cur_start, duration, cur_label, float(np.mean(cur_scores))))

    minimum = {SUNG: min_sung, SPOKEN: min_spoken, DRONE: min_sung, SILENT: 0.3}
    kept: list[Region] = []
    for region in regions:
        if region.duration < minimum.get(region.kind, 0.3) and kept:
            kept[-1].end = region.end          # absorb the sliver into its left neighbour
        elif kept and kept[-1].kind == region.kind:
            kept[-1].end = region.end
        else:
            kept.append(region)
    return [r for r in kept if r.duration > 0]


def _trim_sung_regions(
    regions: list[Region], notes: list[Note], pad: float = 0.15
) -> list[Region]:
    """Pull each sung region in to the notes actually held inside it.

    A one-second analysis window can only place a boundary to within half its
    own length, so a demonstration comes out with a second of the surrounding
    explanation attached at each end. That costs twice: the sargam picks up
    stray syllables, and Whisper never sees the speech that was swallowed. The
    held notes themselves are a far sharper boundary than the window grid, so
    the region is snapped to them and the reclaimed time is handed back to the
    neighbouring spoken stretch.
    """
    held = [n for n in notes if n.duration >= _TRIM_HOLD]
    if not held:
        return regions

    for i, region in enumerate(regions):
        if region.kind != SUNG:
            continue
        inside = [n for n in held if n.overlap_seconds(region.start, region.end) > 0]
        if not inside:
            continue
        start = max(region.start, inside[0].start - pad)
        end = min(region.end, inside[-1].end + pad)
        if end - start < _MIN_TRIMMED:
            continue
        if i > 0:
            regions[i - 1].end = start
        if i + 1 < len(regions):
            regions[i + 1].start = end
        region.start, region.end = start, end

    return [r for r in regions if r.duration > 0.05]


def speech_spans(
    regions: list[Region],
    pad: float = 0.25,
    merge_gap: float = 12.0,
    min_span: float = 0.6,
) -> list[tuple[float, float]]:
    """Spoken stretches to hand to Whisper, padded and coalesced.

    *merge_gap* is the important one, and it exists because of how Whisper
    costs out: every clip you hand it is padded to a full 30-second window
    before the encoder runs, so a 2-second clip costs exactly what a 30-second
    one does. A lesson that alternates "listen — *sings* — now you" every few
    seconds would otherwise be chopped into hundreds of clips and take longer
    than transcribing the whole recording twice over.

    So short sung interjections are decoded *through* rather than skipped
    (their output is discarded afterwards by the sung-region check in
    :mod:`music_lesson.core`), while long stretches of alaap — where
    hallucination is worst and the saving is real — are still excluded.
    """
    spans = [
        (max(0.0, r.start - pad), r.end + pad)
        for r in regions if r.kind == SPOKEN
    ]
    merged: list[tuple[float, float]] = []
    for start, end in spans:
        if merged and start - merged[-1][1] <= merge_gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    # A clip too short to hold a phrase is not worth an encoder pass of its own.
    return [(a, b) for a, b in merged if b - a >= min_span]


def region_at(regions: list[Region], start: float, end: float) -> Region | None:
    """The region with the most overlap of [start, end]."""
    best, best_overlap = None, 0.0
    for region in regions:
        overlap = region.overlap(start, end)
        if overlap > best_overlap:
            best, best_overlap = region, overlap
    return best
