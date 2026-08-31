"""Process-level setup that must happen before any ML library loads.

faster-whisper (via ctranslate2) and torch each bundle their *own* copy of the
Intel OpenMP runtime, ``libiomp5``. This pipeline needs both libraries, so both
copies get loaded into one process, and on macOS the second one to initialize
aborts the process outright:

    OMP: Error #15: Initializing libiomp5.dylib, but found libiomp5.dylib
    already initialized.

That abort is not catchable -- it is ``__kmp_abort_process`` calling
``abort()``, so there is no exception to handle and no traceback, just a crash
report. The only fix is to set ``KMP_DUPLICATE_LIB_OK`` *before* either library
is imported, which is why this module exists and why the package imports it
first.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys

# Intel's own docs warn this "may cause crashes or silently produce incorrect
# results". That warning is aimed at mixing *different* OpenMP runtimes (GNU
# libgomp against Intel libiomp5). Here both copies are the same libiomp5 build
# shipped by two wheels, which is the benign case -- and the alternative is not
# a subtle numeric issue but a guaranteed hard abort. Set TRANSCRIBER_NO_OMP_FIX=1
# to opt out and get the crash back (useful when diagnosing a different problem).
_OMP_FLAG = "KMP_DUPLICATE_LIB_OK"
_OPT_OUT = "TRANSCRIBER_NO_OMP_FIX"


def configure_openmp(env: dict | None = None) -> bool:
    """Allow the duplicate OpenMP runtime. Returns True if we set the flag.

    Respects an existing value: if the user already set ``KMP_DUPLICATE_LIB_OK``
    (either way), that is a deliberate choice and we leave it alone.
    """
    env = os.environ if env is None else env
    if env.get(_OPT_OUT):
        return False
    if _OMP_FLAG in env:
        return False
    env[_OMP_FLAG] = "TRUE"
    return True


def is_rosetta() -> bool:
    """True if this x86_64 process is being translated on Apple Silicon.

    ``platform.machine()`` reports "x86_64" under Rosetta and cannot tell the
    difference, so ask the kernel instead.
    """
    if platform.system() != "Darwin":
        return False
    try:
        proc = subprocess.run(
            ["sysctl", "-n", "sysctl.proc_translated"],
            capture_output=True, text=True, timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        # Missing or unresponsive sysctl is not worth failing over; we just
        # lose the advisory warning.
        return False
    return proc.stdout.strip() == "1"


def environment_warnings() -> list[str]:
    """Advisory notes about a setup that will be slow or fragile.

    Returns an empty list when nothing is worth saying. Kept separate from
    :func:`configure_openmp` because this one shells out, and import time is
    the wrong place to pay for that.
    """
    notes: list[str] = []

    if is_rosetta():
        notes.append(
            "Running x86_64 Python under Rosetta on Apple Silicon. Transcription "
            "will be several times slower than it needs to be, and the x86 "
            "wheels are what force two copies of the OpenMP runtime into one "
            "process. Install a native arm64 Python (e.g. python.org's "
            "universal2 build or `brew install python@3.12`) and reinstall the "
            "requirements into a fresh venv."
        )

    if sys.version_info < (3, 10):
        notes.append(
            f"Python {sys.version_info[0]}.{sys.version_info[1]} is older "
            "than the 3.10+ these ML wheels are built and tested against; "
            "newer builds are both faster and better supported."
        )

    return notes
