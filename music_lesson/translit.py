"""Devanagari to readable Latin, for people who speak Hindi but read Roman.

Whisper writes Hindi in Devanagari. That is the right thing to store — it is
what was said — but a lesson transcript is something you read while singing,
and plenty of Hindi speakers read Roman faster than they read Devanagari. So
every Hindi segment gets a romanized companion line.

This is deliberately *not* scholarly ISO 15919: no macrons, no dots under
retroflexes. It targets the spelling a Hindi speaker would text — "raag",
"bandish", "khayaal" — because that is what makes a transcript skimmable.

The one piece of real linguistics here is schwa deletion. Devanagari writes an
inherent "a" after every consonant that Hindi often does not pronounce: the
spelling of "raag" is literally r-aa-g-a, and "sargam" is s-a-r-a-g-a-m-a. The
deletion rule runs right to left over the word, the standard formulation.
"""
from __future__ import annotations

from dataclasses import dataclass

DEVANAGARI_RANGE = ("ऀ", "ॿ")

_INDEPENDENT_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
    "ऑ": "o", "ऍ": "e",
}

# Vowel signs (matras). Each renders as a mark that attaches to the preceding
# consonant, so the comment names it: the key itself is nearly invisible here.
_MATRAS = {
    "ा": "aa",   # AA
    "ि": "i",    # I
    "ी": "ee",   # II
    "ु": "u",    # U
    "ू": "oo",   # UU
    "ृ": "ri",   # vocalic R
    "े": "e",    # E
    "ै": "ai",   # AI
    "ो": "o",    # O
    "ौ": "au",   # AU
    "ॉ": "o",    # CANDRA O
    "ॅ": "e",    # CANDRA E
}

_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "ळ": "l",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    # Precomposed nukta letters, common in the Urdu-derived vocabulary a guru
    # uses freely (riyaz, gazal, kaifiyat).
    "क़": "q", "ख़": "kh", "ग़": "gh", "ज़": "z",
    "ड़": "d", "ढ़": "dh", "फ़": "f",
}

# What a nukta turns each base consonant into, when the text is decomposed.
_NUKTA_FORMS = {"क": "q", "ख": "kh", "ग": "gh", "ज": "z", "ड": "d", "ढ": "dh", "फ": "f"}

_VIRAMA = "्"        # halant: kills the inherent vowel
_NUKTA = "़"
_ANUSVARA = "ं"
_CHANDRABINDU = "ँ"
_VISARGA = "ः"

# Conjuncts Hindi pronounces unpredictably from their parts.
_LIGATURES = {
    "ज" + _VIRAMA + "ञ": "gy",     # gya, not jnya
    "क" + _VIRAMA + "ष": "ksh",
    "त" + _VIRAMA + "र": "tr",
    "श" + _VIRAMA + "र": "shr",
}

# An anusvara before these reads as "m" rather than "n".
_LABIALS = frozenset("पफबभम")

_PUNCTUATION = {"।": ".", "॥": ".", "॰": "."}   # danda, double danda

_SENTINEL = "\x00"      # brackets a pre-expanded ligature inside a word


@dataclass
class _Syllable:
    consonant: str
    vowel: str
    inherent: bool          # True when the vowel is the unwritten schwa
    trailing: str = ""      # nasal / visarga attached after the vowel


def is_devanagari(text: str) -> bool:
    """True if *text* contains any Devanagari at all."""
    return any(DEVANAGARI_RANGE[0] <= ch <= DEVANAGARI_RANGE[1] for ch in text)


def devanagari_ratio(text: str) -> float:
    """Share of the letters in *text* that are Devanagari — a script detector.

    Whisper sometimes labels a code-switched segment "hi" while writing it in
    Latin (or the reverse), so the script actually used is the more reliable
    signal about which form the reader is getting.
    """
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    hits = sum(1 for ch in letters if DEVANAGARI_RANGE[0] <= ch <= DEVANAGARI_RANGE[1])
    return hits / len(letters)


def romanize(text: str) -> str:
    """Transliterate the Devanagari in *text*; leave everything else untouched."""
    if not is_devanagari(text):
        return text

    out: list[str] = []
    word: list[str] = []

    def flush() -> None:
        if word:
            out.append(_romanize_word("".join(word)))
            word.clear()

    for ch in text:
        if ch in _PUNCTUATION:
            flush()
            out.append(_PUNCTUATION[ch])
        elif DEVANAGARI_RANGE[0] <= ch <= DEVANAGARI_RANGE[1]:
            word.append(ch)
        else:
            flush()
            out.append(ch)
    flush()
    return "".join(out)


def _romanize_word(word: str) -> str:
    for ligature, replacement in _LIGATURES.items():
        word = word.replace(ligature, _SENTINEL + replacement + _SENTINEL)
    syllables = _parse(word)
    _delete_schwas(syllables)
    return "".join(s.consonant + s.vowel + s.trailing for s in syllables)


def _parse(word: str) -> list[_Syllable]:
    """Turn a Devanagari word into consonant+vowel syllables."""
    syllables: list[_Syllable] = []
    i = 0
    while i < len(word):
        ch = word[i]

        if ch == _SENTINEL:                         # pre-expanded ligature
            end = word.index(_SENTINEL, i + 1)
            consonant = word[i + 1:end]
            i = end + 1
        elif ch in _CONSONANTS:
            consonant = _CONSONANTS[ch]
            i += 1
            if i < len(word) and word[i] == _NUKTA:
                consonant = _NUKTA_FORMS.get(ch, consonant)
                i += 1
        elif ch in _INDEPENDENT_VOWELS:
            trailing, i = _read_trailing(word, i + 1)
            syllables.append(_Syllable("", _INDEPENDENT_VOWELS[ch], False, trailing))
            continue
        else:
            i += 1                                  # unknown mark: drop it
            continue

        vowel, inherent = _read_vowel(word, i)
        i += _vowel_width(word, i)
        trailing, i = _read_trailing(word, i)
        syllables.append(_Syllable(consonant, vowel, inherent, trailing))
    return syllables


def _read_vowel(word: str, i: int) -> tuple[str, bool]:
    """The vowel after a consonant: a matra, nothing (virama), or the schwa."""
    if i < len(word) and word[i] == _VIRAMA:
        return "", False
    if i < len(word) and word[i] in _MATRAS:
        return _MATRAS[word[i]], False
    return "a", True


def _vowel_width(word: str, i: int) -> int:
    return 1 if i < len(word) and (word[i] == _VIRAMA or word[i] in _MATRAS) else 0


def _read_trailing(word: str, i: int) -> tuple[str, int]:
    """Consume any nasal or visarga sitting after the vowel."""
    trailing = ""
    while i < len(word) and word[i] in (_ANUSVARA, _CHANDRABINDU, _VISARGA):
        if word[i] == _VISARGA:
            trailing += "h"
        else:
            following = word[i + 1] if i + 1 < len(word) else ""
            trailing += "m" if following in _LABIALS else "n"
        i += 1
    return trailing, i


def _delete_schwas(syllables: list[_Syllable]) -> None:
    """Apply Hindi schwa deletion right to left, in place.

    The word-final schwa always goes ("raaga" -> "raag"). A medial schwa goes
    when it sits between two consonants that both carry vowels of their own,
    which is what turns "saragama" into "sargam" — but never in the first
    syllable, where deleting it leaves an unpronounceable onset.
    """
    if not syllables:
        return

    last = syllables[-1]
    if last.inherent and last.consonant and not last.trailing:
        last.vowel = ""

    for idx in range(len(syllables) - 2, 0, -1):
        syllable = syllables[idx]
        if not (syllable.inherent and syllable.vowel and syllable.consonant):
            continue
        if syllable.trailing:
            continue
        previous, following = syllables[idx - 1], syllables[idx + 1]
        if not (previous.consonant and following.consonant):
            continue
        if not previous.vowel or not following.vowel:
            continue
        syllable.vowel = ""
        break        # one medial deletion per word is enough for Hindi
