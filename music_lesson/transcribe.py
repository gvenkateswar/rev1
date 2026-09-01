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
    rescripted: int = 0            # off-list windows re-decoded as the primary
    foreign_languages: list[str] = field(default_factory=list)   # tags seen off-list


# The language picker: display name -> Whisper language code. The main
# South Asian languages (Indo-Aryan and Dravidian), because a lesson archive
# can hold Hindustani taalim in Hindi/English one day and Carnatic teaching in
# Telugu or Tamil the next.
SOUTH_ASIAN_LANGUAGES: dict[str, str] = {
    "Hindi": "hi", "English": "en", "Bengali": "bn", "Sanskrit": "sa",
    "Punjabi": "pa", "Marathi": "mr", "Gujarati": "gu",
    "Urdu (kept in Nastaliq)": "ur", "Tamil": "ta", "Telugu": "te",
    "Kannada": "kn", "Malayalam": "ml", "Nepali": "ne", "Odia": "or",
    "Assamese": "as", "Sinhala": "si",
}

# What a lesson recording is allowed to be unless told otherwise. Left free,
# Whisper's per-window detector on accented, code-switched audio with singing
# bleeding through picks Tibetan, Vietnamese or Greek for entire windows and
# decodes them in those scripts. Note "ur" is absent: spoken Urdu IS the Hindi
# the guru is speaking, and leaving it off the list is what routes those
# windows to a Devanagari re-decode.
DEFAULT_ALLOWED_LANGUAGES: tuple[str, ...] = ("hi", "en", "bn")

# Which Unicode letter ranges each language's text should sit in. Latin is
# always acceptable (English, and romanized asides inside any language).
_SCRIPT_RANGES: dict[str, tuple[tuple[int, int], ...]] = {
    "hi": ((0x0900, 0x097F),), "mr": ((0x0900, 0x097F),),
    "sa": ((0x0900, 0x097F),), "ne": ((0x0900, 0x097F),),
    "bn": ((0x0980, 0x09FF),), "as": ((0x0980, 0x09FF),),
    "pa": ((0x0A00, 0x0A7F),), "gu": ((0x0A80, 0x0AFF),),
    "or": ((0x0B00, 0x0B7F),), "ta": ((0x0B80, 0x0BFF),),
    "te": ((0x0C00, 0x0C7F),), "kn": ((0x0C80, 0x0CFF),),
    "ml": ((0x0D00, 0x0D7F),), "si": ((0x0D80, 0x0DFF),),
    "ur": ((0x0600, 0x06FF), (0x0750, 0x077F)),
    "en": (),
}

_LATIN_RANGES = ((0x0041, 0x024F), (0x1E00, 0x1EFF))



def transcribe_speech(
    wav_path: str,
    model_name: str = "small",
    language: str | None = None,
    hotwords: str | None = None,
    initial_prompt: str | None = None,
    clip_spans: list[tuple[float, float]] | None = None,
    multilingual: bool = True,
    allowed_languages: tuple[str, ...] = DEFAULT_ALLOWED_LANGUAGES,
    hotwords_devanagari: str | None = None,
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

    rescripted, foreign = 0, []
    if language is None and "clip_timestamps" not in dropped:
        segments, rescripted, foreign = _redecode_off_list(
            model, wav_path, segments, tuple(allowed_languages),
            hotwords_devanagari, beam_size,
        )

    return SpeechResult(
        segments=segments,
        language=str(info.language or ""),
        speech_seconds=total,
        clips=len(clip_spans) if clip_spans else 1,
        dropped_options=dropped,
        rescripted=rescripted,
        foreign_languages=foreign,
    )


def primary_language(allowed: tuple[str, ...]) -> str:
    """The language off-list windows are re-decoded as: the first non-English."""
    for code in allowed:
        if code != "en":
            return code
    return "en"


def _letter_in_ranges(ch: str, ranges) -> bool:
    point = ord(ch)
    return any(low <= point <= high for low, high in ranges)


def _script_acceptable(text: str, allowed: tuple[str, ...]) -> bool:
    """True if the text sits in the scripts the allowed languages imply.

    Counted over characters, not just letters: Whisper's junk output includes
    symbol blocks (Tibetan marks, box-drawing, U+FFFD) that ``isalpha`` never
    sees, and a window made of nothing but those must fail this check.
    """
    ok_ranges = list(_LATIN_RANGES)
    for code in allowed:
        ok_ranges.extend(_SCRIPT_RANGES.get(code, ()))

    good = bad = 0
    for ch in text:
        if ch.isascii() or _letter_in_ranges(ch, ok_ranges):
            if ch.isalpha():
                good += 1
        elif ord(ch) >= 0x0370 and not ch.isspace():
            bad += 1                # Greek and beyond: some other script's glyph
    if bad == 0:
        return True
    return bad / max(good + bad, 1) < 0.2


def _redecode_off_list(
    model,
    wav_path: str,
    segments: list[SpeechSegment],
    allowed: tuple[str, ...],
    hotwords_devanagari: str | None,
    beam_size: int,
) -> tuple[list[SpeechSegment], int, list[str]]:
    """Re-decode windows whose language or script fell outside the list.

    Two things flag a window: a language tag not in *allowed* (the detector
    picked Tibetan for a Hindi sentence), or text whose letters sit outside
    the allowed scripts (junk glyphs under an allowed tag). Flagged spans are
    decoded again with the language pinned to the primary allowed language.

    The re-decode's own prompt matters more than it looks: hotwords bias not
    just vocabulary but *script* — a Devanagari decode prompted with Latin
    text tends to answer in Latin. So the Hindi pass gets Devanagari hotwords,
    and other languages get none rather than a wrong-script prompt.
    """
    flagged = [
        seg for seg in segments
        if seg.language not in allowed
        or not _script_acceptable(seg.text, allowed)
    ]
    if not flagged:
        return segments, 0, []

    foreign = sorted({seg.language for seg in flagged if seg.language})
    target = primary_language(allowed)

    spans: list[tuple[float, float]] = []
    for seg in sorted(flagged, key=lambda s: s.start):
        start, end = max(0.0, seg.start - 0.2), seg.end + 0.2
        if spans and start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], end))
        else:
            spans.append((start, end))

    try:
        seg_iter, _info = model.transcribe(
            wav_path,
            language=target,
            word_timestamps=True,
            beam_size=beam_size,
            hotwords=hotwords_devanagari if target == "hi" else None,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            clip_timestamps=_format_clips(spans),
        )
        redecoded = [
            SpeechSegment(
                start=float(seg.start), end=float(seg.end),
                text=seg.text.strip(),
                words=[
                    Word(start=float(w.start), end=float(w.end), text=w.word)
                    for w in (seg.words or [])
                    if w.start is not None and w.end is not None
                ],
                language=target,
                avg_logprob=float(getattr(seg, "avg_logprob", 0.0) or 0.0),
                no_speech_prob=float(getattr(seg, "no_speech_prob", 0.0) or 0.0),
            )
            for seg in seg_iter
            if seg.text.strip()
        ]
    except TypeError:
        return segments, 0, []      # a signature this old was already reported

    flagged_ids = {id(seg) for seg in flagged}
    merged = [seg for seg in segments if id(seg) not in flagged_ids] + redecoded
    merged.sort(key=lambda seg: seg.start)
    return merged, len(flagged), foreign


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
