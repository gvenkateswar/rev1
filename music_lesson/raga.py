"""Name the scale a demonstration sits in.

A pitch histogram tells you which swaras were used; it cannot tell you a raga.
Ragas that share a scale differ by phrase shape, by which note you rest on, by
which direction you approach a note from — Bhimpalasi and Kafi share every
note, and no amount of counting pitch classes will separate them.

So this module claims only what the evidence supports. It reports the **thaat**
(the ten-parent-scale classification, which *is* a set of swaras and therefore
*is* decidable from pitch), it flags an exact match against the common
pentatonic and hexatonic ragas (where the note set really is distinctive), and
it lists the ragas of that thaat as candidates rather than an answer.

The transcript then does the disambiguating that pitch cannot: gurus say the
name of the raga out loud, constantly. :mod:`music_lesson.lexicon` catches
those mentions and :mod:`music_lesson.output` cross-references them here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .swara import SWARA_SHORT

# The ten Bhatkhande thaats as sets of semitones above Sa.
THAATS: dict[str, frozenset[int]] = {
    "Bilawal": frozenset({0, 2, 4, 5, 7, 9, 11}),
    "Khamaj": frozenset({0, 2, 4, 5, 7, 9, 10}),
    "Kafi": frozenset({0, 2, 3, 5, 7, 9, 10}),
    "Asavari": frozenset({0, 2, 3, 5, 7, 8, 10}),
    "Bhairavi": frozenset({0, 1, 3, 5, 7, 8, 10}),
    "Bhairav": frozenset({0, 1, 4, 5, 7, 8, 11}),
    "Kalyan": frozenset({0, 2, 4, 6, 7, 9, 11}),
    "Marwa": frozenset({0, 1, 4, 6, 7, 9, 11}),
    "Poorvi": frozenset({0, 1, 4, 6, 7, 8, 11}),
    "Todi": frozenset({0, 1, 3, 6, 7, 8, 11}),
}

# Ragas commonly taught out of each thaat. Not exhaustive — a starting point
# for "which of these does it sound like?", which is the question a student
# actually asks.
THAAT_RAGAS: dict[str, tuple[str, ...]] = {
    "Bilawal": ("Bilawal", "Deshkar", "Shankara", "Durga", "Bhupali"),
    "Khamaj": ("Khamaj", "Des", "Rageshri", "Tilak Kamod", "Jhinjhoti", "Bihag"),
    "Kafi": ("Kafi", "Bageshri", "Bhimpalasi", "Patdeep", "Dhani", "Miyan ki Malhar"),
    "Asavari": ("Asavari", "Jaunpuri", "Darbari Kanada", "Adana", "Gandhari"),
    "Bhairavi": ("Bhairavi", "Malkauns", "Bilaskhani Todi", "Komal Rishabh Asavari"),
    "Bhairav": ("Bhairav", "Ahir Bhairav", "Nat Bhairav", "Gunkali", "Jogiya"),
    "Kalyan": ("Yaman", "Yaman Kalyan", "Bhupali", "Shuddha Kalyan", "Kedar", "Hamir"),
    "Marwa": ("Marwa", "Puriya", "Sohini", "Bhatiyar"),
    "Poorvi": ("Poorvi", "Puriya Dhanashri", "Basant", "Shree", "Lalit"),
    "Todi": ("Todi", "Multani", "Gujari Todi", "Madhuvanti"),
}

# Ragas whose *note set alone* is distinctive enough to name. An exact match
# here is a much stronger claim than a thaat.
DISTINCTIVE_RAGAS: dict[str, frozenset[int]] = {
    "Bhupali": frozenset({0, 2, 4, 7, 9}),
    "Deshkar": frozenset({0, 2, 4, 7, 9}),
    "Malkauns": frozenset({0, 3, 5, 8, 10}),
    "Durga": frozenset({0, 2, 5, 7, 9}),
    "Hamsadhwani": frozenset({0, 2, 4, 7, 11}),
    "Chandrakauns": frozenset({0, 3, 5, 8, 11}),
    "Megh": frozenset({0, 2, 5, 7, 10}),
    "Jog": frozenset({0, 3, 4, 5, 7, 10}),
    "Shivaranjani": frozenset({0, 2, 3, 7, 9}),
    "Kalavati": frozenset({0, 4, 7, 9, 10}),
    "Bageshri": frozenset({0, 3, 5, 7, 9, 10}),
    "Dhani": frozenset({0, 3, 5, 7, 10}),
    "Vrindavani Sarang": frozenset({0, 2, 5, 7, 10, 11}),
    "Tilang": frozenset({0, 4, 5, 7, 10, 11}),
}

# A swara has to carry this share of the total sung time before it counts as
# part of the scale. Below it, it is a passing touch or a tracking error.
_PRESENCE_FLOOR = 0.03


@dataclass
class ScaleGuess:
    swaras: list[int] = field(default_factory=list)     # semitones, by prominence
    thaat: str | None = None                            # best fit, if any
    thaats: tuple[str, ...] = ()                        # every equally good fit
    thaat_score: float = 0.0
    thaat_ragas: tuple[str, ...] = ()
    exact_ragas: tuple[str, ...] = ()
    total_seconds: float = 0.0

    @property
    def swara_line(self) -> str:
        return " ".join(SWARA_SHORT[s] for s in sorted(self.swaras))

    def summary(self) -> str:
        """One line, hedged as strongly as the evidence deserves."""
        if not self.swaras:
            return "not enough sung material to identify a scale"
        if self.exact_ragas:
            names = " / ".join(self.exact_ragas)
            return f"{self.swara_line} — matches {names}"
        if self.thaat:
            candidates = ", ".join(self.thaat_ragas[:4])
            named = " or ".join(self.thaats) if len(self.thaats) > 1 else self.thaat
            return (
                f"{self.swara_line} — {named} thaat "
                f"({self.thaat_score:.0%} fit); could be {candidates}"
            )
        return f"{self.swara_line} — no thaat fits cleanly"

    def to_dict(self) -> dict:
        return {
            "swaras": self.swara_line,
            "thaat": self.thaat,
            "thaat_candidates": list(self.thaats),
            "thaat_fit": round(self.thaat_score, 3),
            "candidate_ragas": list(self.thaat_ragas),
            "exact_match_ragas": list(self.exact_ragas),
            "sung_seconds": round(self.total_seconds, 1),
            "summary": self.summary(),
        }


def identify_scale(weights: dict[int, float], min_seconds: float = 8.0) -> ScaleGuess:
    """Guess the scale from seconds-per-swara (see :func:`swara.swara_weights`).

    *min_seconds* guards against naming a raga off four notes of a warm-up.
    """
    total = sum(weights.values())
    if total <= 0 or total < min_seconds:
        return ScaleGuess(total_seconds=total)

    present = sorted(
        (s for s, w in weights.items() if w / total >= _PRESENCE_FLOOR),
        key=lambda s: -weights[s],
    )
    used = frozenset(present)
    guess = ScaleGuess(swaras=present, total_seconds=total)
    if not used:
        return guess

    # Exact set match against the distinctive ragas: the strong claim.
    guess.exact_ragas = tuple(
        name for name, notes in DISTINCTIVE_RAGAS.items() if notes == used
    )

    # Otherwise fit a thaat: reward time spent inside the scale, punish time
    # spent outside it harder, since one foreign note rules a thaat out.
    scored: dict[str, float] = {}
    for name, notes in THAATS.items():
        inside = sum(w for s, w in weights.items() if s in notes)
        outside = sum(w for s, w in weights.items() if s not in notes)
        scored[name] = (inside - 2.0 * outside) / total

    best_score = max(scored.values())
    if best_score < 0.5:
        return guess

    # A pentatonic raag sits inside several thaats at once, and picking one of
    # them by dictionary order would be an invented distinction. Report every
    # scale the notes fit equally well and let the spoken transcript decide.
    tied = tuple(
        name for name, score in scored.items() if best_score - score <= 1e-9
    )
    guess.thaats = tied
    guess.thaat = tied[0]
    guess.thaat_score = max(0.0, best_score)
    guess.thaat_ragas = tuple(
        dict.fromkeys(r for name in tied for r in THAAT_RAGAS.get(name, ()))
    )
    return guess


def ragas_matching_thaat(name: str) -> tuple[str, ...]:
    """Ragas taught out of *name* thaat, for cross-referencing spoken mentions."""
    return THAAT_RAGAS.get(name.title(), ())


def thaat_of_raga(raga: str) -> str | None:
    """Which thaat a named raga belongs to, if we know it."""
    target = raga.strip().lower()
    for thaat, ragas in THAAT_RAGAS.items():
        if any(r.lower() == target for r in ragas):
            return thaat
    return None
