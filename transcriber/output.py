"""Render a TranscriptResult to text, JSON, or SRT subtitles."""
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


def to_text(result: TranscriptResult, show_emotion: bool = True) -> str:
    """Human-readable transcript, one block per segment."""
    lines: list[str] = []
    for seg in result.segments:
        tag = ""
        if show_emotion:
            tag = f" [{seg.emotion} {seg.emotion_score:.0%}]"
        lines.append(f"[{_fmt_ts(seg.start)}] {seg.speaker}{tag}: {seg.text}")
    return "\n".join(lines) + ("\n" if lines else "")


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


def render(result: TranscriptResult, fmt: str, show_emotion: bool = True) -> str:
    fmt = fmt.lower()
    if fmt == "txt":
        return to_text(result, show_emotion)
    if fmt == "json":
        return to_json(result)
    if fmt == "srt":
        return to_srt(result, show_emotion)
    raise ValueError(f"Unknown output format: {fmt!r} (use txt/json/srt)")
