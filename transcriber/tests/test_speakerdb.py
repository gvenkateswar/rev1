"""Tests for the persistent speaker store."""
from __future__ import annotations

import numpy as np
import pytest

from transcriber.speakerdb import EMBED_DIM, SpeakerStore, normalize

from .conftest import make_voice


def test_enroll_creates_speaker_with_unit_centroid(store, rng):
    speaker = store.enroll("Priya", make_voice(rng), source="a.wav", duration=12.0)
    assert speaker.name == "Priya"
    assert speaker.sample_count == 1
    assert np.isclose(np.linalg.norm(speaker.centroid), 1.0, atol=1e-5)


def test_reenrolling_appends_rather_than_replacing(store, rng):
    voice = make_voice(rng)
    store.enroll("Priya", voice)
    store.enroll("Priya", voice)
    assert store.get("Priya").sample_count == 2


def test_centroid_averages_samples(store, rng):
    """The centroid should sit between the samples, not on the newest one."""
    a, b = make_voice(rng), make_voice(rng)
    store.enroll("Priya", a)
    store.enroll("Priya", b)
    centroid = store.get("Priya").centroid
    assert np.dot(centroid, a) == pytest.approx(np.dot(centroid, b), abs=1e-5)


def test_samples_are_capped(tmp_path, rng):
    with SpeakerStore(tmp_path / "s.db", max_samples=3) as store:
        for _ in range(7):
            store.enroll("Priya", make_voice(rng))
        assert store.get("Priya").sample_count == 3


def test_forget_removes_speaker_and_voiceprints(store, rng):
    store.enroll("Priya", make_voice(rng))
    store.forget("Priya")
    assert store.all_speakers() == []
    orphans = store._conn.execute("SELECT COUNT(*) FROM voiceprints").fetchone()[0]
    assert orphans == 0


def test_rename_keeps_voiceprints(store, rng):
    store.enroll("Priya", make_voice(rng))
    store.enroll("Priya", make_voice(rng))
    renamed = store.rename("Priya", "Priya Sharma")
    assert renamed.sample_count == 2


def test_rename_onto_another_speaker_is_refused(store, rng):
    store.enroll("A", make_voice(rng))
    store.enroll("B", make_voice(rng))
    with pytest.raises(ValueError, match="already named"):
        store.rename("A", "B")


def test_rename_to_same_name_is_allowed(store, rng):
    store.enroll("A", make_voice(rng))
    assert store.rename("A", "A").name == "A"


def test_persists_across_connections(tmp_path, rng):
    path = tmp_path / "s.db"
    voice = make_voice(rng)
    with SpeakerStore(path) as store:
        store.enroll("Priya", voice)
    with SpeakerStore(path) as store:
        assert np.allclose(store.get("Priya").centroid, voice, atol=1e-5)


# --- unhappy paths -------------------------------------------------------- #
def test_empty_name_rejected(store, rng):
    with pytest.raises(ValueError, match="cannot be empty"):
        store.enroll("   ", make_voice(rng))


def test_zero_vector_rejected(store):
    with pytest.raises(ValueError, match="zero vector"):
        store.enroll("Priya", np.zeros(EMBED_DIM))


def test_wrong_dimension_rejected(store):
    with pytest.raises(ValueError, match="256-d"):
        store.enroll("Priya", np.ones(64))


def test_unknown_speaker_lookups_raise(store):
    with pytest.raises(KeyError):
        store.get("Nobody")
    with pytest.raises(KeyError):
        store.forget("Nobody")
    with pytest.raises(KeyError):
        store.rename("Nobody", "Someone")


def test_corrupt_voiceprint_is_skipped_not_fatal(store, rng):
    """One truncated blob must not break every other speaker."""
    store.enroll("Priya", make_voice(rng))
    store.enroll("Rahul", make_voice(rng))
    store._conn.execute(
        "UPDATE voiceprints SET vector = ? WHERE speaker_id = "
        "(SELECT id FROM speakers WHERE name = 'Priya')",
        (b"\x00\x01\x02",),
    )
    store._conn.commit()
    names = [s.name for s in store.all_speakers()]
    assert names == ["Rahul"]  # Priya has no usable samples, so she is skipped


def test_normalize_rejects_zero():
    with pytest.raises(ValueError):
        normalize(np.zeros(8))
