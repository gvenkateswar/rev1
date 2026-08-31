"""Transcriber for Hindustani classical music lessons.

Public surface:

    from music_lesson import transcribe_lesson, LessonSegment

`transcribe_lesson` runs the whole pipeline — pitch tracking, tonic detection,
swara segmentation, sung/spoken separation, Whisper on the spoken parts,
diarization, vocabulary repair — and returns a :class:`LessonResult`.

Heavy ML dependencies are imported lazily inside the submodules, so importing
this package (or the pure-DSP modules `pitch`, `swara`, `raga`, `translit`,
`lexicon`) costs nothing.
"""
from __future__ import annotations

from .core import (
    ATTEMPT,
    DEMONSTRATION,
    INSTRUCTION,
    LessonResult,
    LessonSegment,
    transcribe_lesson,
)

__all__ = [
    "transcribe_lesson",
    "LessonResult",
    "LessonSegment",
    "INSTRUCTION",
    "DEMONSTRATION",
    "ATTEMPT",
]
__version__ = "0.1.0"
