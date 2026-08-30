"""Tests for the language timeline that drives code-switching."""
from __future__ import annotations

from transcriber.language import (
    LanguageSpan, _absorb_short_spans, _probes_to_spans, _require_confirmation,
    language_for, summarize,
)


def probe(start, end, lang, prob=0.95):
    return (start, end, lang, prob)


def spans_of(probes, duration, min_span=3.0):
    return [(s.language, s.start, s.end) for s in
            _probes_to_spans(probes, duration, min_span)]


def test_single_language_is_one_span():
    result = spans_of([probe(0, 30, "en"), probe(15, 45, "en")], 45)
    assert result == [("en", 0.0, 45.0)]


def test_confirmed_switch_is_kept():
    result = spans_of(
        [probe(0, 30, "en"), probe(15, 45, "en"),
         probe(30, 60, "hi"), probe(45, 75, "hi")], 75)
    assert [lang for lang, _, _ in result] == ["en", "hi"]


def test_single_window_flip_is_absorbed():
    """One window flipping (a loanword, a name) is not a language change."""
    result = spans_of(
        [probe(0, 30, "en"), probe(15, 45, "en"),
         probe(30, 60, "cy"), probe(45, 75, "en")], 75)
    assert result == [("en", 0.0, 75.0)]


def test_alternating_noise_collapses():
    result = spans_of(
        [probe(0, 30, "en"), probe(15, 45, "hi"),
         probe(30, 60, "en"), probe(45, 75, "hi")], 75)
    assert [lang for lang, _, _ in result] == ["en"]


def test_three_languages_each_confirmed():
    result = spans_of([
        probe(0, 30, "en"), probe(15, 45, "en"),
        probe(30, 60, "hi"), probe(45, 75, "hi"),
        probe(60, 90, "ta"), probe(75, 105, "ta"),
    ], 105)
    assert [lang for lang, _, _ in result] == ["en", "hi", "ta"]


def test_low_confidence_probe_inherits_previous_language():
    """Below the confidence floor the detector is guessing; don't switch."""
    result = spans_of(
        [probe(0, 30, "en"), probe(15, 45, "jw", prob=0.2),
         probe(30, 60, "en")], 60)
    assert result == [("en", 0.0, 60.0)]


def test_spans_cover_the_whole_recording():
    spans = _probes_to_spans(
        [probe(0, 30, "en"), probe(15, 45, "en")], duration=120.0, min_span=3.0)
    assert spans[0].start == 0.0
    assert spans[-1].end == 120.0


def test_no_probes_gives_no_spans():
    assert _probes_to_spans([], 60.0, 3.0) == []


def test_single_probe_file():
    assert spans_of([probe(0, 12, "fr")], 12) == [("fr", 0.0, 12.0)]


# --- _require_confirmation ------------------------------------------------ #
def test_confirmation_requires_two_consecutive():
    probes = [probe(0, 1, "en"), probe(1, 2, "hi"), probe(2, 3, "en")]
    assert [p[2] for p in _require_confirmation(probes, 2)] == ["en", "en", "en"]


def test_confirmation_accepts_a_real_run():
    probes = [probe(0, 1, "en"), probe(1, 2, "hi"), probe(2, 3, "hi")]
    assert [p[2] for p in _require_confirmation(probes, 2)] == ["en", "hi", "hi"]


def test_confirmation_disabled_passes_through():
    probes = [probe(0, 1, "en"), probe(1, 2, "hi")]
    assert _require_confirmation(probes, 1) == probes


def test_confirmation_on_empty_input():
    assert _require_confirmation([], 2) == []


# --- span helpers --------------------------------------------------------- #
def test_absorb_merges_neighbours_of_the_same_language():
    spans = [LanguageSpan(0, 10, "en", 0.9), LanguageSpan(10, 11, "hi", 0.9),
             LanguageSpan(11, 20, "en", 0.9)]
    merged = _absorb_short_spans(spans, min_span=3.0)
    assert len(merged) == 1
    assert merged[0].language == "en"
    assert (merged[0].start, merged[0].end) == (0, 20)


def test_language_for_picks_the_dominant_overlap():
    spans = [LanguageSpan(0, 30, "en", 0.9), LanguageSpan(30, 60, "hi", 0.9)]
    assert language_for(2, 8, spans) == "en"
    assert language_for(35, 50, spans) == "hi"
    assert language_for(28, 33, spans) == "hi"   # 2s en vs 3s hi


def test_language_for_without_spans_uses_the_default():
    assert language_for(0, 5, [], default="de") == "de"


def test_language_for_outside_every_span_uses_the_nearest():
    spans = [LanguageSpan(0, 30, "en", 0.9), LanguageSpan(30, 60, "hi", 0.9)]
    assert language_for(500, 505, spans) == "hi"


def test_summarize_totals_seconds_per_language():
    spans = [LanguageSpan(0, 30, "en", 0.9), LanguageSpan(30, 60, "hi", 0.9),
             LanguageSpan(60, 70, "en", 0.9)]
    assert summarize(spans) == {"en": 40.0, "hi": 30.0}


def test_summarize_orders_by_duration():
    spans = [LanguageSpan(0, 5, "hi", 0.9), LanguageSpan(5, 40, "en", 0.9)]
    assert list(summarize(spans)) == ["en", "hi"]
