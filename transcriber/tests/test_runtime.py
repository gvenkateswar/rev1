"""Tests for the OpenMP guard that keeps macOS from aborting the process.

The failure this prevents is an uncatchable abort(), so these tests pin the
one thing that can prevent it: the flag being set before anything imports
torch or ctranslate2.
"""
from __future__ import annotations

import subprocess

import pytest

from transcriber import runtime


def test_flag_is_set_on_a_clean_environment():
    env: dict = {}
    assert runtime.configure_openmp(env) is True
    assert env["KMP_DUPLICATE_LIB_OK"] == "TRUE"


def test_an_existing_value_is_left_alone():
    """A user who set this deliberately gets to keep their choice."""
    env = {"KMP_DUPLICATE_LIB_OK": "FALSE"}
    assert runtime.configure_openmp(env) is False
    assert env["KMP_DUPLICATE_LIB_OK"] == "FALSE"


def test_opt_out_skips_the_fix():
    env = {"TRANSCRIBER_NO_OMP_FIX": "1"}
    assert runtime.configure_openmp(env) is False
    assert "KMP_DUPLICATE_LIB_OK" not in env


def test_is_idempotent():
    env: dict = {}
    runtime.configure_openmp(env)
    assert runtime.configure_openmp(env) is False
    assert env["KMP_DUPLICATE_LIB_OK"] == "TRUE"


def test_importing_the_package_sets_the_flag(monkeypatch):
    """The whole point: importing transcriber must be enough."""
    import os

    monkeypatch.delenv("KMP_DUPLICATE_LIB_OK", raising=False)
    code = "import transcriber, os; print(os.environ.get('KMP_DUPLICATE_LIB_OK'))"
    out = subprocess.run(
        ["python3", "-c", code], capture_output=True, text=True,
        # runtime.py -> transcriber/ -> repo root, which is what must be on
        # sys.path for `import transcriber` to resolve.
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(runtime.__file__))),
    )
    assert out.stdout.strip() == "TRUE", out.stderr


# --- Rosetta detection ----------------------------------------------------- #
def test_rosetta_is_false_off_darwin(monkeypatch):
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    assert runtime.is_rosetta() is False


def test_rosetta_true_when_sysctl_says_translated(monkeypatch):
    monkeypatch.setattr(runtime.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        runtime.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="1\n", stderr=""))
    assert runtime.is_rosetta() is True


def test_rosetta_false_on_native_arm(monkeypatch):
    monkeypatch.setattr(runtime.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        runtime.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="0\n", stderr=""))
    assert runtime.is_rosetta() is False


@pytest.mark.parametrize("boom", [OSError("no sysctl"),
                                  subprocess.TimeoutExpired("sysctl", 2)])
def test_rosetta_survives_a_broken_sysctl(monkeypatch, boom):
    """Losing the advisory warning is fine; crashing on it is not."""
    def raise_it(*a, **k):
        raise boom

    monkeypatch.setattr(runtime.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(runtime.subprocess, "run", raise_it)
    assert runtime.is_rosetta() is False


def test_rosetta_warning_names_the_fix(monkeypatch):
    monkeypatch.setattr(runtime, "is_rosetta", lambda: True)
    notes = runtime.environment_warnings()
    assert any("arm64" in n for n in notes)


def test_no_warnings_on_a_healthy_setup(monkeypatch):
    monkeypatch.setattr(runtime, "is_rosetta", lambda: False)
    monkeypatch.setattr(runtime.sys, "version_info", (3, 12, 0))
    assert runtime.environment_warnings() == []


def test_old_python_is_flagged(monkeypatch):
    monkeypatch.setattr(runtime, "is_rosetta", lambda: False)
    monkeypatch.setattr(runtime.sys, "version_info", (3, 9, 0))
    assert any("3.9" in n for n in runtime.environment_warnings())


# --- pyannote token argument ----------------------------------------------- #
class _V4Pipeline:
    """pyannote.audio 4.x: the argument is `token`."""

    @staticmethod
    def from_pretrained(checkpoint, revision=None, hparams_file=None,
                        subfolder=None, token=None, cache_dir=None):
        return None


class _V3Pipeline:
    """pyannote.audio 3.x: the argument is `use_auth_token`."""

    @staticmethod
    def from_pretrained(checkpoint, hparams_file=None, use_auth_token=None,
                        cache_dir=None):
        return None


def test_token_kwarg_matches_pyannote_4():
    from transcriber.diarize import _token_kwarg

    assert _token_kwarg(_V4Pipeline, "hf_abc") == {"token": "hf_abc"}


def test_token_kwarg_matches_pyannote_3():
    """The 3.x name must still work; passing the wrong one is a TypeError."""
    from transcriber.diarize import _token_kwarg

    assert _token_kwarg(_V3Pipeline, "hf_abc") == {"use_auth_token": "hf_abc"}


def test_token_kwarg_is_accepted_by_the_signature_it_came_from():
    """The whole point: the kwarg we build must actually be callable."""
    from transcriber.diarize import _token_kwarg

    for cls in (_V3Pipeline, _V4Pipeline):
        cls.from_pretrained("ckpt", **_token_kwarg(cls, "hf_abc"))
