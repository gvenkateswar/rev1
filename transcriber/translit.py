"""Romanize non-Latin transcript text into the Latin alphabet.

A transcript in Devanagari or Arabic script is only useful to someone who
reads that script. A romanization is the third rendering the reader gets: not
a translation (the words are unchanged) but a spelling of those same words in
letters they can sound out, which is what lets a non-reader follow along with
the audio and recognise names.

Romanization is done by uroman, ISI's universal romanizer: one API for every
script, rather than a different library per writing system that silently does
nothing for the script nobody wired up. It is script-driven, so it needs no
model and no network -- only its rule tables, loaded once and reused.
"""
from __future__ import annotations

import unicodedata

from .runtime import require

# uroman spends ~2.5s parsing its rule tables. That is once per process, not
# once per segment, so the loaded romanizer is cached at module scope the same
# way the Whisper models are.
_ROMANIZER = None


def needs_romanization(text: str) -> bool:
    """True if *text* contains a letter from a script other than Latin.

    Romanizing text that is already Latin produces the text back, so the point
    here is not correctness but restraint: a segment that needs no
    transliteration should carry none, and the reader should not be shown a
    second copy of a line they can already read.

    Unicode character names carry the script ("DEVANAGARI LETTER KA",
    "LATIN SMALL LETTER E WITH ACUTE"), which keeps accented Latin -- French,
    Vietnamese, Turkish -- correctly classified as Latin.
    """
    return any(
        ch.isalpha() and "LATIN" not in unicodedata.name(ch, "")
        for ch in text
    )


def romanize(text: str, language: str | None = None) -> str | None:
    """Latin transliteration of *text*, or None if it needs none.

    *language* is passed through as uroman's ``lcode``. uroman decides
    primarily from the script, so this is a hint rather than a requirement,
    and an unrecognised code is ignored rather than rejected.
    """
    if not text.strip() or not needs_romanization(text):
        return None
    return _romanizer().romanize_string(text, lcode=language).strip() or None


def _romanizer():
    global _ROMANIZER
    if _ROMANIZER is None:
        _ROMANIZER = require(
            "uroman",
            purpose="needed to transliterate non-Latin scripts",
            install="pip install uroman",
        ).Uroman()
    return _ROMANIZER
