"""Per-segment language detection for code-switching recordings.

faster-whisper's ``transcribe(multilingual=True)`` re-detects the language on
every 30s decode window, so a bilingual conversation *decodes* correctly. What
it does not do is report the result: ``Segment`` has no language field and
``info.language`` only reflects the first detection.

So we run our own detection pass over windows to build a language timeline,
collapse it into spans, and label each transcript segment by the language
spoken across it. This costs one encoder pass per window and no decoding.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import audio as _audio

# Whisper's own detection window. Using the same size means each probe sees
# exactly what a decode window would see.
#
# Shortening this to 10s was tried, to resolve turns too brief for a 30s probe
# to notice. It made transcription markedly worse and was reverted. Spans do
# not only label the audio, they are the units the decode runs on: more spans
# means shorter slices decoded in isolation, and Whisper needs context. A
# recording that decoded cleanly as one Hindi stretch came back as fragments.
# Language resolution and decode chunking are the same knob here, and decode
# quality is worth more than a boundary a few seconds sharper.
WINDOW_SECONDS = 30.0

# Overlap so a switch that lands mid-window is caught by the next probe.
HOP_SECONDS = 15.0

# Spans shorter than this are dropped as residue after smoothing.
MIN_SPAN_SECONDS = 3.0

# How many consecutive windows must agree before we accept a language switch.
# Overlapping windows flip on a loanword or a proper noun often enough that one
# probe is not evidence; a real switch persists across at least two.
MIN_CONSECUTIVE_PROBES = 2

# ...unless the detector is this sure. Confirmation exists to reject guesses,
# and a probe this confident is not one. Without the exemption a switch
# shorter than two hops can never occupy two probes and is unreachable. At a
# 30s window a lone probe this confident means half a minute of confidently
# different language, which is a real switch and not a loanword.
CONFIDENT_ENOUGH_ALONE = 0.85

# Below this confidence the detector is guessing; we carry the previous
# language through rather than introduce a spurious switch.
MIN_CONFIDENCE = 0.5


@dataclass
class LanguageSpan:
    """A contiguous stretch of audio detected as one language."""

    start: float
    end: float
    language: str
    confidence: float

    def overlap(self, start: float, end: float) -> float:
        return max(0.0, min(self.end, end) - max(self.start, start))


def detect_language_timeline(
    wav_path: str,
    model,
    *,
    window: float = WINDOW_SECONDS,
    hop: float = HOP_SECONDS,
    min_span: float = MIN_SPAN_SECONDS,
    max_windows: int = 240,
) -> list[LanguageSpan]:
    """Probe *wav_path* on a sliding window and return language spans.

    *model* is a loaded ``faster_whisper.WhisperModel``. *max_windows* caps the
    work on very long files (240 windows at a 15s hop covers an hour).
    """
    samples, sr = _audio.load_waveform(wav_path)
    duration = len(samples) / float(sr)
    if duration <= 0:
        return []

    probes: list[tuple[float, float, str, float]] = []
    starts = _window_starts(duration, window, hop, max_windows)
    for start in starts:
        end = min(start + window, duration)
        chunk = _audio.slice_waveform(samples, sr, start, end)
        # Whisper pads short input, but under ~1s there is nothing to go on.
        if len(chunk) < sr:
            continue
        detected = _detect_one(model, chunk)
        if detected is None:
            continue
        lang, prob = detected
        probes.append((start, end, lang, prob))

    if not probes:
        return []
    return _probes_to_spans(probes, duration, min_span)


def _window_starts(
    duration: float, window: float, hop: float, max_windows: int
) -> list[float]:
    if duration <= window:
        return [0.0]
    starts: list[float] = []
    t = 0.0
    while t < duration and len(starts) < max_windows:
        starts.append(t)
        t += hop
    return starts


def detect_one_language(model, chunk: np.ndarray) -> tuple[str, float] | None:
    """Public name for a single-chunk detection, used to re-check segments."""
    return _detect_one(model, chunk)


def _detect_one(model, chunk: np.ndarray) -> tuple[str, float] | None:
    """Detect the language of one chunk, or None if the model cannot."""
    try:
        lang, prob, _all = model.detect_language(
            audio=chunk.astype(np.float32), language_detection_segments=1
        )
    except (RuntimeError, ValueError):
        # A chunk of pure silence or noise can fail feature extraction. One bad
        # window should not abort detection for the whole recording.
        return None
    return str(lang), float(prob)


def _probes_to_spans(
    probes: list[tuple[float, float, str, float]],
    duration: float,
    min_span: float,
) -> list[LanguageSpan]:
    """Collapse overlapping window probes into contiguous language spans."""
    # Low-confidence probes carry the previous language forward instead of
    # asserting a switch the detector is not sure about.
    cleaned: list[tuple[float, float, str, float]] = []
    for start, end, lang, prob in probes:
        if prob < MIN_CONFIDENCE and cleaned:
            lang = cleaned[-1][2]
        cleaned.append((start, end, lang, prob))

    cleaned = _require_confirmation(cleaned, MIN_CONSECUTIVE_PROBES)

    spans: list[LanguageSpan] = []
    for start, end, lang, prob in cleaned:
        if spans and spans[-1].language == lang:
            spans[-1].end = max(spans[-1].end, end)
            spans[-1].confidence = max(spans[-1].confidence, prob)
        else:
            # Windows overlap, so start the new span where the last one ended
            # rather than double-covering the overlap region.
            begin = max(start, spans[-1].end) if spans else 0.0
            if spans and begin >= end:
                continue
            spans.append(LanguageSpan(begin, end, lang, prob))

    if spans:
        spans[0].start = 0.0
        spans[-1].end = max(spans[-1].end, duration)
    return _absorb_short_spans(spans, min_span)


def _require_confirmation(
    probes: list[tuple[float, float, str, float]], min_consecutive: int
) -> list[tuple[float, float, str, float]]:
    """Reject language switches not confirmed by *min_consecutive* probes.

    An unconfirmed probe is rewritten to the language currently in effect, so a
    lone flipped window disappears instead of becoming a span.
    """
    if min_consecutive <= 1 or not probes:
        return probes

    out = list(probes)
    current = out[0][2]
    i = 1
    while i < len(out):
        lang = out[i][2]
        if lang == current:
            i += 1
            continue
        # Count how many probes from here agree on the new language.
        run = 1
        while i + run < len(out) and out[i + run][2] == lang:
            run += 1
        confident = max(out[k][3] for k in range(i, i + run))
        if run >= min_consecutive or confident >= CONFIDENT_ENOUGH_ALONE:
            current = lang
            i += run
        else:
            for k in range(i, i + run):
                start, end, _lang, prob = out[k]
                out[k] = (start, end, current, prob)
            i += run
    return out


def _absorb_short_spans(
    spans: list[LanguageSpan], min_span: float
) -> list[LanguageSpan]:
    """Drop spans too short to be a real language change, then re-merge."""
    if len(spans) <= 1:
        return spans

    kept: list[LanguageSpan] = []
    for span in spans:
        if span.end - span.start < min_span and kept:
            # Hand the time to the previous span rather than deleting it.
            kept[-1].end = span.end
        else:
            kept.append(span)

    merged: list[LanguageSpan] = []
    for span in kept:
        if merged and merged[-1].language == span.language:
            merged[-1].end = span.end
            merged[-1].confidence = max(merged[-1].confidence, span.confidence)
        else:
            merged.append(span)
    return merged


def language_for(
    start: float, end: float, spans: list[LanguageSpan], default: str = "en"
) -> str:
    """The language covering the most of [start, end]."""
    if not spans:
        return default
    totals: dict[str, float] = {}
    for span in spans:
        got = span.overlap(start, end)
        if got > 0:
            totals[span.language] = totals.get(span.language, 0.0) + got
    if not totals:
        # A segment in a gap (all silence between spans) takes the nearest.
        nearest = min(
            spans,
            key=lambda s: min(abs(start - s.end), abs(end - s.start)),
        )
        return nearest.language
    return max(totals, key=totals.get)


def summarize(spans: list[LanguageSpan]) -> dict[str, float]:
    """Total seconds per language, for reporting which languages were heard."""
    totals: dict[str, float] = {}
    for span in spans:
        totals[span.language] = totals.get(span.language, 0.0) + (
            span.end - span.start
        )
    return dict(sorted(totals.items(), key=lambda kv: -kv[1]))


def describe_spans(spans: list[LanguageSpan]) -> str:
    """One-line summary of a timeline, for the stage log.

    e.g. "hi 0-45s (0.97), en 45-60s (0.88)". When a transcript comes out
    wrong this says whether the language was read correctly before the decode
    ever ran, which is otherwise invisible.
    """
    return ", ".join(
        f"{s.language} {s.start:.0f}-{s.end:.0f}s ({s.confidence:.2f})"
        for s in spans
    )
