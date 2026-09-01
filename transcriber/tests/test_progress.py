"""Tests for progress reporting during the long stages.

Diarization on CPU can run for many minutes. Without these, the only signal a
user has is a bar that has not moved, which is indistinguishable from a hang.
"""
from __future__ import annotations

import numpy as np
import pytest

from transcriber import core, diarize as _diarize


def test_stage_progress_maps_into_its_slice():
    seen = []
    report = core._stage_progress(lambda s, f: seen.append((s, f)), "Diarizing", 0.5, 0.7)
    report("embedding", 0.0)
    report("clustering", 0.5)
    report("done", 1.0)
    assert [f for _, f in seen] == [0.5, 0.6, 0.7]
    assert seen[0][0] == "Diarizing — embedding"


def test_stage_progress_clamps_out_of_range_fractions():
    seen = []
    report = core._stage_progress(lambda s, f: seen.append(f), "x", 0.0, 1.0)
    report("", -3.0)
    report("", 42.0)
    assert seen == [0.0, 1.0]


def test_an_unknown_backend_is_still_rejected():
    with pytest.raises(ValueError, match="Unknown diarization backend"):
        _diarize.diarize("unused.wav", backend="nope")


# --------------------------------------------------------------------------- #
# pyannote's hook
# --------------------------------------------------------------------------- #
def test_the_hook_converts_counts_to_a_fraction():
    seen = []
    hook = _diarize._progress_hook(lambda d, f: seen.append((d, f)))
    hook("segmentation", None, total=4, completed=1)
    assert seen == [("segmentation", 0.25)]


def test_the_hook_survives_a_step_with_no_counts():
    """pyannote calls the hook once per step before it knows the total."""
    seen = []
    hook = _diarize._progress_hook(lambda d, f: seen.append((d, f)))
    hook("embeddings")
    hook("embeddings", None, None, None, None)
    assert seen == [("embeddings", 0.0), ("embeddings", 0.0)]


def test_the_hook_tolerates_arguments_it_has_never_seen():
    """A future pyannote passing a new keyword must not kill the run."""
    seen = []
    hook = _diarize._progress_hook(lambda d, f: seen.append(d))
    hook("step", None, total=2, completed=2, something_new=object())
    assert seen == ["step"]


def test_the_hook_is_only_passed_to_versions_that_accept_it():
    class Old:
        def apply(self, file, num_speakers=None):
            ...

    class New:
        def apply(self, file, num_speakers=None, hook=None):
            ...

    assert _diarize._accepts_hook(Old()) is False
    assert _diarize._accepts_hook(New()) is True
    assert _diarize._accepts_hook(object()) is False


# --------------------------------------------------------------------------- #
# The offline clustering backend
# --------------------------------------------------------------------------- #
class FakeClustering:
    """Stands in for sklearn's AgglomerativeClustering.

    _cluster_embeddings takes both sklearn callables as arguments, so the
    search can be tested without the dependency -- and deterministically.
    """

    def __init__(self, n_clusters):
        self.n_clusters = n_clusters

    def fit_predict(self, embeds):
        return np.arange(len(embeds)) % self.n_clusters


def fake_silhouette(embeds, labels, metric="cosine"):
    return 0.5


def test_clustering_reports_each_candidate_speaker_count():
    embeds = np.zeros((20, 8))
    seen = []
    _diarize._cluster_embeddings(
        embeds, None, 4, FakeClustering, fake_silhouette,
        progress=lambda detail, frac: seen.append((detail, frac)),
    )
    assert [d for d, _ in seen] == [
        "trying 2 speakers", "trying 3 speakers", "trying 4 speakers"]
    assert seen[-1][1] == pytest.approx(1.0)


def test_a_known_speaker_count_skips_the_search_entirely():
    """Told how many speakers there are, there is nothing to search."""
    seen = []
    _diarize._cluster_embeddings(
        np.zeros((10, 8)), 2, 8, FakeClustering, fake_silhouette,
        progress=lambda detail, frac: seen.append(detail),
    )
    assert seen == []


def test_sub_progress_narrows_into_a_band():
    seen = []
    report = _diarize._sub_progress(lambda d, f: seen.append(f), "x", 0.7, 1.0)
    report("", 0.0)
    report("", 1.0)
    assert seen == [pytest.approx(0.7), pytest.approx(1.0)]


# --------------------------------------------------------------------------- #
# Stage logging
# --------------------------------------------------------------------------- #
def test_a_failing_stage_is_logged_as_failed_not_done(monkeypatch, capsys):
    monkeypatch.delenv("TRANSCRIBER_QUIET", raising=False)
    timings: dict[str, float] = {}
    with pytest.raises(ZeroDivisionError):
        with core._timed(timings, "diarize"):
            1 / 0
    err = capsys.readouterr().err
    assert "diarize: FAILED" in err
    assert "diarize: done" not in err
    assert "diarize" in timings          # still recorded, for the report


def test_quiet_silences_the_terminal_notes(monkeypatch, capsys):
    monkeypatch.setenv("TRANSCRIBER_QUIET", "1")
    with core._timed({}, "extract"):
        pass
    assert capsys.readouterr().err == ""
