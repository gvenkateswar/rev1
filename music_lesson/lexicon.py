"""Hindustani vocabulary: bias Whisper toward it, then repair what it missed.

Whisper has heard very little Hindustani classical music. Left alone it turns
"bandish" into "band dish", "teentaal" into "tea total", "meend" into "mind",
and "Raag Yaman" into "raga man". Two passes fix most of it:

1. **Before decoding** the terms go into Whisper's ``initial_prompt``, which
   conditions the decoder toward that vocabulary — the cheapest accuracy win
   available for a domain model you cannot fine-tune.
2. **After decoding** we repair what still came out wrong: an explicit table of
   mishearings heard in real lessons, then a deliberately conservative fuzzy
   match against the term list. Every repair is recorded in the result so a
   wrong one can be spotted rather than silently believed.

Spoken sargam gets its own pass. Whisper renders "sa re ga ma pa" as "saw ray
gah ma pa" or worse, but a *run* of three or more solfège-shaped syllables is
almost never anything else, which makes the run — not the syllable — the safe
unit to normalize.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

RAGAS: tuple[str, ...] = (
    "Yaman", "Yaman Kalyan", "Bhairav", "Ahir Bhairav", "Nat Bhairav", "Bhairavi",
    "Bhupali", "Deshkar", "Bageshri", "Bihag", "Kedar", "Hamir", "Kamod",
    "Todi", "Multani", "Gujari Todi", "Bilaskhani Todi", "Madhuvanti",
    "Marwa", "Puriya", "Sohini", "Puriya Dhanashri", "Shree", "Basant", "Lalit",
    "Darbari Kanada", "Adana", "Jaunpuri", "Asavari", "Malkauns", "Chandrakauns",
    "Kafi", "Bhimpalasi", "Patdeep", "Dhani", "Khamaj", "Des", "Jhinjhoti",
    "Rageshri", "Tilak Kamod", "Durga", "Hamsadhwani", "Jog", "Shivaranjani",
    "Shuddha Sarang", "Vrindavani Sarang", "Miyan ki Malhar", "Gaud Malhar",
    "Megh", "Charukeshi", "Kirwani", "Jaijaiwanti", "Poorvi", "Shankara",
    "Bilawal", "Tilang", "Kalavati", "Nand", "Chhayanat", "Gorakh Kalyan",
)

TALAS: tuple[str, ...] = (
    "Teentaal", "Ektaal", "Jhaptaal", "Rupak", "Keherwa", "Dadra", "Deepchandi",
    "Jhoomra", "Tilwada", "Chautaal", "Addha", "Sooltaal", "Punjabi", "Dhamar",
)

# Technique, form and structure. The words a guru says fifty times a lesson.
TERMS: tuple[str, ...] = (
    "raag", "raga", "thaat", "swara", "sur", "shruti", "saptak", "sargam",
    "aroha", "avaroha", "pakad", "chalan", "vadi", "samvadi", "vivadi",
    "komal", "shuddha", "teevra", "mandra", "madhya", "taar",
    "alaap", "jod", "jhala", "vistaar", "badhat", "nyas", "aakar",
    "bandish", "cheez", "sthayi", "antara", "sanchari", "abhog", "mukhda",
    "khayal", "bada khayal", "chota khayal", "dhrupad", "dhamar", "thumri",
    "dadra", "tappa", "tarana", "bhajan", "lakshan geet", "sargam geet",
    "meend", "gamak", "kan", "murki", "khatka", "andolan", "sparsh",
    "taan", "sapaat taan", "gamak taan", "bol taan", "bol banao", "boltaan",
    "palta", "alankar", "paltas", "riyaz", "riyaaz", "sadhana",
    "sam", "khali", "bhari", "matra", "vibhag", "theka", "avartan", "tihai",
    "laya", "vilambit", "madhyalaya", "drut", "dugun", "tigun", "chaugun",
    "tanpura", "tambura", "sarangi", "harmonium", "tabla", "swarmandal",
    "gharana", "guru", "shishya", "bhaav", "rasa", "baithak", "taalim",
    "Gwalior", "Kirana", "Agra", "Jaipur Atrauli", "Patiala", "Mewati",
    "Rampur Sahaswan", "Indore", "Bhendibazaar",
)

# Mishearings observed in real lesson audio, or predictable from how Whisper
# segments Hindi loanwords. Applied literally and case-insensitively.
MISHEARINGS: dict[str, str] = {
    "tea total": "teentaal", "teen tal": "teentaal", "tin tal": "teentaal",
    "three taal": "teentaal", "teental": "teentaal", "tintal": "teentaal",
    "ache tal": "ektaal", "ek tal": "ektaal", "eck taal": "ektaal",
    "jap tal": "jhaptaal", "jhap tal": "jhaptaal", "roopak": "rupak",
    "band dish": "bandish", "bundish": "bandish",
    "sthai": "sthayi", "asthai": "sthayi",
    "aalap": "alaap", "alap": "alaap", "aalaap": "alaap",
    "vistar": "vistaar", "vistara": "vistaar",
    "mend": "meend",
    "gumuck": "gamak", "gamuck": "gamak", "gum ac": "gamak",
    "thans": "taans",
    "pull ta": "palta", "paltas": "paltas", "alankaar": "alankar",
    "raaga": "raag",
    "yeah man": "Yaman", "raga man": "Raag Yaman", "raag aman": "Raag Yaman",
    "yamun": "Yaman", "yamuna": "Yaman", "kalian": "Kalyan",
    "bhairvi": "Bhairavi",
    "boop ali": "Bhupali", "bhoopali": "Bhupali", "boopali": "Bhupali",
    "mal cows": "Malkauns", "malkosh": "Malkauns", "malkoshi": "Malkauns",
    "bag ashri": "Bageshri", "bageshree": "Bageshri", "bhageshri": "Bageshri",
    "bhim palasi": "Bhimpalasi", "bheem palasi": "Bhimpalasi",
    "durbari": "Darbari", "darbari kanhada": "Darbari Kanada",
    "comal": "komal", "kaumal": "komal",
    "tivra": "teevra", "tiwra": "teevra", "thivra": "teevra",
    "shudh": "shuddha", "shud": "shuddha", "sudh": "shuddha",
    "ria's": "riyaz", "riaz": "riyaz", "reyaz": "riyaz",
    "guru ji": "guruji", "gharaana": "gharana",
    "avroh": "avaroha", "aaroh": "aroha", "arohi": "aroha",
    "shrutis": "shrutis", "swar": "swara", "sware": "swara",
}

# The same job, for words that are also ordinary English. "I don't mind the
# sound" must survive untouched, so these apply only in a sentence that is
# already talking about music — a domain term, a raga name, or spoken sargam
# somewhere in the same sentence.
CONTEXT_MISHEARINGS: dict[str, str] = {
    "mind": "meend", "tan": "taan", "tans": "taans",
    "rag": "raag", "rug": "raag", "the alarm": "the alaap",
    "come all": "komal", "the some": "the sam", "bandage": "bandish",
    "by ravi": "Bhairavi", "bye ravi": "Bhairavi",
    "sum": "sam", "cheese": "cheez", "tar": "taar", "mothra": "matra",
}


# Solfège syllables and the ways Whisper spells them when it has no idea.
SARGAM_VARIANTS: dict[str, str] = {
    "sa": "Sa", "saa": "Sa", "say": "Sa", "sah": "Sa", "saw": "Sa", "so": "Sa",
    "re": "Re", "ray": "Re", "rey": "Re", "reh": "Re", "ri": "Re", "ree": "Re",
    "ga": "Ga", "gaa": "Ga", "gah": "Ga", "guh": "Ga", "ge": "Ga",
    "ma": "Ma", "maa": "Ma", "mah": "Ma", "muh": "Ma", "me": "Ma",
    "pa": "Pa", "paa": "Pa", "pah": "Pa", "puh": "Pa", "pe": "Pa",
    "dha": "Dha", "dhaa": "Dha", "da": "Dha", "duh": "Dha", "the": "Dha",
    "ni": "Ni", "nee": "Ni", "knee": "Ni", "ne": "Ni", "nih": "Ni",
}

# One-line glosses for the terms most likely to need one, used to build a
# lesson-specific glossary. Only terms a student would actually look up.
GLOSSES: dict[str, str] = {
    "raag": "the melodic framework: which swaras, in which shapes, with which mood",
    "thaat": "parent scale a raag is grouped under (ten in the Bhatkhande system)",
    "swara": "a note of the scale",
    "shruti": "microtonal shading of a swara — the cents your Ga sits off equal temperament",
    "saptak": "octave register: mandra (low), madhya (middle), taar (high)",
    "sargam": "solfège — Sa Re Ga Ma Pa Dha Ni",
    "aroha": "ascending line of the raag",
    "avaroha": "descending line of the raag",
    "pakad": "the catch-phrase that identifies the raag in a few notes",
    "vadi": "the most important swara of the raag",
    "samvadi": "the second most important swara, usually a fourth or fifth from the vadi",
    "komal": "flattened swara",
    "teevra": "sharpened Ma",
    "shuddha": "natural, unaltered swara",
    "alaap": "unmetered opening exploration of the raag, no tabla",
    "jod": "the section after alaap where a pulse enters, still without tabla",
    "vistaar": "gradual expansion of the raag, phrase by phrase",
    "nyas": "a resting note a phrase is allowed to settle on",
    "bandish": "the composed piece: fixed melody and lyrics set in a taal",
    "sthayi": "first section of a bandish, sitting in the lower and middle octave",
    "antara": "second section, moving into the upper octave",
    "mukhda": "the opening phrase of the bandish that lands on sam",
    "khayal": "the main vocal genre — a bandish plus improvisation",
    "dhrupad": "older, austere vocal genre with extended alaap",
    "thumri": "lighter semi-classical genre, text-driven and expressive",
    "tarana": "composition sung on rhythmic syllables instead of words",
    "meend": "a continuous glide between two swaras",
    "gamak": "a heavy oscillation on a swara",
    "kan": "a grace note touched on the way to the main swara",
    "murki": "a fast, light ornamental cluster",
    "khatka": "a sharp cluster of notes around the main swara",
    "andolan": "a slow, deliberate oscillation within a swara's shruti range",
    "taan": "a fast melodic run",
    "palta": "a permutation pattern practised across the scale",
    "alankar": "a melodic exercise pattern",
    "riyaz": "daily practice",
    "sam": "the first beat of the rhythmic cycle, where phrases land",
    "khali": "the unstressed section of the cycle, shown with a wave of the hand",
    "matra": "one beat of the cycle",
    "vibhag": "a division of the cycle",
    "theka": "the standard drum pattern of a taal",
    "avartan": "one full cycle of the taal",
    "tihai": "a phrase repeated three times so that it lands on sam",
    "laya": "tempo, and the sense of it",
    "vilambit": "slow tempo",
    "drut": "fast tempo",
    "dugun": "double the speed against the same cycle",
    "gharana": "a school of playing or singing, carried down a teaching lineage",
    "bol banao": "elaborating the words of a composition for meaning",
    "bhaav": "the emotional expression the phrase is meant to carry",
}

_MIN_FUZZY_LEN = 4
_FUZZY_CUTOFF = 0.87
_WORD_RE = re.compile(r"[A-Za-zऀ-ॿ']+")


@dataclass
class Correction:
    original: str
    replacement: str
    kind: str          # "mishearing" | "fuzzy" | "sargam"

    def to_dict(self) -> dict:
        return {"from": self.original, "to": self.replacement, "kind": self.kind}


def whisper_prompt(extra_terms: list[str] | None = None, limit: int = 60) -> str:
    """An ``initial_prompt`` that primes Whisper for a Hindustani lesson.

    Whisper truncates the prompt to its last 224 tokens, so the caller's own
    terms (`--raga Yaman`, a guru's name) go last, where they always survive.
    """
    core = [
        "raag", "swara", "sargam", "alaap", "bandish", "taan", "meend", "gamak",
        "sthayi", "antara", "vilambit", "drut", "teentaal", "ektaal", "laya",
        "komal", "teevra", "aroha", "avaroha", "pakad", "riyaz", "tanpura",
        "sa re ga ma pa dha ni sa",
    ]
    ragas = list(RAGAS[:limit - len(core)])
    words = core + ragas + [t for t in (extra_terms or []) if t]
    return (
        "A Hindustani classical music lesson in a mix of Hindi and English. "
        "Terms used: " + ", ".join(words) + "."
    )


def correct_text(text: str) -> tuple[str, list[Correction]]:
    """Repair domain vocabulary in *text*; return the text and what changed."""
    if not text.strip():
        return text, []

    corrections: list[Correction] = []
    working = _apply_mishearings(text, corrections)
    working = _apply_context_mishearings(working, corrections)
    working = _normalize_sargam_runs(working, corrections)
    working = _fuzzy_repair(working, corrections)
    return working, corrections


def gloss_for(term: str) -> str | None:
    """A one-line explanation of *term*, if we have one."""
    return GLOSSES.get(term.strip().lower())


def find_mentions(text: str) -> dict[str, list[str]]:
    """Ragas, talas and terms named in *text* — the transcript's own metadata.

    A guru saying "aaj Yaman karte hain" is better evidence of the raga than
    any pitch histogram, so this feeds straight into the lesson summary.
    """
    lowered = text.lower()
    found = {
        "ragas": [r for r in RAGAS if _contains_phrase(lowered, r.lower())],
        "talas": [t for t in TALAS if _contains_phrase(lowered, t.lower())],
        "terms": [t for t in TERMS if _contains_phrase(lowered, t.lower())],
    }
    # "Yaman Kalyan" implies "Yaman"; keep only the longest match of a family.
    found["ragas"] = _drop_subsumed(found["ragas"])
    return found


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _contains_phrase(lowered_text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", lowered_text) is not None


def _drop_subsumed(names: list[str]) -> list[str]:
    return [
        name for name in names
        if not any(other != name and name.lower() in other.lower() for other in names)
    ]


def _apply_mishearings(text: str, corrections: list[Correction]) -> str:
    """Longest phrases first, so 'darbari kanhada' beats 'darbari'."""
    for wrong in sorted(MISHEARINGS, key=len, reverse=True):
        right = MISHEARINGS[wrong]
        pattern = re.compile(rf"(?<![\w]){re.escape(wrong)}(?![\w])", re.IGNORECASE)
        if pattern.search(text):
            text = pattern.sub(right, text)
            corrections.append(Correction(wrong, right, "mishearing"))
    return text


def _apply_context_mishearings(text: str, corrections: list[Correction]) -> str:
    """Per sentence: repair ambiguous words only where the topic is clearly music."""
    pieces = re.split(r"([.!?।\n]+)", text)
    out: list[str] = []
    for piece in pieces:
        if _has_musical_context(piece):
            for wrong in sorted(CONTEXT_MISHEARINGS, key=len, reverse=True):
                right = CONTEXT_MISHEARINGS[wrong]
                pattern = re.compile(rf"(?<![\w]){re.escape(wrong)}(?![\w])", re.IGNORECASE)
                if pattern.search(piece):
                    piece = pattern.sub(right, piece)
                    corrections.append(Correction(wrong, right, "context"))
        out.append(piece)
    return "".join(out)


def _has_musical_context(sentence: str) -> bool:
    """True if the sentence names a raga, a tala, a technique, or sings sargam."""
    lowered = sentence.lower()
    for phrase in TERMS + RAGAS + TALAS:
        if _contains_phrase(lowered, phrase.lower()):
            return True
    words = [m.group().lower() for m in _WORD_RE.finditer(lowered)]
    run = 0
    for word in words:
        run = run + 1 if word in SARGAM_VARIANTS else 0
        if run >= 3:
            return True
    return False


def _normalize_sargam_runs(
    text: str, corrections: list[Correction], min_run: int = 3
) -> str:
    """Rewrite runs of >=3 solfège-shaped tokens as canonical sargam.

    One "so" is the English word. Three in a row — "so ray gah" — is a guru
    singing the scale, and the run length is what makes the call safe.
    """
    tokens = list(_WORD_RE.finditer(text))
    if len(tokens) < min_run:
        return text

    out = text
    run: list[re.Match] = []
    spans: list[tuple[int, int, str, str]] = []

    def flush() -> None:
        if len(run) >= min_run:
            start, end = run[0].start(), run[-1].end()
            canonical = " ".join(SARGAM_VARIANTS[m.group().lower()] for m in run)
            spans.append((start, end, text[start:end], canonical))

    for match in tokens:
        if match.group().lower() in SARGAM_VARIANTS:
            run.append(match)
        else:
            flush()
            run = []
    flush()

    for start, end, original, canonical in reversed(spans):
        if original != canonical:
            out = out[:start] + canonical + out[end:]
            corrections.append(Correction(original, canonical, "sargam"))
    return out


def _lexicon_words() -> list[str]:
    words: set[str] = set()
    for phrase in TERMS + RAGAS + TALAS:
        for word in phrase.split():
            if len(word) >= _MIN_FUZZY_LEN:
                words.add(word.lower())
    return sorted(words)


_LEXICON_WORDS = _lexicon_words()
# Ordinary English that sits close to a domain term. Never "corrected".
_PROTECTED = frozenset({
    "song", "sang", "sung", "sing", "sound", "round", "band", "bandage", "hand",
    "mind", "meant", "means", "meaning", "than", "then", "that", "than", "team",
    "time", "tune", "turn", "same", "some", "come", "came", "call", "tall",
    "raga", "ragas", "note", "notes", "name", "names", "part", "past", "last",
    "must", "just", "gum", "gun", "guru", "gurus", "sadhna", "match", "watch",
    "start", "stars", "smart", "stay", "star", "tan", "tans", "damage",
})


def _fuzzy_repair(text: str, corrections: list[Correction]) -> str:
    """Conservative last pass: only long, non-English tokens, only near matches."""
    def replace(match: re.Match) -> str:
        word = match.group()
        lowered = word.lower()
        if len(lowered) < _MIN_FUZZY_LEN or lowered in _PROTECTED:
            return word
        if lowered in _LEXICON_WORDS:
            return word
        candidates = difflib.get_close_matches(
            lowered, _LEXICON_WORDS, n=1, cutoff=_FUZZY_CUTOFF
        )
        if not candidates:
            return word
        replacement = candidates[0]
        if word[:1].isupper():
            replacement = replacement.capitalize()
        corrections.append(Correction(word, replacement, "fuzzy"))
        return replacement

    return _WORD_RE.sub(replace, text)
