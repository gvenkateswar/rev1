"""Pipeline orchestration: file in, labelled transcript out.

    extract audio -> Whisper -> diarize -> align speakers -> fuse emotion

The interesting glue is :func:`assign_speakers`, which uses Whisper's
word-level timestamps to *split* a transcript segment when the speaker changes
mid-sentence, so a back-and-forth that Whisper merged into one segment still
comes out as separate speaker turns.
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable

from . import audio as _audio
from .diarize import Turn, diarize
from .transcribe import RawSegment, Word, transcribe

ProgressCb = Callable[[str, float], None]


@dataclass
class TranscriptSegment:
    start: float
    end: float
    speaker: str
    text: str
    emotion: str = "neutral"
    emotion_score: float = 0.0
    emotion_scores: dict[str, float] = field(default_factory=dict)
    audio_emotion: str | None = None
    text_emotion: str | None = None

    def to_dict(self) -> dict:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "speaker": self.speaker,
            "text": self.text,
            "emotion": self.emotion,
            "emotion_score": round(self.emotion_score, 4),
            "emotion_scores": {k: round(v, 4) for k, v in self.emotion_scores.items()},
            "audio_emotion": self.audio_emotion,
            "text_emotion": self.text_emotion,
        }


@dataclass
class TranscriptResult:
    segments: list[TranscriptSegment]
    language: str
    speakers: list[str]
    source: str
    timings: dict[str, float] = field(default_factory=dict)  # stage -> seconds

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "language": self.language,
            "speakers": self.speakers,
            "timings": {k: round(v, 3) for k, v in self.timings.items()},
            "segments": [s.to_dict() for s in self.segments],
        }


def _noop(_stage: str, _frac: float) -> None:
    pass


@contextmanager
def _timed(timings: dict[str, float], key: str):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        timings[key] = time.perf_counter() - t0


def transcribe_file(
    src_path: str,
    *,
    whisper_model: str = "base",
    language: str | None = None,
    diarization_backend: str = "cluster",
    num_speakers: int | None = None,
    hf_token: str | None = None,
    detect_emotion: bool = True,
    audio_weight: float = 0.5,
    use_audio_emotion: bool = True,
    use_text_emotion: bool = True,
    progress: ProgressCb | None = None,
) -> TranscriptResult:
    """Run the full pipeline on *src_path* and return a TranscriptResult."""
    progress = progress or _noop
    hf_token = hf_token or os.environ.get("HF_TOKEN")
    timings: dict[str, float] = {}

    progress("Extracting audio", 0.05)
    with _timed(timings, "extract"):
        wav_path = _audio.extract_audio(src_path)
    try:
        progress("Transcribing", 0.15)
        with _timed(timings, "transcribe"):
            raw_segments, lang = transcribe(
                wav_path, model_name=whisper_model, language=language
            )

        progress("Identifying speakers", 0.55)
        with _timed(timings, "diarize"):
            turns = diarize(
                wav_path,
                backend=diarization_backend,
                num_speakers=num_speakers,
                hf_token=hf_token,
            )

        segments = assign_speakers(raw_segments, turns)

        if detect_emotion and segments:
            progress("Analyzing emotion", 0.75)
            with _timed(timings, "emotion"):
                _attach_emotions(
                    wav_path, segments, audio_weight,
                    use_audio_emotion, use_text_emotion, progress,
                )

        speakers = _ordered_speakers(segments)
        timings["total"] = sum(v for k, v in timings.items() if k != "total")
        progress("Done", 1.0)
        return TranscriptResult(
            segments=segments, language=lang, speakers=speakers,
            source=src_path, timings=timings,
        )
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Speaker alignment
# --------------------------------------------------------------------------- #
def assign_speakers(
    raw_segments: list[RawSegment], turns: list[Turn]
) -> list[TranscriptSegment]:
    """Attach a speaker to each segment, splitting on mid-segment speaker change.

    If a segment has word timestamps we group its words by the speaker active
    at each word and emit one TranscriptSegment per contiguous run. Without
    word timestamps (or diarization) we fall back to a whole-segment vote.
    """
    if not turns:
        return [
            TranscriptSegment(s.start, s.end, "Speaker 1", s.text)
            for s in raw_segments
        ]

    out: list[TranscriptSegment] = []
    for seg in raw_segments:
        if seg.words:
            out.extend(_split_segment_by_words(seg, turns))
        else:
            spk = _dominant_speaker(seg.start, seg.end, turns)
            out.append(TranscriptSegment(seg.start, seg.end, spk, seg.text))
    return out


def _split_segment_by_words(
    seg: RawSegment, turns: list[Turn]
) -> list[TranscriptSegment]:
    pieces: list[TranscriptSegment] = []
    cur_spk: str | None = None
    cur_words: list[Word] = []

    def flush():
        if cur_words:
            pieces.append(
                TranscriptSegment(
                    start=cur_words[0].start,
                    end=cur_words[-1].end,
                    speaker=cur_spk,
                    text="".join(w.text for w in cur_words).strip(),
                )
            )

    for w in seg.words:
        spk = _speaker_at((w.start + w.end) / 2, turns)
        if cur_spk is None or spk == cur_spk:
            cur_spk = spk
            cur_words.append(w)
        else:
            flush()
            cur_spk, cur_words = spk, [w]
    flush()

    # Coalesce tiny fragments back into neighbours to avoid 1-word flip-flops.
    return _merge_short_pieces(pieces) or [
        TranscriptSegment(
            seg.start, seg.end,
            _dominant_speaker(seg.start, seg.end, turns), seg.text,
        )
    ]


def _merge_short_pieces(
    pieces: list[TranscriptSegment], min_words: int = 2
) -> list[TranscriptSegment]:
    if len(pieces) <= 1:
        return pieces
    merged: list[TranscriptSegment] = []
    for p in pieces:
        n_words = len(p.text.split())
        if merged and n_words < min_words and merged[-1].speaker != p.speaker:
            # Absorb a stray fragment into the previous run.
            prev = merged[-1]
            prev.end = p.end
            prev.text = (prev.text + " " + p.text).strip()
        elif merged and merged[-1].speaker == p.speaker:
            prev = merged[-1]
            prev.end = p.end
            prev.text = (prev.text + " " + p.text).strip()
        else:
            merged.append(p)
    return merged


def _speaker_at(t: float, turns: list[Turn]) -> str:
    """Speaker whose turn contains time *t*; nearest turn if t is in a gap."""
    for turn in turns:
        if turn.start <= t <= turn.end:
            return turn.speaker
    nearest = min(
        turns,
        key=lambda tr: 0 if tr.start <= t <= tr.end
        else min(abs(t - tr.start), abs(t - tr.end)),
    )
    return nearest.speaker


def _dominant_speaker(start: float, end: float, turns: list[Turn]) -> str:
    """Speaker with the most temporal overlap of [start, end]."""
    overlap: dict[str, float] = {}
    for turn in turns:
        lo, hi = max(start, turn.start), min(end, turn.end)
        if hi > lo:
            overlap[turn.speaker] = overlap.get(turn.speaker, 0.0) + (hi - lo)
    if not overlap:
        return _speaker_at((start + end) / 2, turns)
    return max(overlap, key=overlap.get)


def _ordered_speakers(segments: list[TranscriptSegment]) -> list[str]:
    seen: list[str] = []
    for s in segments:
        if s.speaker not in seen:
            seen.append(s.speaker)
    return seen


# --------------------------------------------------------------------------- #
# Emotion
# --------------------------------------------------------------------------- #
def _attach_emotions(
    wav_path: str,
    segments: list[TranscriptSegment],
    audio_weight: float,
    use_audio: bool,
    use_text: bool,
    progress: ProgressCb,
) -> None:
    from .emotion import EmotionAnalyzer

    analyzer = EmotionAnalyzer(
        audio_weight=audio_weight, use_audio=use_audio, use_text=use_text
    )
    samples, sr = _audio.load_waveform(wav_path)
    items = [
        (_audio.slice_waveform(samples, sr, seg.start, seg.end), sr, seg.text)
        for seg in segments
    ]
    # One batched pass over both models instead of per-segment inference.
    results = analyzer.analyze_batch(items)
    for seg, res in zip(segments, results):
        seg.emotion = res.label
        seg.emotion_score = res.score
        seg.emotion_scores = res.scores
        seg.audio_emotion = res.audio_label
        seg.text_emotion = res.text_label
    progress("Analyzing emotion", 0.95)
