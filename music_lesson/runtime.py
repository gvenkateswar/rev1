"""Process-level guards for the mess that is native ML wheels on macOS.

The lesson pipeline can end up loading two Intel OpenMP runtimes into one
process: CTranslate2 (faster-whisper) bundles a libiomp5, and so does torch,
which Resemblyzer imports for speaker diarization. On macOS the second one to
initialize calls abort() — "OMP: Error #15" — and takes the whole app with it.

The real fix is not to load torch at all, and the transcription path no longer
does (see `transcriber.transcribe._auto_device`). But diarization legitimately
needs torch, so for the case where both runtimes genuinely coexist we set
Intel's documented escape hatch, KMP_DUPLICATE_LIB_OK — *before* either
library loads, which is why this runs from the package __init__.

Intel calls the workaround unsafe because two OpenMP runtimes can, in theory,
mis-schedule threads and corrupt results. In practice it is what every project
mixing torch with another OpenMP-linked wheel ships. Anyone who wants the
strict behaviour back can export KMP_DUPLICATE_LIB_OK=FALSE, which is
respected: an explicit setting is never overwritten.
"""
from __future__ import annotations

import os
import sys

_applied = False


def ensure_single_openmp() -> None:
    """Allow duplicate OpenMP runtimes on macOS unless the user said otherwise.

    Must run before torch or ctranslate2 are imported; environment variables
    are read once, when the dylib initializes.
    """
    global _applied
    if sys.platform != "darwin":
        return
    if "KMP_DUPLICATE_LIB_OK" in os.environ:
        return                      # the user's choice, whichever way it goes
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    _applied = True


def openmp_workaround_applied() -> bool:
    """Whether this process is running under the duplicate-OpenMP escape hatch."""
    return _applied
