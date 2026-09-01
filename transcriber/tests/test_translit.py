"""Tests for Latin transliteration of non-Latin transcript text.

The script test is what keeps the feature quiet: a reader looking at English
or French should not be shown a second, identical-looking copy of the line.
"""
from __future__ import annotations

import pytest

from transcriber import runtime, translit


@pytest.mark.parametrize("text", [
    "नमस्ते",          # Devanagari
    "مرحبا",           # Arabic
    "你好",             # Han
    "Привет",          # Cyrillic
    "안녕하세요",        # Hangul
    "こんにちは",        # Kana
    "hello नमस्ते",     # mixed: one non-Latin letter is enough
])
def test_non_latin_scripts_are_detected(text):
    assert translit.needs_romanization(text) is True


@pytest.mark.parametrize("text", [
    "hello there",
    "Café Français",       # accented Latin is still Latin
    "Tiếng Việt",          # Vietnamese stacks marks, still Latin
    "Istanbul'da",
    "1234 -- !?",          # no letters at all
    "",
])
def test_latin_and_letterless_text_needs_nothing(text):
    assert translit.needs_romanization(text) is False


def test_romanize_declines_text_that_is_already_latin():
    """None, not a copy: the caller shows the field only when it adds something."""
    assert translit.romanize("hello there", "en") is None
    assert translit.romanize("   ", "hi") is None


def test_romanize_does_not_load_the_romanizer_for_latin_text(monkeypatch):
    """The uroman dependency is only needed by a run that has a script to romanize."""
    monkeypatch.setattr(translit, "_romanizer", lambda: 1 / 0)
    assert translit.romanize("plain english", "en") is None


def test_a_missing_uroman_is_reported_as_a_dependency_error(monkeypatch):
    monkeypatch.setattr(translit, "_ROMANIZER", None)

    def absent(name):
        raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    monkeypatch.setattr(runtime.importlib, "import_module", absent)
    with pytest.raises(RuntimeError) as err:
        translit.romanize("नमस्ते", "hi")
    assert "pip install uroman" in str(err.value)


# --------------------------------------------------------------------------- #
# Against the real romanizer, when it is installed
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text, language, expected", [
    ("नमस्ते", "hi", "namaste"),
    ("Привет", "ru", "Privet"),
    ("안녕하세요", "ko", "annyeonghaseyo"),
])
def test_real_romanization(text, language, expected):
    pytest.importorskip("uroman")
    assert translit.romanize(text, language) == expected


def test_punctuation_is_carried_through():
    pytest.importorskip("uroman")
    assert translit.romanize("नमस्ते, आप कैसे हैं?", "hi").endswith("?")
