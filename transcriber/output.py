"""Render a TranscriptResult to text, JSON, or SRT subtitles.

Language tags appear only when the recording actually contains more than one
language -- tagging every line "[en]" in a monolingual transcript is noise.
Low-confidence lines are marked so a reader knows which words to distrust
rather than having to re-listen to the whole thing.
"""
from __future__ import annotations

import json

from .core import TranscriptResult, TranscriptSegment


def _fmt_ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_srt_ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# Whisper word probabilities below this usually mean a garbled or guessed
# phrase. Marking them beats silently presenting a guess as a transcript.
LOW_CONFIDENCE = 0.60


def to_text(
    result: TranscriptResult,
    show_emotion: bool = True,
    show_language: bool | None = None,
    mark_low_confidence: bool = True,
) -> str:
    """Human-readable transcript, one block per segment.

    *show_language* defaults to tagging only multilingual recordings.
    """
    if show_language is None:
        show_language = result.is_multilingual

    lines: list[str] = []
    for seg in result.segments:
        tags = ""
        if show_language:
            tags += f" [{seg.language}]"
        if show_emotion:
            tags += f" [{seg.emotion} {seg.emotion_score:.0%}]"
        if mark_low_confidence and seg.confidence < LOW_CONFIDENCE:
            tags += f" [low confidence {seg.confidence:.0%}]"
        lines.append(f"[{_fmt_ts(seg.start)}] {seg.speaker}{tags}: {seg.text}")
    return "\n".join(lines) + ("\n" if lines else "")


def to_summary(result: TranscriptResult) -> str:
    """One-paragraph header: languages heard and who was recognised."""
    parts: list[str] = []
    if result.languages:
        langs = ", ".join(
            f"{lang} ({secs:.0f}s)" if secs else lang
            for lang, secs in result.languages.items()
        )
        parts.append(f"Languages: {langs}")
    if result.identified:
        named = ", ".join(
            f"{label} -> {name}" for label, name in sorted(result.identified.items())
        )
        parts.append(f"Recognised: {named}")
    if result.unmatched:
        parts.append(
            "Unrecognised: "
            + "; ".join(
                f"{label} ({reason})"
                for label, reason in sorted(result.unmatched.items())
            )
        )
    return "\n".join(parts)


def to_json(result: TranscriptResult, indent: int = 2) -> str:
    return json.dumps(result.to_dict(), indent=indent, ensure_ascii=False)


def to_srt(result: TranscriptResult, show_emotion: bool = True) -> str:
    """SRT subtitles; speaker and emotion are prepended to each cue."""
    blocks: list[str] = []
    for i, seg in enumerate(result.segments, start=1):
        tag = f" ({seg.emotion})" if show_emotion else ""
        blocks.append(
            f"{i}\n"
            f"{_fmt_srt_ts(seg.start)} --> {_fmt_srt_ts(seg.end)}\n"
            f"{seg.speaker}{tag}: {seg.text}\n"
        )
    return "\n".join(blocks)


def to_vtt(result: TranscriptResult, show_emotion: bool = True) -> str:
    """WebVTT subtitles -- what browsers and most web players want."""
    blocks = ["WEBVTT", ""]
    for seg in result.segments:
        tag = f" ({seg.emotion})" if show_emotion else ""
        blocks.append(
            f"{_fmt_srt_ts(seg.start).replace(',', '.')} --> "
            f"{_fmt_srt_ts(seg.end).replace(',', '.')}\n"
            f"<v {seg.speaker}>{seg.speaker}{tag}: {seg.text}\n"
        )
    return "\n".join(blocks)


def render(result: TranscriptResult, fmt: str, show_emotion: bool = True) -> str:
    fmt = fmt.lower()
    if fmt == "txt":
        return to_text(result, show_emotion)
    if fmt == "vtt":
        return to_vtt(result, show_emotion)
    if fmt == "json":
        return to_json(result)
    if fmt == "srt":
        return to_srt(result, show_emotion)
    raise ValueError(f"Unknown output format: {fmt!r} (use txt/json/srt/vtt)")
