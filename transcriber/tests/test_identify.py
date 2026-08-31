"""Tests for voiceprint matching.

The bias under test is deliberate: when in doubt, leave a speaker anonymous.
A wrong name attached to someone's words is worse than no name at all.
"""
from __future__ import annotations

import importlib
import sys

import numpy as np
import pytest

from transcriber import runtime
from transcriber.diarize import Turn
from transcriber.identify import (
    DEFAULT_MIN_ENROLL_SECONDS, ClusterVoiceprint, apply_matches,
    extract_voiceprints, match_speakers,
)
from transcriber.speakerdb import Speaker, normalize

from .conftest import known, make_voice, vary


def cluster(label: str, vec: np.ndarray, seconds: float = 30.0):
    return ClusterVoiceprint(label=label, vector=normalize(vec),
                             speech_seconds=seconds)


def test_same_voice_is_recognised(rng):
    voice = make_voice(rng)
    matches = match_speakers(
        [cluster("Speaker 1", vary(voice, rng))],
        [known("Priya", voice), known("Rahul", make_voice(rng))],
    )
    assert matches[0].name == "Priya"
    assert matches[0].matched


def test_unknown_voice_stays_anonymous(rng):
    matches = match_speakers(
        [cluster("Speaker 1", make_voice(rng))],
        [known("Priya", make_voice(rng))],
    )
    assert matches[0].name is None
    assert "below threshold" in matches[0].reason


def test_ambiguous_voice_stays_anonymous(rng):
    """A voice equidistant from two known speakers must not be guessed."""
    a, b = make_voice(rng), make_voice(rng)
    midpoint = normalize(a + b)
    matches = match_speakers(
        [cluster("Speaker 1", midpoint)],
        [known("Priya", a), known("Rahul", b)],
        threshold=0.4,   # low enough that both clear it
    )
    assert matches[0].name is None
    assert "ambiguous" in matches[0].reason


def test_one_known_speaker_cannot_take_two_clusters(rng):
    """A person cannot be two participants in the same conversation."""
    voice = make_voice(rng)
    matches = match_speakers(
        [cluster("Speaker 1", vary(voice, rng, 0.05)),
         cluster("Speaker 2", vary(voice, rng, 0.06))],
        [known("Priya", voice)],
    )
    assert [m.name for m in matches].count("Priya") == 1
    unmatched = [m for m in matches if not m.matched]
    assert "claimed by a closer cluster" in unmatched[0].reason


def test_two_speakers_match_their_own_voices(rng):
    a, b = make_voice(rng), make_voice(rng)
    matches = match_speakers(
        [cluster("Speaker 1", vary(b, rng)), cluster("Speaker 2", vary(a, rng))],
        [known("Priya", a), known("Rahul", b)],
    )
    assert {m.label: m.name for m in matches} == {
        "Speaker 1": "Rahul", "Speaker 2": "Priya",
    }


def test_raising_threshold_rejects_a_borderline_match(rng):
    voice = make_voice(rng)
    prints = [cluster("Speaker 1", vary(voice, rng, 0.6))]
    speakers = [known("Priya", voice)]
    loose = match_speakers(prints, speakers, threshold=0.5)
    strict = match_speakers(prints, speakers, threshold=0.99)
    assert loose[0].matched
    assert not strict[0].matched


def test_no_enrolled_speakers(rng):
    matches = match_speakers([cluster("Speaker 1", make_voice(rng))], [])
    assert matches[0].name is None
    assert matches[0].reason == "no enrolled speakers yet"


def test_no_clusters():
    assert match_speakers([], [known("Priya", np.ones(256))]) == []


def test_zero_centroid_speaker_never_matches(rng):
    """A speaker whose samples cancelled out is unmatchable, not a crash."""
    ghost = Speaker(id=1, name="Ghost",
                    centroid=np.zeros(256, dtype=np.float32), sample_count=1)
    matches = match_speakers([cluster("Speaker 1", make_voice(rng))], [ghost])
    assert matches[0].name is None


def test_matching_is_deterministic(rng):
    """Identical input must produce identical output across runs."""
    a, b = make_voice(rng), make_voice(rng)
    prints = [cluster("Speaker 1", a), cluster("Speaker 2", b)]
    speakers = [known("Priya", a), known("Rahul", b)]
    first = [m.name for m in match_speakers(prints, speakers)]
    for _ in range(5):
        assert [m.name for m in match_speakers(prints, speakers)] == first


def test_enrollable_gate():
    voice = np.ones(256)
    assert cluster("S", voice, DEFAULT_MIN_ENROLL_SECONDS + 1).enrollable
    assert not cluster("S", voice, DEFAULT_MIN_ENROLL_SECONDS - 1).enrollable


def test_apply_matches_renames_only_matched_turns(rng):
    voice = make_voice(rng)
    turns = [Turn(0, 5, "Speaker 1"), Turn(5, 9, "Speaker 2")]
    matches = match_speakers(
        [cluster("Speaker 1", vary(voice, rng)),
         cluster("Speaker 2", make_voice(rng))],
        [known("Priya", voice)],
    )
    renamed, mapping = apply_matches(matches, turns)
    assert mapping == {"Speaker 1": "Priya"}
    assert [t.speaker for t in renamed] == ["Priya", "Speaker 2"]


def test_apply_matches_with_nothing_matched_is_a_noop(rng):
    turns = [Turn(0, 5, "Speaker 1")]
    matches = match_speakers([cluster("Speaker 1", make_voice(rng))],
                             [known("Priya", make_voice(rng))])
    renamed, mapping = apply_matches(matches, turns)
    assert mapping == {}
    assert renamed[0].speaker == "Speaker 1"


# --------------------------------------------------------------------------- #
# Dependency reporting
# --------------------------------------------------------------------------- #
def _install_fake_resemblyzer(tmp_path, monkeypatch, body: str) -> None:
    package = tmp_path / "resemblyzer"
    package.mkdir()
    (package / "__init__.py").write_text(body)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "resemblyzer", raising=False)
    importlib.invalidate_caches()


def test_a_broken_resemblyzer_is_not_reported_as_missing(tmp_path, monkeypatch):
    """Regression: an installed Resemblyzer whose own imports fail.

    The old guard caught the ModuleNotFoundError raised inside Resemblyzer and
    told the user to `pip install resemblyzer` -- which they already had, so
    the advice could not work and the real culprit was never named.
    """
    _install_fake_resemblyzer(
        tmp_path, monkeypatch, "import definitely_not_a_real_module_xyz\n"
    )

    with pytest.raises(RuntimeError) as err:
        extract_voiceprints("unused.wav", [Turn(0.0, 5.0, "Speaker 1")])

    message = str(err.value)
    assert "definitely_not_a_real_module_xyz" in message
    assert "is not installed" not in message


def test_a_missing_resemblyzer_still_says_how_to_install_it(monkeypatch):
    def absent(name):
        raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    monkeypatch.setattr(runtime.importlib, "import_module", absent)

    with pytest.raises(RuntimeError) as err:
        extract_voiceprints("unused.wav", [Turn(0.0, 5.0, "Speaker 1")])
    assert "pip install resemblyzer" in str(err.value)


def test_no_turns_needs_no_dependency():
    """The import is paid for only when there is something to embed."""
    assert extract_voiceprints("unused.wav", []) == []
