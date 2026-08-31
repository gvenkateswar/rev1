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

import importlib
import os
import platform
import subprocess
import sys
from pathlib import Path

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
            "Running x86_64 Python under Rosetta on Apple Silicon. Expect this "
            "run to CRASH, not merely to be slow: the x86 wheels load two "
            "copies of the OpenMP runtime into one process, and the result is "
            "a segmentation fault partway through -- usually during "
            "diarization, with no traceback, because the crash happens below "
            "Python. It is also several times slower. Install a native arm64 "
            "Python (e.g. python.org's universal2 build or "
            "`brew install python@3.12`), make a fresh venv with it, and "
            "activate that venv before starting the app."
        )

    if sys.version_info < (3, 10):
        notes.append(
            f"Python {sys.version_info[0]}.{sys.version_info[1]} is older "
            "than the 3.10+ these ML wheels are built and tested against; "
            "newer builds are both faster and better supported."
        )

    return notes


def require(module: str, *, purpose: str, install: str):
    """Import *module*, or raise a RuntimeError that names the real problem.

    A plain ``except ImportError`` around an optional dependency is a trap:
    ``ModuleNotFoundError`` subclasses ``ImportError``, so a failure *inside*
    the dependency's own import chain (a broken transitive dependency) is
    caught by the same handler and reported as "not installed". That sends
    people to run an install command that reinstalls something already
    present and cannot possibly help, while the actual failing module is
    never named.

    ``ImportError.name`` tells the two cases apart: it is the module that
    could not be found, which is *module* itself only when *module* really is
    absent.

    :param purpose: why this pipeline needs it, e.g. "needed to recognise
        speakers" -- shown so the message says what stopped working.
    :param install: the command that fixes a genuine absence.
    """
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise RuntimeError(_import_error_message(module, purpose, install, exc)) from exc


def _import_error_message(
    module: str, purpose: str, install: str, exc: ImportError
) -> str:
    missing = getattr(exc, "name", None)
    root = module.split(".")[0]

    if missing is not None and missing in (module, root):
        return f"{module} is not installed ({purpose}). Run: {install}"

    blame = f"its dependency {missing}" if missing else "one of its imports"
    return (
        f"{module} is installed but failed to import ({purpose}): {blame} "
        f"could not be loaded.\n"
        f"  {type(exc).__name__}: {exc}\n"
        f"Reinstalling {module} will not fix this -- the broken package is "
        f"{missing or 'further down its dependency chain'}. "
        f"Run `python -c \"import {module}\"` for the full traceback."
    )


# Streamlit re-executes its entry script on every interaction, so writing the
# notes inline reprinted the same paragraphs on every rerun. Module state
# survives that -- modules are imported once per process, only the script is
# re-run -- which is what lets "once" mean once here.
_ANNOUNCED = False


def announce_environment(stream=None) -> list[str]:
    """Write the environment notes to *stream* the first time, and return them.

    Callers still get the notes on every call, so a UI can keep showing them;
    only the terminal copy is written once.
    """
    global _ANNOUNCED
    notes = environment_warnings()
    if notes and not _ANNOUNCED:
        stream = sys.stderr if stream is None else stream
        for note in notes:
            stream.write(f"Note: {note}\n")
        stream.flush()
        _ANNOUNCED = True
    return notes


# The running code and the code you think you edited are not always the same
# file -- a half-finished pull leaves a new module beside an old one, and the
# symptom is an ImportError with no obvious cause. Showing the commit (and
# whether the tree is dirty) in the UI makes that visible before it bites.
_UNSET = object()
_REVISION = _UNSET      # cached: (short commit, dirty) or None


def git_revision(repo: Path | None = None) -> tuple[str, bool] | None:
    """(short commit, tree-is-modified), or None outside a git checkout.

    Cached: this shells out twice, and the Streamlit script that shows it
    re-runs on every interaction.
    """
    global _REVISION
    if _REVISION is not _UNSET:
        return _REVISION
    _REVISION = _read_git_revision(repo or Path(__file__).resolve().parent)
    return _REVISION


def _read_git_revision(repo: Path) -> tuple[str, bool] | None:
    commit = _git(repo, "rev-parse", "--short", "HEAD")
    if commit is None:
        return None
    # An empty porcelain listing means clean. A *failed* status call is not
    # evidence of cleanliness, so treat it as unknown-and-therefore-dirty
    # rather than quietly claiming the tree matches the commit.
    status = _git(repo, "status", "--porcelain")
    return commit, status is None or bool(status)


def _git(repo: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None                 # no git, or it hung
    if proc.returncode != 0:
        return None                 # not a checkout, or no commits yet
    return proc.stdout.strip()


def build_id() -> str:
    """Version and commit of the code that is actually running.

    e.g. "0.3.0 (a8db1cd)", or "0.3.0 (a8db1cd, modified)" when the working
    tree differs from that commit, or bare "0.3.0" outside a checkout.
    """
    # Imported here, not at module scope: the package imports this module
    # first, so a top-level import would be circular.
    from . import __version__

    return format_build(__version__, git_revision())


def format_build(version: str, revision: tuple[str, bool] | None) -> str:
    if revision is None:
        return version
    commit, modified = revision
    return f"{version} ({commit}{', modified' if modified else ''})"
