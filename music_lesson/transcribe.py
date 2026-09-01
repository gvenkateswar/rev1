"""Whisper decoding tuned for a code-switched music lesson.

Four things differ from the plain transcriber in `transcriber/`:

* **Domain vocabulary on every window.** Whisper has barely heard this
  vocabulary, and the fix is to put it in the decoder's prompt. Note that
  ``initial_prompt`` is *not* the way to do it: faster-whisper applies it to
  the first 30-second window only, so on a forty-minute lesson it conditions
  the first half-minute and nothing else. ``hotwords`` is re-injected into
  every window's prompt, which is what a domain glossary actually needs.
* **Per-window language detection.** A guru switches between Hindi and English
  inside a single sentence. faster-whisper can re-detect the language every
  window (``multilingual=True``); on older versions we fall back to a single
  detected language, which still works but labels the file, not the sentence.
* **No hallucination on singing.** Whisper cannot help inventing words over
  alaap. ``clip_timestamps`` restricts decoding to the stretches the segmenter
  called speech. Every clip is padded to a full 30-second window before the
  encoder runs, so the caller coalesces them first — see
  :func:`music_lesson.segmentation.speech_spans`.
* **Progress you can watch.** Decoding is by far the longest stage, and a bar
  that sits at 40% for half an hour is indistinguishable from a hang. The
  generator is consumed here, so progress is reported as it yields.

The model cache is shared with `transcriber.transcribe`, so a GUI that runs
both tools loads each model once.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from transcriber.transcribe import RawSegment, Word, load_model


@dataclass
class SpeechSegment(RawSegment):
    """A Whisper segment plus the language it was decoded as."""

    language: str = ""
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0
    words: list[Word] = field(default_factory=list)


@dataclass
class SpeechResult:
    segments: list[SpeechSegment]
    language: str
    speech_seconds: float          # audio actually handed to the decoder
    clips: int                     # how many windows that was split across
    dropped_options: list[str]     # kwargs this faster-whisper did not support


def transcribe_speech(
    wav_path: str,
    model_name: str = "small",
    language: str | None = None,
    hotwords: str | None = None,
    initial_prompt: str | None = None,
    clip_spans: list[tuple[float, float]] | None = None,
    multilingual: bool = True,
    beam_size: int = 5,
    progress: Callable[[float], None] | None = None,
    model=None,
) -> SpeechResult:
    """Decode *wav_path*, restricted to *clip_spans* if given.

    *progress* is called with a 0..1 fraction of the speech decoded so far.
    """
    model = model or load_model(model_name)

    kwargs: dict = {
        "language": language,
        "word_timestamps": True,
        "beam_size": beam_size,
        "hotwords": hotwords,
        # Kept alongside hotwords purely as a fallback for faster-whisper
        # versions predating hotwords support; it conditions the first window.
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
    else:
        # Without clips, fall back to Whisper's own VAD so silence is skipped.
        # (faster-whisper ignores vad_filter whenever clip_timestamps is set.)
        kwargs["vad_filter"] = True

    seg_iter, info, dropped = _call_with_supported_kwargs(model, wav_path, kwargs)
    if "clip_timestamps" in dropped:
        clip_spans = None          # this version decoded the whole file

    total = (
        sum(end - start for start, end in clip_spans)
        if clip_spans else float(getattr(info, "duration", 0.0) or 0.0)
    )

    segments: list[SpeechSegment] = []
    for seg in seg_iter:           # generator — consuming it runs the decode
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
        if progress and total > 0:
            progress(min(_speech_elapsed(float(seg.end), clip_spans) / total, 1.0))

    return SpeechResult(
        segments=segments,
        language=str(info.language or ""),
        speech_seconds=total,
        clips=len(clip_spans) if clip_spans else 1,
        dropped_options=dropped,
    )


def _format_clips(spans: list[tuple[float, float]]) -> str:
    """faster-whisper wants clip timestamps as "start,end,start,end,…"."""
    flat: list[str] = []
    for start, end in spans:
        if end - start <= 0.05:
            continue
        flat.append(f"{max(0.0, start):.2f}")
        flat.append(f"{end:.2f}")
    return ",".join(flat)


def _speech_elapsed(
    position: float, clip_spans: list[tuple[float, float]] | None
) -> float:
    """How much *decoded* audio precedes *position* in the timeline.

    With clips, wall-clock position runs ahead of decoding progress by all the
    singing that was skipped, so a bar driven by raw timestamps would lurch.
    """
    if not clip_spans:
        return position
    elapsed = 0.0
    for start, end in clip_spans:
        if position >= end:
            elapsed += end - start
        elif position > start:
            elapsed += position - start
            break
        else:
            break
    return elapsed


def _call_with_supported_kwargs(model, wav_path: str, kwargs: dict):
    """Call ``model.transcribe``, dropping kwargs this faster-whisper lacks.

    ``multilingual``, ``hotwords`` and ``clip_timestamps`` arrived in different
    releases, and a lesson transcript is more useful degraded than not produced
    at all — so a TypeError from an older version costs the feature, not the
    run. What was dropped is reported back, because silently losing the sung
    filter would look like nothing more than a slow, oddly chatty transcript.
    """
    attempt = dict(kwargs)
    dropped: list[str] = []
    for _ in range(len(kwargs) + 1):
        try:
            seg_iter, info = model.transcribe(wav_path, **attempt)
            return seg_iter, info, dropped
        except TypeError as exc:
            unsupported = _unsupported_kwarg(str(exc), attempt)
            if unsupported is None:
                raise
            attempt.pop(unsupported)
            dropped.append(unsupported)
            if unsupported == "clip_timestamps":
                attempt["vad_filter"] = True
    raise RuntimeError("Could not find a supported faster-whisper call signature")


def _unsupported_kwarg(message: str, kwargs: dict) -> str | None:
    for name in ("multilingual", "hotwords", "clip_timestamps",
                 "initial_prompt", "vad_filter"):
        if name in kwargs and name in message:
            return name
    return None
