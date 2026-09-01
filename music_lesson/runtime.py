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

import ctypes
import os
import platform
import subprocess
import sys
from functools import lru_cache

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


def environment_summary() -> str:
    """One line saying what this process actually runs on.

    The architecture question is subtler than ``platform.machine()`` on a Mac:
    an x86_64 Python on an M-series chip reports ``x86_64`` and *works*, while
    Rosetta quietly translates every instruction — the ML stack runs 2-4x
    slower and pulls Intel-only native wheels (whose OpenMP runtime is the one
    that aborts the process). So on macOS we also ask the kernel whether this
    process is translated, which is the fact worth surfacing.
    """
    line = f"Python {platform.python_version()} · {platform.machine()}"
    if sys.platform != "darwin":
        return line
    translated = _rosetta_translated()
    if translated is True:
        return (
            line + " — translated by Rosetta on Apple silicon; "
            "an arm64 Python would run 2-4x faster"
        )
    if translated is False and platform.machine() == "arm64":
        return line + " (Apple silicon, native)"
    return line


def _rosetta_translated() -> bool | None:
    """Ask the macOS kernel if this process runs under Rosetta 2.

    ``sysctl.proc_translated`` is 1 under Rosetta and 0 native; the sysctl does
    not exist at all on Intel hardware (or anything might fail in a sandbox),
    so None means "could not tell", which callers must not read as native.
    """
    try:
        libc = ctypes.CDLL(None)
        value = ctypes.c_int(0)
        size = ctypes.c_size_t(ctypes.sizeof(value))
        result = libc.sysctlbyname(
            b"sysctl.proc_translated",
            ctypes.byref(value), ctypes.byref(size), None, 0,
        )
        if result != 0:
            return None
        return bool(value.value)
    except Exception:
        return None


@lru_cache(maxsize=1)
def build_info() -> str:
    """Which build of this app is running: version, commit, commit time.

    Answers the recurring debugging question "did the git pull actually reach
    the app I have open?" — the sidebar shows this string, so a stale commit
    id or a missing one settles it at a glance. Falls back to the bare
    version when the package runs outside a git checkout. Uncommitted edits
    are flagged, because "8fb739e plus local changes" and "8fb739e" do not
    behave the same.
    """
    from music_lesson import __version__

    label = f"v{__version__}"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        head = subprocess.run(
            ["git", "-C", root, "log", "-1", "--format=%h %cI"],
            capture_output=True, text=True, timeout=3,
        )
        if head.returncode != 0 or not head.stdout.strip():
            return label
        sha, _, stamp = head.stdout.strip().partition(" ")
        when = stamp[:16].replace("T", " ")
        dirty = subprocess.run(
            ["git", "-C", root, "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, timeout=3,
        )
        suffix = (
            " + local changes"
            if dirty.returncode == 0 and dirty.stdout.strip() else ""
        )
        return f"{label} · {sha} · {when}{suffix}"
    except Exception:
        return label
