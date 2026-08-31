"""Tests for pipeline glue: speaker alignment and language/confidence labelling."""
from __future__ import annotations

from transcriber import core
from transcriber.core import (
    TranscriptSegment, _attach_languages, _overlapping_raw, _ordered_speakers,
    assign_speakers,
)
from transcriber.diarize import Turn
from transcriber.language import LanguageSpan
from transcriber.transcribe import RawSegment, Word


def words(*specs):
    return [Word(start=s, end=e, text=t, probability=p)
            for s, e, t, p in specs]


def test_no_diarization_puts_everything_on_one_speaker():
    raw = [RawSegment(0, 2, "hello"), RawSegment(2, 4, "there")]
    out = assign_speakers(raw, [])
    assert {s.speaker for s in out} == {"Speaker 1"}


def test_whole_segment_vote_without_word_timestamps():
    raw = [RawSegment(0, 4, "hello there")]
    turns = [Turn(0, 1, "Speaker 1"), Turn(1, 4, "Speaker 2")]
    out = assign_speakers(raw, turns)
    assert len(out) == 1
    assert out[0].speaker == "Speaker 2"   # holds 3 of the 4 seconds


def test_segment_splits_when_the_speaker_changes_mid_sentence():
    raw = [RawSegment(0, 4, "hi there how are you", words(
        (0.0, 0.5, "hi", .9), (0.5, 1.0, " there", .9),
        (2.0, 2.5, " how", .9), (2.5, 3.0, " are", .9), (3.0, 3.5, " you", .9),
    ))]
    turns = [Turn(0, 1.5, "Speaker 1"), Turn(1.5, 4, "Speaker 2")]
    out = assign_speakers(raw, turns)
    assert [s.speaker for s in out] == ["Speaker 1", "Speaker 2"]
    assert out[0].text == "hi there"
    assert out[1].text == "how are you"


def test_one_word_flip_flop_is_merged_away():
    """A single stray word must not become its own speaker turn."""
    raw = [RawSegment(0, 3, "a b c", words(
        (0.0, 1.0, "a", .9), (1.0, 1.2, " b", .9), (1.2, 3.0, " c", .9)))]
    turns = [Turn(0, 1.0, "Speaker 1"), Turn(1.0, 1.2, "Speaker 2"),
             Turn(1.2, 3.0, "Speaker 1")]
    out = assign_speakers(raw, turns)
    assert len(out) == 1
    assert out[0].speaker == "Speaker 1"


def test_ordered_speakers_follows_first_appearance():
    segs = [TranscriptSegment(0, 1, "Rahul", "x"),
            TranscriptSegment(1, 2, "Priya", "y"),
            TranscriptSegment(2, 3, "Rahul", "z")]
    assert _ordered_speakers(segs) == ["Rahul", "Priya"]


# --- language + confidence labelling -------------------------------------- #
def test_attach_languages_labels_each_segment():
    segs = [TranscriptSegment(0, 10, "Speaker 1", "hello"),
            TranscriptSegment(40, 50, "Speaker 2", "namaste")]
    raw = [RawSegment(0, 10, "hello"), RawSegment(40, 50, "namaste")]
    spans = [LanguageSpan(0, 30, "en", 0.9), LanguageSpan(30, 60, "hi", 0.9)]
    _attach_languages(segs, raw, spans, default="en")
    assert [s.language for s in segs] == ["en", "hi"]


def test_attach_languages_falls_back_to_the_detected_language():
    segs = [TranscriptSegment(0, 10, "Speaker 1", "hello")]
    _attach_languages(segs, [RawSegment(0, 10, "hello")], [], default="fr")
    assert segs[0].language == "fr"


def test_confidence_is_carried_from_the_overlapping_raw_segment():
    """Speaker splitting means indexes don't line up; overlap must be used."""
    raw = [RawSegment(0, 5, "a", words((0, 5, "a", 0.4))),
           RawSegment(5, 10, "b", words((5, 10, "b", 0.9)))]
    segs = [TranscriptSegment(0, 2, "Speaker 1", "a"),
            TranscriptSegment(2, 5, "Speaker 2", "a2"),
            TranscriptSegment(5, 10, "Speaker 1", "b")]
    _attach_languages(segs, raw, [], default="en")
    assert [round(s.confidence, 2) for s in segs] == [0.4, 0.4, 0.9]


def test_overlapping_raw_returns_none_when_nothing_overlaps():
    seg = TranscriptSegment(100, 110, "Speaker 1", "x")
    assert _overlapping_raw(seg, [RawSegment(0, 5, "a")]) is None


def test_segment_confidence_uses_mean_word_probability():
    seg = RawSegment(0, 2, "hi", words((0, 1, "hi", 0.9), (1, 2, "there", 0.7)))
    assert round(seg.confidence, 3) == 0.8


def test_segment_confidence_falls_back_to_logprob():
    assert 0.7 < RawSegment(0, 1, "x", [], avg_logprob=-0.3).confidence < 0.75


def test_segment_confidence_is_clamped_to_one():
    assert RawSegment(0, 1, "x", [], avg_logprob=0.5).confidence == 1.0


# --------------------------------------------------------------------------- #
# Choosing a segment's language from its own audio
# --------------------------------------------------------------------------- #
def seg(start, end, text="x", language="hi"):
    return core.TranscriptSegment(start, end, "Speaker 1", text, language=language)


def test_a_confident_disagreement_overrides_the_span():
    """The case this exists for: an English question inside a Hindi stretch."""
    assert core._should_relanguage(seg(0, 6), ("en", 0.95)) is True


def test_agreement_with_the_span_changes_nothing():
    assert core._should_relanguage(seg(0, 6), ("hi", 0.99)) is False


def test_an_unsure_disagreement_defers_to_the_span():
    """The timeline saw far more audio than one segment carries."""
    assert core._should_relanguage(seg(0, 6), ("en", 0.55)) is False


def test_a_segment_too_short_to_judge_is_left_alone():
    assert core._should_relanguage(seg(0, 1.5), ("en", 0.99)) is False


def test_a_failed_detection_is_not_a_disagreement():
    assert core._should_relanguage(seg(0, 6), None) is False


# --------------------------------------------------------------------------- #
# Detecting a "transcript" that is really the translation
# --------------------------------------------------------------------------- #
def flagged(text, english, language="hi"):
    s = core.TranscriptSegment(0, 5, "S1", text, language=language, english=english)
    core._flag_missing_native_text([s])
    return s.native_is_english


def test_an_identical_pair_is_flagged():
    """Whisper base returned the translation for both renderings."""
    assert flagged("How do you earn Urfi?", "How do you earn Urfi?") is True


def test_a_nearly_identical_pair_is_flagged():
    """The real case: two English sentences differing in a few words."""
    assert flagged(
        "You keep watching on Instagram that you wear new clothes every "
        "time and you wear a sport.",
        "You keep watching on Instagram that you wear new clothes every "
        "time, and you are spotted.",
    ) is True


def test_a_real_transcript_and_its_translation_are_not_flagged():
    assert flagged("नमस्ते, आप कैसे हैं?", "Hello, how are you?") is False


def test_latin_script_languages_are_judged_on_the_words_not_the_script():
    """Spanish transcribed correctly reads nothing like its translation."""
    assert flagged("el gato está sobre la mesa", "the cat is on the table",
                   language="es") is False


def test_punctuation_and_case_cannot_hide_a_match():
    assert flagged("HOW DO YOU EARN URFI",
                   "How do you earn, Urfi?!") is True


def test_short_phrases_are_left_alone():
    """"ok"/"ok" is a coincidence, not evidence the model gave up."""
    assert flagged("Ok, thanks", "Ok, thanks") is False


def test_english_segments_are_never_flagged():
    assert flagged("How do you earn Urfi?", "How do you earn Urfi?",
                   language="en") is False


def test_a_segment_with_no_translation_is_never_flagged():
    """Nothing to compare against is not evidence of anything."""
    s = core.TranscriptSegment(0, 5, "S1", "some long enough text here",
                               language="hi", english=None)
    core._flag_missing_native_text([s])
    assert s.native_is_english is False


def test_the_result_counts_the_flagged_lines():
    good = core.TranscriptSegment(0, 5, "S1", "नमस्ते जी कैसे हैं आप",
                                  language="hi", english="Hello how are you")
    bad = core.TranscriptSegment(5, 9, "S1", "How do you earn Urfi?",
                                 language="hi", english="How do you earn Urfi?")
    core._flag_missing_native_text([good, bad])
    result = core.TranscriptResult(
        segments=[good, bad], language="hi", speakers=["S1"], source="m.wav")
    assert result.untranscribed_segments == 1


# --------------------------------------------------------------------------- #
# Speech that produced no segment at all
# --------------------------------------------------------------------------- #
def turn(start, end, speaker="Speaker 1"):
    return Turn(start, end, speaker)


def test_a_leading_stretch_with_no_segment_is_a_gap():
    """The reported case: two seconds of English before the first line."""
    segments = [seg(2, 10)]
    turns = [turn(0, 10)]
    assert core._uncovered_speech(segments, turns, 1.0) == [(0, 2)]


def test_a_gap_between_two_segments_is_found():
    segments = [seg(0, 4), seg(9, 15)]
    assert core._uncovered_speech(segments, [turn(0, 15)], 1.0) == [(4, 9)]


def test_a_trailing_stretch_is_found():
    assert core._uncovered_speech([seg(0, 8)], [turn(0, 12)], 1.0) == [(8, 12)]


def test_silence_is_never_a_gap():
    """Nobody spoke there, so there is nothing missing.

    Whisper handed silence invents text, so this filter is what keeps a
    fabricated line out of the transcript.
    """
    segments = [seg(0, 4), seg(20, 24)]
    turns = [turn(0, 4), turn(20, 24)]        # 4-20s is silence
    assert core._uncovered_speech(segments, turns, 1.0) == []


def test_a_pause_between_words_is_not_a_gap():
    segments = [seg(0, 4), seg(4.3, 9)]
    assert core._uncovered_speech(segments, [turn(0, 9)], 1.0) == []


def test_fully_covered_speech_has_no_gaps():
    assert core._uncovered_speech([seg(0, 10)], [turn(0, 10)], 1.0) == []


def test_no_diarization_means_no_gap_filling():
    """Without turns there is no evidence of speech, so nothing is invented."""
    assert core._uncovered_speech([seg(2, 10)], [], 1.0) == []


def test_overlapping_segments_do_not_manufacture_gaps():
    segments = [seg(0, 6), seg(4, 10)]
    assert core._uncovered_speech(segments, [turn(0, 10)], 1.0) == []


def test_gaps_are_found_across_several_speaker_turns():
    segments = [seg(0, 3), seg(10, 13)]
    turns = [turn(0, 5, "A"), turn(8, 15, "B")]
    assert core._uncovered_speech(segments, turns, 1.0) == [(3, 5), (8, 10), (13, 15)]


# --- _merge_intervals ------------------------------------------------------ #
def test_merging_joins_overlaps_and_sorts():
    assert core._merge_intervals([(5, 9), (0, 6)]) == [(0, 9)]


def test_merging_joins_touching_intervals():
    assert core._merge_intervals([(0, 4), (4, 8)]) == [(0, 8)]


def test_merging_drops_empty_intervals():
    assert core._merge_intervals([(3, 3), (0, 2)]) == [(0, 2)]


def test_merging_keeps_separate_intervals_apart():
    assert core._merge_intervals([(0, 2), (5, 7)]) == [(0, 2), (5, 7)]
