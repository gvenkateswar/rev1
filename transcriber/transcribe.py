"""Whisper transcription via faster-whisper (CTranslate2).

faster-whisper runs the same Whisper models ~4x faster than openai-whisper on
CPU, uses less memory (int8), and ships a built-in VAD that skips silence so we
don't pay to decode dead air. It still emits word-level timestamps, which the
diarizer needs to split a segment when the speaker changes mid-sentence.

Loaded models are cached at module scope keyed by (name, device, compute_type).
Because the Streamlit script and the CLI both run in a single long-lived
process, this makes every run after the first skip model loading entirely.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# (name, device, compute_type) -> WhisperModel
_MODEL_CACHE: dict[tuple, object] = {}


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


def _auto_device(
    device: str | None, compute_type: str | None
) -> tuple[str, str]:
    """Pick (device, compute_type): CUDA+float16 if available, else CPU+int8."""
    if device is None:
        try:
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
    if compute_type is None:
        compute_type = "float16" if device == "cuda" else "int8"
    return device, compute_type


def load_model(
    model_name: str = "base",
    device: str | None = None,
    compute_type: str | None = None,
):
    """Load (and cache) a faster-whisper model.

    *model_name* is any Whisper size (tiny/base/small/medium/large-v3) or a
    distil-whisper repo id (e.g. "distil-large-v3") for extra speed.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - dependency hint
        raise RuntimeError(
            "faster-whisper is not installed. Run: pip install faster-whisper"
        ) from exc

    dev, ct = _auto_device(device, compute_type)
    key = (model_name, dev, ct)
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = WhisperModel(model_name, device=dev, compute_type=ct)
    return _MODEL_CACHE[key]


def transcribe(
    wav_path: str,
    model_name: str = "base",
    language: str | None = None,
    word_timestamps: bool = True,
    vad_filter: bool = True,
    beam_size: int = 5,
    model=None,
) -> tuple[list[RawSegment], str]:
    """Transcribe *wav_path*. Returns (segments, detected_language).

    *vad_filter* drops silence before decoding (big speedup on real audio).
    Pass a preloaded *model* to skip the cache lookup entirely.
    """
    model = model or load_model(model_name)

    seg_iter, info = model.transcribe(
        wav_path,
        language=language,
        word_timestamps=word_timestamps,
        vad_filter=vad_filter,
        beam_size=beam_size,
    )

    segments: list[RawSegment] = []
    for seg in seg_iter:  # generator — consuming it runs the decode
        words = [
            Word(start=float(w.start), end=float(w.end), text=w.word)
            for w in (seg.words or [])
            if w.start is not None and w.end is not None
        ]
        segments.append(
            RawSegment(
                start=float(seg.start),
                end=float(seg.end),
                text=seg.text.strip(),
                words=words,
            )
        )
    return segments, info.language
