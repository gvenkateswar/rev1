"""Tests for pipeline glue: speaker alignment and language/confidence labelling."""
from __future__ import annotations

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
