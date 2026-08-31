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

import math
from dataclasses import dataclass, field, replace

from . import audio as _audio
from .runtime import require

# (name, device, compute_type) -> WhisperModel
_MODEL_CACHE: dict[tuple, object] = {}


@dataclass
class Word:
    start: float
    end: float
    text: str
    probability: float = 1.0


@dataclass
class RawSegment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0

    @property
    def confidence(self) -> float:
        """Segment confidence in 0..1, from the mean word probability.

        Word probabilities are the honest signal when we have them. Falling
        back on avg_logprob (a per-token log probability, typically -1..0)
        keeps a usable number when word timestamps are off.
        """
        if self.words:
            return sum(w.probability for w in self.words) / len(self.words)
        return min(1.0, max(0.0, math.exp(self.avg_logprob)))


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
    WhisperModel = require(
        "faster_whisper",
        purpose="needed to transcribe audio",
        install="pip install faster-whisper",
    ).WhisperModel

    dev, ct = _auto_device(device, compute_type)
    key = (model_name, dev, ct)
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = WhisperModel(model_name, device=dev, compute_type=ct)
    return _MODEL_CACHE[key]


def transcribe(
    audio,
    model_name: str = "base",
    language: str | None = None,
    word_timestamps: bool = True,
    vad_filter: bool = True,
    beam_size: int = 5,
    multilingual: bool = True,
    task: str = "transcribe",
    model=None,
) -> tuple[list[RawSegment], str]:
    """Transcribe *audio* (a WAV path or a 16 kHz float waveform).

    Returns (segments, detected_language).

    *vad_filter* drops silence before decoding (big speedup on real audio).

    *multilingual* re-detects the language on every 30s decode window and swaps
    the tokenizer, so a speaker switching language mid-recording is transcribed
    in the language they actually spoke instead of being force-decoded (and
    often mistranslated) into the first language detected. It is ignored when
    *language* pins a single language, and by English-only models.

    *task* is Whisper's own: "transcribe" writes what was said in the language
    it was said in; "translate" writes an English translation of it. Whisper
    has no other target language -- English is the only one it was trained to
    translate into.

    Pass a preloaded *model* to skip the cache lookup entirely.
    """
    model = model or load_model(model_name)

    seg_iter, info = model.transcribe(
        audio,
        language=language,
        task=task,
        word_timestamps=word_timestamps,
        vad_filter=vad_filter,
        beam_size=beam_size,
        # Pinning a language is an explicit instruction to stay in it.
        multilingual=multilingual and language is None,
        # Whisper conditions each 30s window on the text it produced for the
        # previous one. Across a language change that prompt is a block of the
        # *old* language, and the model follows it -- which is how a Hindi
        # stretch comes back written in English. Drop the carry-over whenever
        # the language is free to change.
        condition_on_previous_text=language is not None,
    )

    segments: list[RawSegment] = []
    for seg in seg_iter:  # generator — consuming it runs the decode
        words = [
            Word(
                start=float(w.start),
                end=float(w.end),
                text=w.word,
                probability=float(getattr(w, "probability", 1.0)),
            )
            for w in (seg.words or [])
            if w.start is not None and w.end is not None
        ]
        segments.append(
            RawSegment(
                start=float(seg.start),
                end=float(seg.end),
                text=seg.text.strip(),
                words=words,
                avg_logprob=float(getattr(seg, "avg_logprob", 0.0)),
                no_speech_prob=float(getattr(seg, "no_speech_prob", 0.0)),
            )
        )
    return segments, info.language


def shift_segments(segments: list[RawSegment], offset: float) -> list[RawSegment]:
    """Move *segments* (and their words) *offset* seconds later.

    Decoding a slice of a recording yields timestamps relative to the slice.
    Everything downstream -- diarization, speaker alignment, the language
    timeline -- works in whole-recording time, so the slice has to be put back
    where it came from.
    """
    return [
        replace(
            seg,
            start=seg.start + offset,
            end=seg.end + offset,
            words=[
                replace(w, start=w.start + offset, end=w.end + offset)
                for w in seg.words
            ],
        )
        for seg in segments
    ]


def transcribe_spans(
    wav_path: str,
    spans,
    *,
    model,
    task: str = "transcribe",
    word_timestamps: bool = True,
    beam_size: int = 5,
) -> list[RawSegment]:
    """Decode each language span with its own language pinned.

    *spans* is any sequence of objects with ``start``, ``end`` and
    ``language`` -- :class:`transcriber.language.LanguageSpan` in practice.

    This exists because letting Whisper pick the language during decoding is
    the weaker option when we have already worked it out. ``multilingual=True``
    re-detects on each 30s window in isolation, from one window's audio and
    nothing else; our timeline detects on overlapping windows and only accepts
    a switch two consecutive probes agree on, then decodes a whole span in one
    piece. Pinning the language also rules out the failure the user sees when
    detection wobbles: a non-English stretch written out in English.

    Spans are decoded independently, so no span can prompt the next one in the
    wrong language. VAD stays on: faster-whisper maps timestamps back onto the
    audio it was handed (``restore_speech_timestamps``), so they are still
    slice-relative and the offset below is still all that is needed -- while
    skipping silence keeps the decoder from filling it with invented text.
    """
    samples, sr = _audio.load_waveform(wav_path)

    out: list[RawSegment] = []
    for span in spans:
        chunk = _audio.slice_waveform(samples, sr, span.start, span.end)
        if chunk.size < sr // 10:        # under 100ms: nothing to decode
            continue
        segments, _ = transcribe(
            chunk,
            language=span.language,
            task=task,
            word_timestamps=word_timestamps,
            vad_filter=True,
            beam_size=beam_size,
            multilingual=False,
            model=model,
        )
        out.extend(shift_segments(segments, span.start))

    out.sort(key=lambda s: s.start)
    return out


def decode_chunk(
    chunk,
    *,
    model,
    language: str | None,
    task: str = "transcribe",
    beam_size: int = 5,
) -> str:
    """Decode one audio chunk into a single line of text.

    VAD is off: on a chunk that is already one utterance there is nothing to
    trim, and trimming could take the whole thing.
    """
    segments, _ = transcribe(
        chunk,
        language=language,
        task=task,
        word_timestamps=False,
        vad_filter=False,
        beam_size=beam_size,
        multilingual=False,
        model=model,
    )
    return " ".join(s.text.strip() for s in segments if s.text.strip()).strip()


def translate_each(wav_path: str, spans, *, model, beam_size: int = 5) -> list[str]:
    """One English translation per span, decoded from that span's own audio.

    Returns a list the same length as *spans*; an empty string means the span
    was too short to decode.

    Translating whole language stretches and matching the pieces to the
    transcript afterwards cannot be made to work: the two passes segment
    independently, so a three-second line gets handed a thirty-second
    paragraph and the two renderings stop describing the same audio.
    Decoding each line's own audio removes the alignment problem rather than
    improving the guess at it. The cost is context -- a short line is
    translated without the sentence around it.
    """
    samples, sr = _audio.load_waveform(wav_path)

    out: list[str] = []
    for span in spans:
        chunk = _audio.slice_waveform(samples, sr, span.start, span.end)
        if chunk.size < sr // 2:            # under 0.5s: nothing to translate
            out.append("")
            continue
        out.append(decode_chunk(chunk, model=model, language=span.language,
                                task="translate", beam_size=beam_size))
    return out
