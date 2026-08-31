"""Speaker diarization with two interchangeable backends.

Both backends return the same thing: a list of :class:`Turn` (start, end,
speaker) sorted by start time. ``core`` then maps Whisper words onto these
turns, so the rest of the pipeline doesn't care which backend ran.

Backends
--------
* ``pyannote``  - pyannote.audio's pretrained pipeline. Best accuracy, but
  needs a (free) Hugging Face token and a one-time license acceptance.
* ``cluster``   - fully offline. Embeds short windows with Resemblyzer's
  VoiceEncoder and clusters them (agglomerative). No token, no license.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Turn:
    start: float
    end: float
    speaker: str


def diarize(
    wav_path: str,
    backend: str = "cluster",
    num_speakers: int | None = None,
    hf_token: str | None = None,
) -> list[Turn]:
    """Dispatch to the chosen backend. *num_speakers* None means auto-detect."""
    if backend == "pyannote":
        return _diarize_pyannote(wav_path, num_speakers, hf_token)
    if backend == "cluster":
        return _diarize_cluster(wav_path, num_speakers)
    raise ValueError(f"Unknown diarization backend: {backend!r}")


# --------------------------------------------------------------------------- #
# Backend 1: pyannote.audio
# --------------------------------------------------------------------------- #
def _diarize_pyannote(
    wav_path: str, num_speakers: int | None, hf_token: str | None
) -> list[Turn]:
    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "pyannote.audio is not installed. Run: pip install pyannote.audio\n"
            "Then accept the model license at "
            "https://hf.co/pyannote/speaker-diarization-3.1 and pass a token."
        ) from exc

    if not hf_token:
        raise RuntimeError(
            "The pyannote backend needs a Hugging Face access token.\n"
            "Get one at https://hf.co/settings/tokens, accept the license at\n"
            "https://hf.co/pyannote/speaker-diarization-3.1, then pass it via\n"
            "--hf-token / the HF_TOKEN env var / the GUI sidebar."
        )

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1", **_token_kwarg(Pipeline, hf_token)
    )
    if pipeline is None:
        # from_pretrained returns None rather than raising when the checkpoint
        # cannot be loaded -- almost always an unaccepted licence or a token
        # without access. Without this the next line dies on NoneType.
        raise RuntimeError(
            "pyannote returned no pipeline for "
            "'pyannote/speaker-diarization-3.1'. Accept the licence at "
            "https://hf.co/pyannote/speaker-diarization-3.1 with the same "
            "account as your token, then try again."
        )
    kwargs = {}
    if num_speakers:
        kwargs["num_speakers"] = num_speakers
    annotation = pipeline(wav_path, **kwargs)

    turns = [
        Turn(start=float(seg.start), end=float(seg.end), speaker=str(label))
        for seg, _, label in annotation.itertracks(yield_label=True)
    ]
    turns.sort(key=lambda t: t.start)
    return _normalize_speaker_names(turns)


def _token_kwarg(pipeline_cls, hf_token: str) -> dict:
    """Name the Hugging Face token argument the installed pyannote expects.

    pyannote.audio 4.x renamed ``use_auth_token`` to ``token``. Passing the
    wrong one is a TypeError at call time, so pick it from the real signature
    rather than pinning a version.
    """
    import inspect

    params = inspect.signature(pipeline_cls.from_pretrained).parameters
    name = "token" if "token" in params else "use_auth_token"
    return {name: hf_token}


# --------------------------------------------------------------------------- #
# Backend 2: offline embedding + clustering
# --------------------------------------------------------------------------- #
def _diarize_cluster(
    wav_path: str,
    num_speakers: int | None,
    window: float = 1.5,
    hop: float = 0.75,
    max_speakers: int = 8,
) -> list[Turn]:
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Resemblyzer is not installed (needed for the offline 'cluster' "
            "backend). Run: pip install resemblyzer"
        ) from exc
    try:
        from sklearn.cluster import AgglomerativeClustering
        from sklearn.metrics import silhouette_score
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "scikit-learn is not installed. Run: pip install scikit-learn"
        ) from exc

    wav = preprocess_wav(wav_path)            # 16 kHz float, VAD-trimmed
    encoder = VoiceEncoder()

    # Continuous embedding: one partial embedding per `rate` slices.
    sr = 16_000
    rate = 1.0 / hop                          # embeddings per second
    _, cont_embeds, slices = encoder.embed_utterance(
        wav, return_partials=True, rate=rate
    )
    if len(cont_embeds) == 0:
        return []

    # Time (centre, in seconds) of each partial embedding window.
    centres = np.array([(s.start + s.stop) / 2 / sr for s in slices])

    labels = _cluster_embeddings(
        cont_embeds, num_speakers, max_speakers,
        AgglomerativeClustering, silhouette_score,
    )

    # Collapse consecutive same-label windows into turns.
    turns = _labels_to_turns(centres, labels, hop)
    return _normalize_speaker_names(turns)


def _cluster_embeddings(
    embeds: np.ndarray,
    num_speakers: int | None,
    max_speakers: int,
    AgglomerativeClustering,
    silhouette_score,
) -> np.ndarray:
    n = len(embeds)
    if n == 1:
        return np.zeros(1, dtype=int)

    if num_speakers:
        k = min(num_speakers, n)
        if k <= 1:
            return np.zeros(n, dtype=int)
        return AgglomerativeClustering(n_clusters=k).fit_predict(embeds)

    # Auto-detect: pick the k (>=2) with the best silhouette, but fall back to
    # a single speaker if even the best split is weak (mono-speaker audio).
    best_k, best_score, best_labels = 1, -1.0, np.zeros(n, dtype=int)
    upper = min(max_speakers, n)
    for k in range(2, upper + 1):
        labels = AgglomerativeClustering(n_clusters=k).fit_predict(embeds)
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(embeds, labels, metric="cosine")
        if score > best_score:
            best_k, best_score, best_labels = k, score, labels

    # Silhouette below ~0.1 means the "clusters" aren't really separable.
    if best_score < 0.10:
        return np.zeros(n, dtype=int)
    return best_labels


def _labels_to_turns(
    centres: np.ndarray, labels: np.ndarray, hop: float
) -> list[Turn]:
    turns: list[Turn] = []
    half = hop / 2
    cur_label = labels[0]
    seg_start = max(0.0, centres[0] - half)
    for i in range(1, len(labels)):
        if labels[i] != cur_label:
            boundary = (centres[i - 1] + centres[i]) / 2
            turns.append(Turn(seg_start, boundary, f"SPEAKER_{int(cur_label)}"))
            seg_start = boundary
            cur_label = labels[i]
    turns.append(
        Turn(seg_start, centres[-1] + half, f"SPEAKER_{int(cur_label)}")
    )
    return turns


# --------------------------------------------------------------------------- #
# Shared post-processing
# --------------------------------------------------------------------------- #
def _normalize_speaker_names(turns: list[Turn]) -> list[Turn]:
    """Rename raw labels to stable, 1-based "Speaker 1/2/..." by first appearance."""
    mapping: dict[str, str] = {}
    for t in turns:
        if t.speaker not in mapping:
            mapping[t.speaker] = f"Speaker {len(mapping) + 1}"
    for t in turns:
        t.speaker = mapping[t.speaker]
    return turns
