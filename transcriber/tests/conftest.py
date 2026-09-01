"""Shared fixtures.

These tests cover pipeline logic only — matching, smoothing, alignment — so
they run without torch, ffmpeg, or any model download. Anything needing real
inference belongs in the end-to-end check in SPEC.md.
"""
from __future__ import annotations

import numpy as np
import pytest

from transcriber.speakerdb import EMBED_DIM, Speaker, SpeakerStore, normalize


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(1234)


@pytest.fixture
def store(tmp_path) -> SpeakerStore:
    with SpeakerStore(tmp_path / "speakers.db") as s:
        yield s


def make_voice(rng: np.random.Generator) -> np.ndarray:
    """A random unit-norm vector standing in for one person's voice."""
    return normalize(rng.normal(size=EMBED_DIM))


def vary(voice: np.ndarray, rng: np.random.Generator, amount: float = 0.15):
    """The same voice recorded again: same direction, slightly perturbed.

    *amount* is the norm of the perturbation relative to the unit-length voice,
    so cosine similarity to the original is about 1/sqrt(1 + amount**2). Scaling
    the noise to unit length first matters: raw ``normal(size=256)`` has norm
    ~16, so adding it unscaled would swamp the voice rather than nudge it.
    """
    noise = normalize(rng.normal(size=EMBED_DIM))
    return normalize(voice + amount * noise)


def known(name: str, voice: np.ndarray, samples: int = 3) -> Speaker:
    return Speaker(id=abs(hash(name)) % 10_000, name=name,
                   centroid=normalize(voice), sample_count=samples)
