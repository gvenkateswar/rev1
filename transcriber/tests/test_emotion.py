"""Tests for language gating in emotion fusion.

The text model is English-only. Fed other languages it does not decline -- it
returns a confident wrong answer -- so these tests pin the gate that stops it.
"""
from __future__ import annotations

import numpy as np
import pytest

from transcriber.emotion import EmotionAnalyzer


@pytest.fixture
def analyzer(monkeypatch):
    """An analyzer whose text model records what it was asked to score."""
    scored: list[str] = []

    def fake_text_pipe(texts, **kw):
        scored.extend(texts)
        return [[{"label": "joy", "score": 0.9}] for _ in texts]

    a = EmotionAnalyzer(use_audio=False, use_text=True)
    monkeypatch.setattr(a, "_ensure_text", lambda: fake_text_pipe)
    a.scored = scored
    return a


def silence():
    return np.zeros(16_000, dtype=np.float32)


def test_english_text_is_scored(analyzer):
    analyzer.analyze_batch([(silence(), 16_000, "I am delighted")],
                           languages=["en"])
    assert analyzer.scored == ["I am delighted"]


def test_non_english_text_is_not_scored(analyzer):
    results = analyzer.analyze_batch(
        [(silence(), 16_000, "मैं बहुत खुश हूँ")], languages=["hi"])
    assert analyzer.scored == []
    assert "skipped" in results[0].text_raw
    assert "hi" in results[0].text_raw


def test_mixed_languages_score_only_the_english_ones(analyzer):
    analyzer.analyze_batch(
        [(silence(), 16_000, "hello"),
         (silence(), 16_000, "namaste"),
         (silence(), 16_000, "goodbye")],
        languages=["en", "hi", "en"],
    )
    assert analyzer.scored == ["hello", "goodbye"]


def test_without_languages_everything_is_scored(analyzer):
    """Callers that pass no languages keep the previous behaviour."""
    analyzer.analyze_batch([(silence(), 16_000, "hello"),
                            (silence(), 16_000, "bonjour")])
    assert analyzer.scored == ["hello", "bonjour"]


def test_empty_text_is_never_scored(analyzer):
    analyzer.analyze_batch([(silence(), 16_000, "   ")], languages=["en"])
    assert analyzer.scored == []


def test_analyze_passes_language_through(analyzer):
    analyzer.analyze(silence(), 16_000, "namaste", language="hi")
    assert analyzer.scored == []


def test_requires_at_least_one_channel():
    with pytest.raises(ValueError, match="at least one"):
        EmotionAnalyzer(use_audio=False, use_text=False)


def test_empty_batch():
    assert EmotionAnalyzer(use_audio=False).analyze_batch([]) == []
