"""Tests for rendering and the CLI's argument handling."""
from __future__ import annotations

import json

import pytest

from transcriber.cli import _parse_assignment
from transcriber.core import TranscriptResult, TranscriptSegment
from transcriber.output import render, to_summary, to_text


def result(**kw) -> TranscriptResult:
    base = dict(
        segments=[
            TranscriptSegment(0, 3, "Priya", "Good morning.", language="en",
                              confidence=0.95, known_speaker=True,
                              emotion="happy", emotion_score=0.82),
            TranscriptSegment(3, 7, "Speaker 2", "नमस्ते", language="hi",
                              confidence=0.88, emotion="neutral",
                              emotion_score=0.60),
        ],
        language="en", speakers=["Priya", "Speaker 2"], source="m.wav",
        languages={"en": 30.0, "hi": 12.0},
        identified={"Speaker 1": "Priya"},
    )
    base.update(kw)
    return TranscriptResult(**base)


def test_language_tags_appear_only_when_multilingual():
    assert "[hi]" in to_text(result())
    mono = result(languages={"en": 30.0}, segments=result().segments[:1])
    assert "[en]" not in to_text(mono)


def test_low_confidence_is_marked():
    r = result(segments=[TranscriptSegment(0, 2, "Priya", "mumble",
                                           confidence=0.41)])
    assert "low confidence 41%" in to_text(r)


def test_confident_segments_are_not_marked():
    assert "low confidence" not in to_text(result())


def test_low_confidence_marking_can_be_disabled():
    r = result(segments=[TranscriptSegment(0, 2, "Priya", "mumble",
                                           confidence=0.41)])
    assert "low confidence" not in to_text(r, mark_low_confidence=False)


def test_json_round_trips_with_the_new_fields():
    data = json.loads(render(result(), "json"))
    assert data["languages"] == {"en": 30.0, "hi": 12.0}
    assert data["identified"] == {"Speaker 1": "Priya"}
    seg = data["segments"][0]
    assert seg["language"] == "en"
    assert seg["known_speaker"] is True
    assert seg["confidence"] == 0.95


def test_json_omits_voiceprints():
    """Biometric vectors must never land in an exported transcript."""
    data = json.loads(render(result(voiceprints={"Priya": object()}), "json"))
    assert "voiceprints" not in data


def test_srt_and_vtt_render():
    srt, vtt = render(result(), "srt"), render(result(), "vtt")
    assert srt.startswith("1\n00:00:00,000 --> 00:00:03,000")
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:03.000" in vtt


def test_unknown_format_is_rejected():
    with pytest.raises(ValueError, match="Unknown output format"):
        render(result(), "pdf")


def test_summary_reports_languages_and_identities():
    summary = to_summary(result(
        unmatched={"Speaker 2": "below threshold"}))
    assert "Languages: en (30s), hi (12s)" in summary
    assert "Speaker 1 -> Priya" in summary
    assert "Speaker 2 (below threshold)" in summary


def test_empty_transcript_renders_without_error():
    empty = TranscriptResult(segments=[], language="en", speakers=[],
                             source="m.wav")
    assert to_text(empty) == ""
    assert json.loads(render(empty, "json"))["segments"] == []


# --- CLI argument parsing ------------------------------------------------- #
@pytest.mark.parametrize("raw,expected", [
    ("Speaker 1=Priya", ("Speaker 1", "Priya")),
    ("  Speaker 1 = Priya  ", ("Speaker 1", "Priya")),
    ("Speaker 1=A=B", ("Speaker 1", "A=B")),   # only the first = splits
])
def test_name_speaker_parsing(raw, expected):
    assert _parse_assignment(raw) == expected


@pytest.mark.parametrize("raw", ["Speaker 1", "=Priya", "Speaker 1=", ""])
def test_malformed_name_speaker_is_rejected(raw):
    with pytest.raises(ValueError):
        _parse_assignment(raw)


def test_name_speaker_implies_identification(monkeypatch):
    """--name-speaker needs voiceprints, which only the identify stage makes."""
    from transcriber import cli

    captured = {}

    def fake_transcribe_file(src, **kw):
        captured.update(kw)
        raise RuntimeError("stop here")

    monkeypatch.setattr(cli, "transcribe_file", fake_transcribe_file)
    cli.main(["audio.wav", "--no-identify",
              "--name-speaker", "Speaker 1=Priya"])
    assert captured["identify_speakers"] is True


def test_no_identify_alone_disables_identification(monkeypatch):
    from transcriber import cli

    captured = {}

    def fake_transcribe_file(src, **kw):
        captured.update(kw)
        raise RuntimeError("stop here")

    monkeypatch.setattr(cli, "transcribe_file", fake_transcribe_file)
    cli.main(["audio.wav", "--no-identify"])
    assert captured["identify_speakers"] is False


# --------------------------------------------------------------------------- #
# Three renderings in the rendered output
# --------------------------------------------------------------------------- #
def trilingual() -> TranscriptResult:
    return result(segments=[
        TranscriptSegment(0, 3, "Priya", "Good morning.", language="en",
                          confidence=0.95, emotion="happy", emotion_score=0.8),
        TranscriptSegment(3, 7, "Speaker 2", "नमस्ते", language="hi",
                          latin="namaste", english="greetings",
                          confidence=0.88, emotion="neutral",
                          emotion_score=0.6),
    ])


def test_text_shows_native_then_latin_then_english():
    lines = to_text(trilingual()).splitlines()
    assert lines[1].endswith("नमस्ते")
    assert lines[2].strip() == "[latin] namaste"
    assert lines[3].strip() == "[english] greetings"


def test_an_english_line_gains_no_extra_lines():
    """The common case must not cost the reader two blank-ish lines."""
    lines = to_text(trilingual()).splitlines()
    assert "[latin]" not in lines[0]
    assert "[english]" not in lines[0]


def test_renderings_reach_srt_and_vtt():
    for fmt in ("srt", "vtt"):
        out = render(trilingual(), fmt)
        assert "[latin] namaste" in out, fmt
        assert "[english] greetings" in out, fmt


def test_renderings_survive_json_round_trip():
    payload = json.loads(render(trilingual(), "json"))
    hindi = payload["segments"][1]
    assert (hindi["text"], hindi["latin"], hindi["english"]) == (
        "नमस्ते", "namaste", "greetings")
    assert payload["segments"][0]["latin"] is None


def test_a_segment_with_only_a_translation_shows_only_that():
    """Romanization off, translation on -- one extra line, not a blank one."""
    one = result(segments=[
        TranscriptSegment(0, 3, "S1", "नमस्ते", language="hi",
                          english="greetings")])
    lines = to_text(one).splitlines()
    assert len(lines) == 2
    assert lines[1].strip() == "[english] greetings"
