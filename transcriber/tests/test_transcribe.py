"""Tests for decoding helpers that do not need a model.

Span decoding hands Whisper a slice of the recording, so it gets back
slice-relative timestamps. Every stage after it -- diarization, speaker
alignment, the language timeline -- works in whole-recording time, so getting
the offset wrong silently misplaces every word in the file.
"""
from __future__ import annotations

import pytest

from transcriber.transcribe import RawSegment, Word, shift_segments


def test_segments_and_their_words_move_together():
    [out] = shift_segments(
        [RawSegment(0.0, 4.0, "hi", [Word(0.0, 1.0, "hi", 0.9)])], 30.0)
    assert (out.start, out.end) == (30.0, 34.0)
    assert (out.words[0].start, out.words[0].end) == (30.0, 31.0)


def test_shifting_leaves_everything_else_intact():
    [out] = shift_segments(
        [RawSegment(0.0, 4.0, "hi", [], avg_logprob=-0.5, no_speech_prob=0.1)], 5.0)
    assert out.text == "hi"
    assert out.avg_logprob == -0.5
    assert out.no_speech_prob == 0.1


def test_the_original_segments_are_not_mutated():
    """The first span starts at 0, so an in-place shift would look correct."""
    original = RawSegment(0.0, 4.0, "hi", [Word(0.0, 1.0, "hi", 0.9)])
    shift_segments([original], 30.0)
    assert original.start == 0.0
    assert original.words[0].start == 0.0


def test_a_zero_offset_changes_nothing():
    [out] = shift_segments([RawSegment(1.0, 2.0, "hi")], 0.0)
    assert (out.start, out.end) == (1.0, 2.0)


@pytest.mark.parametrize("offset", [0.5, 12.75, 3600.0])
def test_confidence_survives_the_shift(offset):
    [out] = shift_segments(
        [RawSegment(0, 2, "hi", [Word(0, 1, "a", 0.8), Word(1, 2, "b", 0.6)])],
        offset)
    assert out.confidence == pytest.approx(0.7)
