"""Whisper decoding tuned for a code-switched music lesson.

Three things differ from the plain transcriber in `transcriber/`:

* **A domain prompt.** Whisper's ``initial_prompt`` conditions the decoder, and
  priming it with "raag, bandish, meend, teentaal, Yaman…" is the only lever
  available for a domain it barely saw in training.
* **Per-window language detection.** A guru switches between Hindi and English
  inside a single sentence. faster-whisper >= 1.1 can re-detect the language
  every window (``multilingual=True``); on older versions we fall back to a
  single detected language, which still works but labels the file, not the
  sentence.
* **No hallucination on singing.** Whisper cannot help inventing words over
  alaap. ``clip_spans`` restricts decoding to the stretches the segmenter
  called speech; where the installed version cannot clip, the caller drops the
  sung segments afterwards instead.

The model cache is shared with `transcriber.transcribe`, so a GUI that runs
both tools loads each model once.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from transcriber.transcribe import RawSegment, Word, load_model


@dataclass
class SpeechSegment(RawSegment):
    """A Whisper segment plus the language it was decoded as."""

    language: str = ""
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0
    words: list[Word] = field(default_factory=list)


def transcribe_speech(
    wav_path: str,
    model_name: str = "small",
    language: str | None = None,
    initial_prompt: str | None = None,
    clip_spans: list[tuple[float, float]] | None = None,
    multilingual: bool = True,
    beam_size: int = 5,
    model=None,
) -> tuple[list[SpeechSegment], str]:
    """Decode *wav_path* and return (segments, dominant language).

    *clip_spans* is a list of (start, end) second pairs to decode; everything
    else is skipped, which both saves time and removes the opportunity to
    hallucinate over music.
    """
    model = model or load_model(model_name)

    kwargs: dict = {
        "language": language,
        "word_timestamps": True,
        "vad_filter": True,
        "beam_size": beam_size,
        "initial_prompt": initial_prompt,
        # Whisper's own guards against looping on non-speech. Worth having even
        # with the segmenter in front, because a tanpura is not silence.
        "condition_on_previous_text": False,
        "no_speech_threshold": 0.6,
    }
    if multilingual and language is None:
        kwargs["multilingual"] = True
    if clip_spans:
        kwargs["clip_timestamps"] = _format_clips(clip_spans)

    seg_iter, info = _call_with_supported_kwargs(model, wav_path, kwargs)

    segments: list[SpeechSegment] = []
    for seg in seg_iter:
        words = [
            Word(start=float(w.start), end=float(w.end), text=w.word)
            for w in (seg.words or [])
            if w.start is not None and w.end is not None
        ]
        segments.append(
            SpeechSegment(
                start=float(seg.start),
                end=float(seg.end),
                text=seg.text.strip(),
                words=words,
                language=str(getattr(seg, "language", "") or info.language or ""),
                avg_logprob=float(getattr(seg, "avg_logprob", 0.0) or 0.0),
                no_speech_prob=float(getattr(seg, "no_speech_prob", 0.0) or 0.0),
            )
        )
    return segments, str(info.language or "")


def _format_clips(spans: list[tuple[float, float]]) -> str:
    """faster-whisper wants clip timestamps as "start,end,start,end,…"."""
    flat: list[str] = []
    for start, end in spans:
        if end - start <= 0.05:
            continue
        flat.append(f"{max(0.0, start):.2f}")
        flat.append(f"{end:.2f}")
    return ",".join(flat)


def _call_with_supported_kwargs(model, wav_path: str, kwargs: dict):
    """Call ``model.transcribe``, dropping kwargs this faster-whisper lacks.

    ``multilingual`` and ``clip_timestamps`` arrived in different releases, and
    a lesson transcript is more useful degraded than not produced at all — so a
    TypeError from an older version costs the feature, not the run.
    """
    attempt = dict(kwargs)
    for _ in range(len(kwargs) + 1):
        try:
            return model.transcribe(wav_path, **attempt)
        except TypeError as exc:
            unsupported = _unsupported_kwarg(str(exc), attempt)
            if unsupported is None:
                raise
            attempt.pop(unsupported)
    raise RuntimeError("Could not find a supported faster-whisper call signature")


def _unsupported_kwarg(message: str, kwargs: dict) -> str | None:
    for name in ("multilingual", "clip_timestamps", "initial_prompt"):
        if name in kwargs and name in message:
            return name
    return None
