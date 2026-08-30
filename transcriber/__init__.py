"""Speaker-diarizing transcriber with fused audio+text emotion detection.

Public surface:

    from transcriber import transcribe_file, TranscriptSegment

`transcribe_file` runs the whole pipeline (extract -> detect languages ->
Whisper -> diarize -> identify speakers -> emotion) and returns a
:class:`TranscriptResult`. Heavy ML deps are imported lazily inside the
submodules, so importing this package is cheap.

Speakers are remembered across runs in a local :class:`SpeakerStore`, so naming
someone once makes them auto-tagged in every later transcript.
"""
from __future__ import annotations

from .core import TranscriptSegment, TranscriptResult, transcribe_file
from .speakerdb import Speaker, SpeakerStore

__all__ = [
    "TranscriptSegment",
    "TranscriptResult",
    "transcribe_file",
    "Speaker",
    "SpeakerStore",
]
__version__ = "0.2.0"
