"""Match diarized speaker clusters against the persistent speaker store.

Diarization answers "which turns are the same person"; this module answers
"which person". It embeds each cluster's speech into a voiceprint and compares
it to every known speaker's centroid.

The matching is deliberately biased toward false negatives. Leaving a speaker
as "Speaker 2" is a small annoyance; confidently printing the wrong person's
name over their words is a real error that a reader has no way to catch.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import audio as _audio
from .diarize import Turn
from .speakerdb import Speaker, normalize

# Resemblyzer cosine similarities: same speaker typically lands 0.75-0.95,
# different speakers 0.4-0.7. 0.72 sits just below the same-speaker band.
DEFAULT_THRESHOLD = 0.72

# How far the best match must beat the runner-up. Two similar voices can both
# clear the threshold, and taking the higher one silently mislabels people.
DEFAULT_MARGIN = 0.05

# Below this much speech, an embedding reflects the phonemes that happened to
# occur more than the voice, so it is unsafe to store as a reference.
DEFAULT_MIN_ENROLL_SECONDS = 6.0

# Windows shorter than this carry too little signal to embed at all.
_MIN_EMBED_SECONDS = 1.0


@dataclass
class ClusterVoiceprint:
    """The aggregate voiceprint of one diarized cluster in one recording."""

    label: str                  # diarization label, e.g. "Speaker 1"
    vector: np.ndarray          # unit-norm embedding
    speech_seconds: float       # total speech behind it

    @property
    def enrollable(self) -> bool:
        return self.speech_seconds >= DEFAULT_MIN_ENROLL_SECONDS


@dataclass
class Match:
    """The identification outcome for one cluster."""

    label: str
    name: str | None            # None when left anonymous
    similarity: float           # best similarity seen (even if rejected)
    runner_up: float            # second-best, for the margin test
    reason: str                 # why it matched or did not

    @property
    def matched(self) -> bool:
        return self.name is not None


def extract_voiceprints(
    wav_path: str,
    turns: list[Turn],
    *,
    max_seconds_per_speaker: float = 60.0,
    encoder=None,
) -> list[ClusterVoiceprint]:
    """Embed each diarized cluster in *wav_path* into one voiceprint.

    Only the longest turns per speaker are used, capped at
    *max_seconds_per_speaker*: long clean turns embed a voice better than many
    short ones, and the cap keeps this cheap on hour-long recordings.
    """
    if not turns:
        return []

    try:
        from resemblyzer import VoiceEncoder
    except ImportError as exc:  # pragma: no cover - dependency hint
        raise RuntimeError(
            "Resemblyzer is not installed (needed to recognise speakers). "
            "Run: pip install resemblyzer"
        ) from exc

    encoder = encoder or VoiceEncoder()
    samples, sr = _audio.load_waveform(wav_path)

    by_speaker: dict[str, list[Turn]] = {}
    for turn in turns:
        by_speaker.setdefault(turn.speaker, []).append(turn)

    prints: list[ClusterVoiceprint] = []
    for label, spk_turns in by_speaker.items():
        chunks: list[np.ndarray] = []
        total = 0.0
        for turn in sorted(
            spk_turns, key=lambda t: t.end - t.start, reverse=True
        ):
            if total >= max_seconds_per_speaker:
                break
            chunk = _audio.slice_waveform(samples, sr, turn.start, turn.end)
            if len(chunk) < int(_MIN_EMBED_SECONDS * sr):
                continue
            chunks.append(chunk)
            total += (turn.end - turn.start)

        if not chunks:
            continue
        vector = _embed(encoder, np.concatenate(chunks))
        if vector is None:
            continue
        prints.append(
            ClusterVoiceprint(label=label, vector=vector, speech_seconds=total)
        )
    return prints


def _embed(encoder, waveform: np.ndarray) -> np.ndarray | None:
    """Embed a 16 kHz mono waveform, or None if it carries no usable signal."""
    from resemblyzer import preprocess_wav

    # preprocess_wav trims silence and normalises loudness; on a chunk that is
    # all silence it can return an empty array, which the encoder cannot embed.
    processed = preprocess_wav(waveform, source_sr=_audio.SAMPLE_RATE)
    if processed.size < int(_MIN_EMBED_SECONDS * _audio.SAMPLE_RATE):
        return None
    try:
        return normalize(encoder.embed_utterance(processed))
    except ValueError:
        return None


def match_speakers(
    prints: list[ClusterVoiceprint],
    known: list[Speaker],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    margin: float = DEFAULT_MARGIN,
) -> list[Match]:
    """Assign known names to clusters, one-to-one.

    Candidate pairs are considered in descending similarity, so the most
    confident assignment claims its speaker first. A known speaker is used at
    most once per recording: one person cannot be two participants in the same
    conversation, and allowing it turns one bad match into two.
    """
    if not prints:
        return []
    if not known:
        return [
            Match(p.label, None, 0.0, 0.0, "no enrolled speakers yet")
            for p in prints
        ]

    # sims[i][j] = cosine similarity of cluster i to known speaker j.
    sims = np.array(
        [[float(np.dot(p.vector, s.centroid)) for s in known] for p in prints],
        dtype=np.float32,
    )

    order = sorted(
        ((sims[i, j], i, j) for i in range(len(prints)) for j in range(len(known))),
        key=lambda t: (-t[0], t[1], t[2]),   # ties resolved deterministically
    )

    taken_cluster: set[int] = set()
    taken_speaker: set[int] = set()
    assigned: dict[int, tuple[str, float]] = {}

    for sim, i, j in order:
        if i in taken_cluster or j in taken_speaker:
            continue
        if sim < threshold:
            break  # sorted descending, so nothing later can qualify either

        # Compare against the best *still-available* alternative for this
        # cluster. A speaker already claimed by a more confident match is not a
        # real competitor, so counting them would suppress a valid match.
        rivals = [
            sims[i, k] for k in range(len(known))
            if k != j and k not in taken_speaker
        ]
        runner_up = max(rivals) if rivals else 0.0
        if sim - runner_up < margin:
            continue  # ambiguous; leave anonymous rather than guess

        assigned[i] = (known[j].name, float(runner_up))
        taken_cluster.add(i)
        taken_speaker.add(j)

    return [
        _build_match(idx, p, sims[idx], known, assigned, threshold, margin)
        for idx, p in enumerate(prints)
    ]


def _build_match(
    idx: int,
    print_: ClusterVoiceprint,
    row: np.ndarray,
    known: list[Speaker],
    assigned: dict[int, tuple[str, float]],
    threshold: float,
    margin: float,
) -> Match:
    ordered = np.sort(row)[::-1]
    best = float(ordered[0])
    second = float(ordered[1]) if ordered.size > 1 else 0.0

    if idx in assigned:
        name, runner_up = assigned[idx]
        return Match(print_.label, name, best, runner_up, "matched")

    if best < threshold:
        reason = (
            f"best similarity {best:.2f} below threshold {threshold:.2f} "
            f"(closest: {known[int(np.argmax(row))].name})"
        )
    elif best - second < margin:
        reason = (
            f"ambiguous: {best:.2f} vs {second:.2f} is under the "
            f"{margin:.2f} margin"
        )
    else:
        reason = "best-matching speaker was claimed by a closer cluster"
    return Match(print_.label, None, best, second, reason)


def apply_matches(
    matches: list[Match], turns: list[Turn]
) -> tuple[list[Turn], dict[str, str]]:
    """Rename matched turns in place-ish and return (turns, label -> name).

    Only matched labels are renamed; unmatched clusters keep "Speaker N" so the
    transcript still distinguishes them.
    """
    mapping = {m.label: m.name for m in matches if m.matched}
    if not mapping:
        return turns, {}
    for turn in turns:
        if turn.speaker in mapping:
            turn.speaker = mapping[turn.speaker]
    return turns, mapping
