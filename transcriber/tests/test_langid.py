"""Tests for the two interchangeable language detectors.

The point of a second detector is that it can disagree, so what matters here
is that both speak the same vocabulary and report "no opinion" the same way.
A detector that returned a differently-shaped answer would silently skew every
threshold written against the other.
"""
from __future__ import annotations

import numpy as np
import pytest

from transcriber import langid

SPEECH = np.zeros(langid.SAMPLE_RATE * 3, dtype=np.float32)


class FakeWhisper:
    def __init__(self, result=None, raises=None):
        self.result, self.raises = result, raises

    def detect_language(self, audio=None, **kwargs):
        if self.raises:
            raise self.raises
        return self.result


# --------------------------------------------------------------------------- #
# Whisper's own
# --------------------------------------------------------------------------- #
def test_whisper_detection_is_reduced_to_code_and_probability():
    detector = langid.WhisperLanguageDetector(
        FakeWhisper(("hi", 0.97, [("hi", 0.97)])))
    assert detector.detect(SPEECH) == ("hi", 0.97)


@pytest.mark.parametrize("error", [RuntimeError("bad features"), ValueError()])
def test_a_chunk_the_model_cannot_read_is_no_opinion(error):
    """Silence can fail feature extraction; one bad chunk is not fatal."""
    detector = langid.WhisperLanguageDetector(FakeWhisper(raises=error))
    assert detector.detect(SPEECH) is None


def test_the_whisper_detector_names_itself():
    assert langid.WhisperLanguageDetector(FakeWhisper()).name == "whisper"


# --------------------------------------------------------------------------- #
# VoxLingua107 labels
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("label, expected", [
    ("hi: Hindi", "hi"),
    ("en: English", "en"),
    ("fr: French", "fr"),
    ("  UR : Urdu ", "ur"),
    ("zh", "zh"),                 # a bare code, should it ever appear
])
def test_voxlingua_labels_reduce_to_whisper_codes(label, expected):
    """Both detectors must speak one vocabulary, or no threshold written
    against Whisper's codes applies to the other."""
    assert langid.language_code(label) == expected


# --------------------------------------------------------------------------- #
# The factory
# --------------------------------------------------------------------------- #
def test_the_factory_builds_the_whisper_detector():
    detector = langid.make_detector("whisper", FakeWhisper(("en", 0.9, [])))
    assert isinstance(detector, langid.WhisperLanguageDetector)


def test_an_unknown_detector_is_rejected():
    with pytest.raises(ValueError, match="whisper or speechbrain"):
        langid.make_detector("magic", FakeWhisper())


def test_a_missing_speechbrain_is_reported_as_a_dependency_error(monkeypatch):
    from transcriber import runtime

    def absent(name):
        raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    monkeypatch.setattr(runtime.importlib, "import_module", absent)
    with pytest.raises(RuntimeError) as err:
        langid.make_detector("speechbrain", FakeWhisper())
    assert "pip install speechbrain" in str(err.value)


# --------------------------------------------------------------------------- #
# VoxLingua107 detection, against a stand-in for the classifier
# --------------------------------------------------------------------------- #
class FakeTensor:
    def __init__(self, value):
        self.value = value

    def squeeze(self, _dim):
        return self

    def max(self):
        return self

    def exp(self):
        return self

    def __float__(self):
        return float(self.value)


class FakeClassifier:
    """classify_batch returns (out_prob, score, index, text_lab)."""

    def __init__(self, label, probability):
        self.label, self.probability = label, probability
        self.seen = []

    def classify_batch(self, wav):
        self.seen.append(wav)
        return FakeTensor(self.probability), None, None, [self.label]


class FakeTorch:
    @staticmethod
    def from_numpy(array):
        class Wrapped:
            def unsqueeze(self, _dim):
                return array
        return Wrapped()


def test_voxlingua_detection_returns_a_code_and_a_probability():
    classifier = FakeClassifier("hi: Hindi", 0.93)
    detector = langid.VoxLinguaDetector(classifier, FakeTorch())
    assert detector.detect(SPEECH) == ("hi", pytest.approx(0.93))


def test_a_chunk_under_half_a_second_gets_no_opinion():
    """Too little audio to identify, and the classifier is not asked."""
    classifier = FakeClassifier("hi: Hindi", 0.93)
    detector = langid.VoxLinguaDetector(classifier, FakeTorch())
    assert detector.detect(np.zeros(4_000, dtype=np.float32)) is None
    assert classifier.seen == []


def test_an_empty_label_list_is_no_opinion():
    classifier = FakeClassifier("hi: Hindi", 0.9)
    classifier.classify_batch = lambda wav: (FakeTensor(0.9), None, None, [])
    detector = langid.VoxLinguaDetector(classifier, FakeTorch())
    assert detector.detect(SPEECH) is None


def test_the_voxlingua_detector_names_itself():
    assert langid.VoxLinguaDetector(None, None).name == "speechbrain"
