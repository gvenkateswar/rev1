"""Integration test for transcribe_file's wiring.

The ML stages are stubbed, so this asserts the orchestration -- stage order,
label renaming, language/confidence propagation, temp-file cleanup -- rather
than model accuracy. Model quality is covered by the end-to-end check in
SPEC.md, which needs real audio.
"""
from __future__ import annotations

import numpy as np
import pytest

from transcriber import core
from transcriber.diarize import Turn
from transcriber.identify import ClusterVoiceprint
from transcriber.language import LanguageSpan
from transcriber.speakerdb import SpeakerStore, normalize
from transcriber.transcribe import RawSegment, Word

from .conftest import make_voice


@pytest.fixture
def stub_pipeline(monkeypatch, tmp_path):
    """Replace every stage that needs a model, ffmpeg, or real audio."""
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"fake")

    state = {"unlinked": []}
    monkeypatch.setattr(core._audio, "extract_audio", lambda src: str(wav))
    monkeypatch.setattr(core._audio, "audio_duration", lambda path: 60.0)
    monkeypatch.setattr(core, "load_model", lambda name: object())
    monkeypatch.setattr(
        core.os, "unlink", lambda p: state["unlinked"].append(p))

    native = [
        RawSegment(0, 4, "hello there", [
            Word(0, 1, "hello", 0.9), Word(1, 4, " there", 0.9)]),
        RawSegment(40, 44, "\u0928\u092e\u0938\u094d\u0924\u0947", [
            Word(40, 44, "\u0928\u092e\u0938\u094d\u0924\u0947", 0.5)]),
    ]

    def fake_spans(wav_path, spans, *, model, task="transcribe", **kw):
        state.setdefault("tasks", []).append((task, [s.language for s in spans]))
        if task == "translate":
            return [RawSegment(40, 44, "greetings")]
        return list(native)

    monkeypatch.setattr(core, "transcribe", lambda *a, **k: (list(native), "en"))
    monkeypatch.setattr(core, "transcribe_spans", fake_spans)
    monkeypatch.setattr(core, "diarize", lambda *a, **k: [
        Turn(0, 4, "Speaker 1"), Turn(40, 44, "Speaker 2")])
    monkeypatch.setattr(core, "detect_language_timeline", lambda *a, **k: [
        LanguageSpan(0, 30, "en", 0.95), LanguageSpan(30, 60, "hi", 0.93)])
    return state


def test_pipeline_produces_labelled_segments(stub_pipeline):
    result = core.transcribe_file("meeting.mp4", identify_speakers=False,
                                  detect_emotion=False)
    assert [s.speaker for s in result.segments] == ["Speaker 1", "Speaker 2"]
    assert [s.language for s in result.segments] == ["en", "hi"]
    assert result.is_multilingual
    assert result.languages == {"en": 30.0, "hi": 30.0}


def test_pipeline_reports_per_segment_confidence(stub_pipeline):
    result = core.transcribe_file("m.mp4", identify_speakers=False,
                                  detect_emotion=False)
    assert result.segments[0].confidence == pytest.approx(0.9)
    assert result.segments[1].confidence == pytest.approx(0.5)


def test_temp_audio_is_cleaned_up(stub_pipeline):
    core.transcribe_file("m.mp4", identify_speakers=False, detect_emotion=False)
    assert len(stub_pipeline["unlinked"]) == 1


def test_temp_audio_is_cleaned_up_even_when_a_stage_fails(
        stub_pipeline, monkeypatch):
    monkeypatch.setattr(core, "diarize", lambda *a, **k: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        core.transcribe_file("m.mp4", detect_emotion=False)
    assert len(stub_pipeline["unlinked"]) == 1


def test_pinning_a_language_skips_detection(stub_pipeline, monkeypatch):
    """A pinned language must not pay for the detection pass."""
    called = []
    monkeypatch.setattr(core, "detect_language_timeline",
                        lambda *a, **k: called.append(1) or [])
    result = core.transcribe_file("m.mp4", language="en",
                                  identify_speakers=False, detect_emotion=False)
    assert called == []
    assert "language" not in result.timings
    assert all(s.language == "en" for s in result.segments)


def test_known_speaker_is_named_from_the_store(stub_pipeline, monkeypatch,
                                               tmp_path, rng):
    """The headline behaviour: an enrolled voice is recognised by name."""
    voice = make_voice(rng)
    db = tmp_path / "speakers.db"
    with SpeakerStore(db) as store:
        store.enroll("Priya", voice)

    monkeypatch.setattr(core, "_identify_speakers", core._identify_speakers)
    monkeypatch.setattr(
        "transcriber.identify.extract_voiceprints",
        lambda wav, turns, **k: [
            ClusterVoiceprint("Speaker 1", normalize(voice), 30.0),
            ClusterVoiceprint("Speaker 2", make_voice(rng), 20.0),
        ],
    )

    result = core.transcribe_file("m.mp4", speaker_db=str(db),
                                  detect_emotion=False)
    assert result.identified == {"Speaker 1": "Priya"}
    assert [s.speaker for s in result.segments] == ["Priya", "Speaker 2"]
    assert result.segments[0].known_speaker is True
    assert result.segments[1].known_speaker is False
    # Voiceprints are keyed by the label shown, so naming works off the transcript.
    assert set(result.voiceprints) == {"Priya", "Speaker 2"}
    assert "Speaker 2" in result.unmatched


def test_identification_can_be_disabled(stub_pipeline, tmp_path, rng):
    db = tmp_path / "speakers.db"
    with SpeakerStore(db) as store:
        store.enroll("Priya", make_voice(rng))
    result = core.transcribe_file("m.mp4", speaker_db=str(db),
                                  identify_speakers=False, detect_emotion=False)
    assert result.identified == {}
    assert result.segments[0].speaker == "Speaker 1"


def test_emotion_receives_per_segment_languages(stub_pipeline, monkeypatch):
    """Non-English segments must reach the analyzer tagged, so it can skip
    the English-only text model instead of scoring foreign text."""
    seen = {}

    class FakeAnalyzer:
        def __init__(self, **kw):
            pass

        def analyze_batch(self, items, languages=None):
            seen["languages"] = languages
            return [type("R", (), {
                "label": "neutral", "score": 0.5, "scores": {},
                "audio_label": None, "text_label": None,
                "audio_raw": None, "text_raw": None})() for _ in items]

    monkeypatch.setattr("transcriber.emotion.EmotionAnalyzer", FakeAnalyzer)
    monkeypatch.setattr(core._audio, "load_waveform",
                        lambda p: (np.zeros(16000 * 60, dtype=np.float32), 16000))
    core.transcribe_file("m.mp4", identify_speakers=False, detect_emotion=True)
    assert seen["languages"] == ["en", "hi"]


def test_dominant_language_wins_over_first_detected(stub_pipeline, monkeypatch):
    """A file that opens in one language but is mostly another reports the
    language actually spoken most, not whichever Whisper saw first."""
    monkeypatch.setattr(core, "detect_language_timeline", lambda *a, **k: [
        core.LanguageSpan(0, 5, "en", 0.9),      # short English greeting
        core.LanguageSpan(5, 300, "hi", 0.95),   # the rest is Hindi
    ])
    result = core.transcribe_file("m.mp4", identify_speakers=False,
                                  detect_emotion=False)
    assert result.language == "hi"
    assert list(result.languages) == ["hi", "en"]


# --------------------------------------------------------------------------- #
# Three renderings: native script, Latin transliteration, English translation
# --------------------------------------------------------------------------- #
NAMASTE = "नमस्ते"


def test_native_script_survives_the_pipeline(stub_pipeline):
    """The reported bug: non-English speech came back written in English."""
    result = core.transcribe_file("m.mp4", identify_speakers=False,
                                  detect_emotion=False)
    assert result.segments[1].text == NAMASTE


def test_translation_only_decodes_the_non_english_spans(stub_pipeline):
    core.transcribe_file("m.mp4", identify_speakers=False, detect_emotion=False)
    assert stub_pipeline["tasks"] == [
        ("transcribe", ["en", "hi"]),
        ("translate", ["hi"]),      # the English span is not decoded twice
    ]


def test_translation_lands_on_the_segment_it_overlaps(stub_pipeline):
    result = core.transcribe_file("m.mp4", identify_speakers=False,
                                  detect_emotion=False)
    assert result.segments[0].english is None      # already English
    assert result.segments[1].english == "greetings"


def test_transliteration_fills_latin_for_non_latin_script_only(stub_pipeline):
    pytest.importorskip("uroman")
    result = core.transcribe_file("m.mp4", identify_speakers=False,
                                  detect_emotion=False)
    assert result.segments[0].latin is None        # already Latin
    assert result.segments[1].latin == "namaste"


def test_both_renderings_can_be_turned_off(stub_pipeline):
    result = core.transcribe_file("m.mp4", identify_speakers=False,
                                  detect_emotion=False,
                                  transliterate=False, translate=False)
    assert all(s.latin is None for s in result.segments)
    assert all(s.english is None for s in result.segments)
    assert [t for t, _ in stub_pipeline["tasks"]] == ["transcribe"]


def test_an_english_recording_pays_for_no_translation_pass(
        stub_pipeline, monkeypatch):
    monkeypatch.setattr(core, "detect_language_timeline", lambda *a, **k: [
        LanguageSpan(0, 60, "en", 0.95)])
    core.transcribe_file("m.mp4", identify_speakers=False, detect_emotion=False)
    assert [t for t, _ in stub_pipeline["tasks"]] == ["transcribe"]
    assert "translate" not in core.transcribe_file(
        "m.mp4", identify_speakers=False, detect_emotion=False).timings


def test_renderings_are_serialized(stub_pipeline):
    pytest.importorskip("uroman")
    result = core.transcribe_file("m.mp4", identify_speakers=False,
                                  detect_emotion=False)
    payload = result.segments[1].to_dict()
    assert payload["text"] == NAMASTE
    assert payload["latin"] == "namaste"
    assert payload["english"] == "greetings"
