"""Whisper transcription with segment- and word-level timestamps.

We keep word timestamps because the diarizer works at a finer granularity than
Whisper's segments; word times let us split a Whisper segment at the exact
point where the speaker changes (see ``core.assign_speakers``).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class RawSegment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


def transcribe(
    wav_path: str,
    model_name: str = "base",
    language: str | None = None,
    word_timestamps: bool = True,
) -> tuple[list[RawSegment], str]:
    """Transcribe *wav_path*.

    Returns (segments, detected_language). *model_name* is any Whisper size
    (tiny/base/small/medium/large) — larger is more accurate but slower.
    """
    try:
        import whisper
    except ImportError as exc:  # pragma: no cover - dependency hint
        raise RuntimeError(
            "openai-whisper is not installed. Run: pip install openai-whisper"
        ) from exc

    model = whisper.load_model(model_name)
    result = model.transcribe(
        wav_path,
        language=language,
        word_timestamps=word_timestamps,
        verbose=False,
    )

    segments: list[RawSegment] = []
    for seg in result.get("segments", []):
        words = [
            Word(start=float(w["start"]), end=float(w["end"]), text=w["word"])
            for w in seg.get("words", [])
            if w.get("start") is not None and w.get("end") is not None
        ]
        segments.append(
            RawSegment(
                start=float(seg["start"]),
                end=float(seg["end"]),
                text=seg["text"].strip(),
                words=words,
            )
        )
    return segments, result.get("language", language or "unknown")
