"""Speaker-diarizing transcriber with fused audio+text emotion detection.

Public surface:

    from transcriber import transcribe_file, TranscriptSegment

`transcribe_file` runs the whole pipeline (extract -> Whisper -> diarize ->
emotion) and returns a list of :class:`TranscriptSegment`. Heavy ML deps are
imported lazily inside the submodules, so importing this package is cheap.
"""
from __future__ import annotations

import os

# Avoid macOS "OMP: Error #15" aborts when PyTorch and CTranslate2/onnxruntime
# each bring their own OpenMP runtime. Set before any of them import. Users can
# override by exporting KMP_DUPLICATE_LIB_OK themselves.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from .core import TranscriptSegment, TranscriptResult, transcribe_file

__all__ = ["TranscriptSegment", "TranscriptResult", "transcribe_file"]
__version__ = "0.1.0"
