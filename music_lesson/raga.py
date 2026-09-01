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

# Swara sets of commonly taught ragas, as semitones above Sa. This is what
# lets a *named* raga be checked against the sung notes — including the many
# ragas (Kirwani, Charukeshi, Ahir Bhairav, Madhuvanti…) whose scale is not
# one of the ten thaats at all, which the thaat matcher alone can never name.
# A set is the union over aroha and avaroha; ragas sharing a set are all
# listed, because pitch alone cannot split them.
RAGA_SCALES: dict[str, frozenset[int]] = {
    # Kalyan-anga
    "Yaman": frozenset({0, 2, 4, 6, 7, 9, 11}),
    "Yaman Kalyan": frozenset({0, 2, 4, 5, 6, 7, 9, 11}),
    "Shuddha Kalyan": frozenset({0, 2, 4, 7, 9}),
    "Bhupali": frozenset({0, 2, 4, 7, 9}),
    "Deshkar": frozenset({0, 2, 4, 7, 9}),
    "Hamsadhwani": frozenset({0, 2, 4, 7, 11}),
    "Shankara": frozenset({0, 2, 4, 7, 9, 11}),
    "Bihag": frozenset({0, 2, 4, 5, 6, 7, 9, 11}),
    "Kedar": frozenset({0, 2, 4, 5, 6, 7, 9, 11}),
    "Hamir": frozenset({0, 2, 4, 5, 6, 7, 9, 11}),
    "Nand": frozenset({0, 2, 4, 5, 6, 7, 9, 11}),
    "Chhayanat": frozenset({0, 2, 4, 5, 7, 9, 11}),
    "Shuddha Sarang": frozenset({0, 2, 5, 6, 7, 9, 11}),
    # Bilawal-anga
    "Bilawal": frozenset({0, 2, 4, 5, 7, 9, 11}),
    "Alhaiya Bilawal": frozenset({0, 2, 4, 5, 7, 9, 10, 11}),
    "Durga": frozenset({0, 2, 5, 7, 9}),
    "Gorakh Kalyan": frozenset({0, 2, 5, 7, 9, 10}),
    # Khamaj-anga
    "Khamaj": frozenset({0, 2, 4, 5, 7, 9, 10}),
    "Jhinjhoti": frozenset({0, 2, 4, 5, 7, 9, 10}),
    "Des": frozenset({0, 2, 4, 5, 7, 9, 10, 11}),
    "Tilak Kamod": frozenset({0, 2, 4, 5, 7, 9, 11}),
    "Gaud Malhar": frozenset({0, 2, 4, 5, 7, 9, 10, 11}),
    "Rageshri": frozenset({0, 2, 4, 5, 9, 10}),
    "Tilang": frozenset({0, 4, 5, 7, 10, 11}),
    "Kalavati": frozenset({0, 4, 7, 9, 10}),
    "Jog": frozenset({0, 3, 4, 5, 7, 10}),
    "Kaushik Dhwani": frozenset({0, 4, 5, 9, 11}),
    # Kafi-anga
    "Kafi": frozenset({0, 2, 3, 5, 7, 9, 10}),
    "Bhimpalasi": frozenset({0, 2, 3, 5, 7, 9, 10}),
    "Bageshri": frozenset({0, 2, 3, 5, 7, 9, 10}),
    "Patdeep": frozenset({0, 2, 3, 5, 7, 9, 11}),
    "Dhani": frozenset({0, 3, 5, 7, 10}),
    "Miyan ki Malhar": frozenset({0, 2, 3, 5, 7, 9, 10, 11}),
    "Bahar": frozenset({0, 2, 3, 5, 7, 9, 10, 11}),
    "Jaijaiwanti": frozenset({0, 2, 3, 4, 5, 7, 9, 10, 11}),
    "Shivaranjani": frozenset({0, 2, 3, 7, 9}),
    "Megh": frozenset({0, 2, 5, 7, 10}),
    "Vrindavani Sarang": frozenset({0, 2, 5, 7, 10, 11}),
    # Asavari-anga
    "Asavari": frozenset({0, 2, 3, 5, 7, 8, 10}),
    "Jaunpuri": frozenset({0, 2, 3, 5, 7, 8, 10}),
    "Darbari Kanada": frozenset({0, 2, 3, 5, 7, 8, 10}),
    "Adana": frozenset({0, 2, 3, 5, 7, 8, 10}),
    # Bhairavi-anga
    "Bhairavi": frozenset({0, 1, 3, 5, 7, 8, 10}),
    "Bilaskhani Todi": frozenset({0, 1, 3, 5, 7, 8, 10}),
    "Komal Rishabh Asavari": frozenset({0, 1, 3, 5, 7, 8, 10}),
    "Malkauns": frozenset({0, 3, 5, 8, 10}),
    "Chandrakauns": frozenset({0, 3, 5, 8, 11}),
    "Madhukauns": frozenset({0, 3, 6, 7, 10}),
    # Bhairav-anga
    "Bhairav": frozenset({0, 1, 4, 5, 7, 8, 11}),
    "Ahir Bhairav": frozenset({0, 1, 4, 5, 7, 9, 10}),
    "Nat Bhairav": frozenset({0, 2, 4, 5, 7, 8, 11}),
    "Gunkali": frozenset({0, 1, 5, 7, 8}),
    "Jogiya": frozenset({0, 1, 5, 7, 8, 11}),
    "Bairagi": frozenset({0, 1, 5, 7, 10}),
    # Todi / Marwa / Poorvi angas
    "Todi": frozenset({0, 1, 3, 6, 7, 8, 11}),
    "Multani": frozenset({0, 1, 3, 6, 7, 8, 11}),
    "Gujari Todi": frozenset({0, 1, 3, 6, 8, 11}),
    "Madhuvanti": frozenset({0, 2, 3, 6, 7, 9, 11}),
    "Marwa": frozenset({0, 1, 4, 6, 9, 11}),
    "Puriya": frozenset({0, 1, 4, 6, 9, 11}),
    "Sohini": frozenset({0, 1, 4, 6, 9, 11}),
    "Lalit": frozenset({0, 1, 4, 5, 6, 9, 11}),
    "Basant": frozenset({0, 1, 4, 5, 6, 8, 11}),
    "Shree": frozenset({0, 1, 4, 6, 7, 8, 11}),
    "Puriya Dhanashri": frozenset({0, 1, 4, 6, 7, 8, 11}),
    "Hindol": frozenset({0, 4, 6, 9, 11}),
    # Carnatic-derived scales, absent from the thaat system entirely
    "Kirwani": frozenset({0, 2, 3, 5, 7, 8, 11}),
    "Charukeshi": frozenset({0, 2, 4, 5, 7, 8, 10}),
    "Vachaspati": frozenset({0, 2, 4, 6, 7, 9, 10}),
}

def all_raga_names() -> list[str]:
    """Every raga this module can score, for pickers and validation."""
    return sorted(RAGA_SCALES)


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
    hint_fits: tuple[tuple[str, float], ...] = ()   # (raga, fit) for user hints
    total_seconds: float = 0.0

    @property
    def swara_line(self) -> str:
        return " ".join(SWARA_SHORT[s] for s in sorted(self.swaras))

    def summary(self) -> str:
        """One line, hedged as strongly as the evidence deserves."""
        if not self.swaras:
            return "not enough sung material to identify a scale"
        if self.hint_fits:
            name, fit = self.hint_fits[0]
            if fit >= 0.6:
                return f"{self.swara_line} — fits your hint {name} ({fit:.0%})"
            hint_note = f"; your hint {name} fits only {fit:.0%}"
        else:
            hint_note = ""
        if self.exact_ragas:
            names = " / ".join(self.exact_ragas)
            return f"{self.swara_line} — matches {names}" + hint_note
        if self.thaat:
            candidates = ", ".join(self.thaat_ragas[:4])
            named = " or ".join(self.thaats) if len(self.thaats) > 1 else self.thaat
            return (
                f"{self.swara_line} — {named} thaat "
                f"({self.thaat_score:.0%} fit); could be {candidates}"
            ) + hint_note
        return f"{self.swara_line} — no thaat fits cleanly" + hint_note

    def to_dict(self) -> dict:
        return {
            "swaras": self.swara_line,
            "thaat": self.thaat,
            "thaat_candidates": list(self.thaats),
            "thaat_fit": round(self.thaat_score, 3),
            "candidate_ragas": list(self.thaat_ragas),
            "exact_match_ragas": list(self.exact_ragas),
            "hint_fits": [
                {"raga": name, "fit": round(fit, 3)} for name, fit in self.hint_fits
            ],
            "sung_seconds": round(self.total_seconds, 1),
            "summary": self.summary(),
        }


def identify_scale(
    weights: dict[int, float],
    min_seconds: float = 8.0,
    hints: list[str] | None = None,
) -> ScaleGuess:
    """Guess the scale from seconds-per-swara (see :func:`swara.swara_weights`).

    *min_seconds* guards against naming a raga off four notes of a warm-up.
    *hints* are raga names the user expects in the lesson: each is scored
    against the sung time, and a hint that fits leads the summary — the person
    who was in the room outranks a histogram. The fits are reported either
    way, because a hint that does NOT fit is worth knowing too (a wrong tonic
    produces exactly that symptom).
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

    # Exact set match against the raga table: the strong claim. Every raga
    # sharing the set is listed, because pitch cannot split them.
    guess.exact_ragas = tuple(
        name for name, notes in RAGA_SCALES.items() if notes == used
    )

    if hints:
        fits = []
        for hint in hints:
            scale = _lookup_scale(hint)
            if scale is None:
                continue
            inside = sum(w for sw, w in weights.items() if sw in scale)
            outside = total - inside
            fits.append((hint.strip().title(), max((inside - 2.0 * outside) / total, 0.0)))
        guess.hint_fits = tuple(sorted(fits, key=lambda item: -item[1]))

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


def _lookup_scale(name: str) -> frozenset[int] | None:
    target = name.strip().lower()
    for raga, scale in RAGA_SCALES.items():
        if raga.lower() == target:
            return scale
    return None


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
