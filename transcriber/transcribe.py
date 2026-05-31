"""Whisper transcription with two selectable engines.

* ``openai`` - openai-whisper, pure PyTorch. The most compatible choice: it
  shares one runtime with the emotion models, so there's no second OpenMP/MKL
  library to clash with. Works on older CPUs.
* ``faster`` - faster-whisper (CTranslate2). ~4x faster on CPU with a built-in
  VAD, BUT CTranslate2 4.x needs a modern (AVX) CPU and bundles its own OpenMP,
  which segfaults alongside PyTorch on some older Intel Macs. Opt in when your
  machine supports it.

Both return the same (list[RawSegment], language). Loaded models are cached at
module scope keyed by (backend, name, device) so repeat runs skip loading.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# (backend, name, device, compute_type) -> model
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


def transcribe(
    wav_path: str,
    model_name: str = "base",
    language: str | None = None,
    word_timestamps: bool = True,
    vad_filter: bool = True,
    beam_size: int = 5,
    backend: str = "openai",
    model=None,
) -> tuple[list[RawSegment], str]:
    """Transcribe *wav_path* with the chosen engine."""
    if backend == "faster":
        return _transcribe_faster(
            wav_path, model_name, language, word_timestamps, vad_filter,
            beam_size, model,
        )
    if backend == "openai":
        return _transcribe_openai(
            wav_path, model_name, language, word_timestamps, model,
        )
    raise ValueError(f"Unknown whisper backend: {backend!r} (use openai/faster)")


# --------------------------------------------------------------------------- #
# Backend: openai-whisper (PyTorch) — default, most compatible
# --------------------------------------------------------------------------- #
def _openai_device() -> str:
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def _load_openai(model_name: str):
    try:
        import whisper
    except ImportError as exc:  # pragma: no cover - dependency hint
        raise RuntimeError(
            "openai-whisper is not installed. Run: pip install openai-whisper"
        ) from exc

    dev = _openai_device()
    key = ("openai", model_name, dev, "")
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = whisper.load_model(model_name, device=dev)
    return _MODEL_CACHE[key]


def _transcribe_openai(
    wav_path, model_name, language, word_timestamps, model,
) -> tuple[list[RawSegment], str]:
    model = model or _load_openai(model_name)
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
        segments.append(RawSegment(
            start=float(seg["start"]), end=float(seg["end"]),
            text=seg["text"].strip(), words=words,
        ))
    return segments, result.get("language", language or "unknown")


# --------------------------------------------------------------------------- #
# Backend: faster-whisper (CTranslate2) — opt-in, needs a modern CPU
# --------------------------------------------------------------------------- #
def _auto_device(
    device: str | None, compute_type: str | None
) -> tuple[str, str]:
    if device is None:
        try:
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
    if compute_type is None:
        compute_type = "float16" if device == "cuda" else "int8"
    return device, compute_type


def _load_faster(model_name: str, device=None, compute_type=None):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "faster-whisper is not installed. Run: pip install faster-whisper"
        ) from exc

    dev, ct = _auto_device(device, compute_type)
    key = ("faster", model_name, dev, ct)
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = WhisperModel(model_name, device=dev, compute_type=ct)
    return _MODEL_CACHE[key]


def _transcribe_faster(
    wav_path, model_name, language, word_timestamps, vad_filter, beam_size, model,
) -> tuple[list[RawSegment], str]:
    model = model or _load_faster(model_name)
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
        segments.append(RawSegment(
            start=float(seg.start), end=float(seg.end),
            text=seg.text.strip(), words=words,
        ))
    return segments, info.language
