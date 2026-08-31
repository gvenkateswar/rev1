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


# --- pyannote result unwrapping -------------------------------------------- #
class _Annotation:
    """Stand-in for pyannote.core.Annotation (the bit we use)."""

    def __init__(self, tag):
        self.tag = tag

    def itertracks(self, yield_label=False):
        return iter(())


class _DiarizeOutput:
    """pyannote.audio 4.x wraps the annotations in a dataclass."""

    def __init__(self):
        self.speaker_diarization = _Annotation("overlapping")
        self.exclusive_speaker_diarization = _Annotation("exclusive")
        self.speaker_embeddings = None


def test_prefers_the_exclusive_annotation_on_pyannote_4():
    """Overlapping turns make word-to-speaker mapping arbitrary, so take the
    annotation pyannote documents as being for downstream transcription."""
    from transcriber.diarize import _as_annotation

    assert _as_annotation(_DiarizeOutput()).tag == "exclusive"


def test_falls_back_to_speaker_diarization_when_exclusive_is_absent():
    from transcriber.diarize import _as_annotation

    result = _DiarizeOutput()
    del result.exclusive_speaker_diarization
    assert _as_annotation(result).tag == "overlapping"


def test_accepts_a_bare_annotation_from_pyannote_3():
    from transcriber.diarize import _as_annotation

    bare = _Annotation("bare")
    assert _as_annotation(bare) is bare


def test_unrecognised_result_raises_a_named_error():
    from transcriber.diarize import _as_annotation

    with pytest.raises(RuntimeError, match="Unexpected pyannote result type"):
        _as_annotation(object())


# --------------------------------------------------------------------------- #
# require(): telling "not installed" apart from "installed but broken"
# --------------------------------------------------------------------------- #
def test_require_returns_the_module():
    assert runtime.require("json", purpose="p", install="i").dumps([1]) == "[1]"


def test_a_genuinely_absent_module_says_install_it():
    with pytest.raises(RuntimeError) as err:
        runtime.require(
            "no_such_module_xyz", purpose="needed to test", install="pip install xyz"
        )
    message = str(err.value)
    assert "is not installed" in message
    assert "pip install xyz" in message


def test_an_absent_parent_is_reported_against_the_module_asked_for():
    """`sklearn.cluster` missing because sklearn is missing is still absence."""
    with pytest.raises(RuntimeError) as err:
        runtime.require(
            "no_such_module_xyz.sub", purpose="p", install="pip install xyz"
        )
    assert "is not installed" in str(err.value)


def test_a_broken_dependency_is_not_reported_as_absence(monkeypatch):
    """The regression: resemblyzer was installed, its dependency was not.

    ModuleNotFoundError subclasses ImportError, so the old guard blamed the
    package the user had and told them to reinstall it.
    """
    def explode(name):
        raise ModuleNotFoundError("No module named 'webrtcvad'", name="webrtcvad")

    monkeypatch.setattr(runtime.importlib, "import_module", explode)

    with pytest.raises(RuntimeError) as err:
        runtime.require(
            "resemblyzer",
            purpose="needed to recognise speakers",
            install="pip install resemblyzer",
        )
    message = str(err.value)
    assert "is not installed" not in message
    assert "webrtcvad" in message
    assert "Reinstalling resemblyzer will not fix this" in message
    assert "ModuleNotFoundError" in message


def test_a_broken_dependency_keeps_the_original_exception_chained(monkeypatch):
    cause = ModuleNotFoundError("No module named 'numba'", name="numba")

    def explode(name):
        raise cause

    monkeypatch.setattr(runtime.importlib, "import_module", explode)

    with pytest.raises(RuntimeError) as err:
        runtime.require("librosa", purpose="p", install="i")
    assert err.value.__cause__ is cause


def test_an_import_error_without_a_module_name_still_reports_the_cause(monkeypatch):
    """`from x import y` where y is gone raises ImportError with no useful name."""
    def explode(name):
        raise ImportError("cannot import name 'binary_dilation'")

    monkeypatch.setattr(runtime.importlib, "import_module", explode)

    with pytest.raises(RuntimeError) as err:
        runtime.require("resemblyzer", purpose="p", install="i")
    message = str(err.value)
    assert "is not installed" not in message
    assert "cannot import name 'binary_dilation'" in message


# --------------------------------------------------------------------------- #
# announce_environment(): once per process, not once per Streamlit rerun
# --------------------------------------------------------------------------- #
class Recorder:
    def __init__(self):
        self.written = []

    def write(self, text):
        self.written.append(text)

    def flush(self):
        pass


def test_the_notes_are_written_only_once(monkeypatch):
    """Streamlit re-runs its script constantly; the terminal copy must not."""
    monkeypatch.setattr(runtime, "environment_warnings", lambda: ["slow python"])
    monkeypatch.setattr(runtime, "_ANNOUNCED", False)

    out = Recorder()
    first = runtime.announce_environment(out)
    second = runtime.announce_environment(out)

    assert out.written == ["Note: slow python\n"]
    # The caller still gets them every time, so a page can keep showing them.
    assert first == second == ["slow python"]


def test_a_clean_environment_writes_nothing_and_stays_unannounced(monkeypatch):
    monkeypatch.setattr(runtime, "environment_warnings", lambda: [])
    monkeypatch.setattr(runtime, "_ANNOUNCED", False)

    out = Recorder()
    assert runtime.announce_environment(out) == []
    assert out.written == []
    assert runtime._ANNOUNCED is False


def test_rosetta_is_described_as_a_crash_not_a_slowdown(monkeypatch):
    """It segfaults. Calling that "slower than it needs to be" misled a user
    into running it anyway and losing a transcription to a silent crash."""
    monkeypatch.setattr(runtime, "is_rosetta", lambda: True)
    monkeypatch.setattr(runtime.sys, "version_info", (3, 12, 0))
    [note] = runtime.environment_warnings()
    assert "CRASH" in note
    assert "arm64" in note


# --------------------------------------------------------------------------- #
# build_id(): which code is actually running
# --------------------------------------------------------------------------- #
def test_a_clean_checkout_shows_version_and_commit():
    assert runtime.format_build("0.3.0", ("a8db1cd", False)) == "0.3.0 (a8db1cd)"


def test_a_modified_tree_says_so():
    """The half-pulled checkout that breaks imports looks exactly like this."""
    assert runtime.format_build("0.3.0", ("a8db1cd", True)) == \
        "0.3.0 (a8db1cd, modified)"


def test_outside_a_checkout_the_version_stands_alone():
    assert runtime.format_build("0.3.0", None) == "0.3.0"


def test_the_revision_is_read_from_the_repo(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "_REVISION", runtime._UNSET)
    monkeypatch.setattr(runtime, "_git", lambda repo, *args:
                        "deadbee" if args[0] == "rev-parse" else "")
    assert runtime.git_revision(tmp_path) == ("deadbee", False)


def test_a_dirty_tree_is_detected_from_porcelain_output(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "_REVISION", runtime._UNSET)
    monkeypatch.setattr(runtime, "_git", lambda repo, *args:
                        "deadbee" if args[0] == "rev-parse" else " M output.py")
    assert runtime.git_revision(tmp_path) == ("deadbee", True)


def test_an_unreadable_status_is_reported_as_modified(monkeypatch, tmp_path):
    """Not knowing is not the same as knowing it is clean."""
    monkeypatch.setattr(runtime, "_REVISION", runtime._UNSET)
    monkeypatch.setattr(runtime, "_git", lambda repo, *args:
                        "deadbee" if args[0] == "rev-parse" else None)
    assert runtime.git_revision(tmp_path) == ("deadbee", True)


def test_no_git_at_all_is_not_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "_REVISION", runtime._UNSET)
    monkeypatch.setattr(runtime, "_git", lambda repo, *args: None)
    assert runtime.git_revision(tmp_path) is None


def test_a_missing_git_binary_is_not_an_error(tmp_path, monkeypatch):
    def no_git(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(runtime.subprocess, "run", no_git)
    assert runtime._git(tmp_path, "rev-parse") is None


def test_the_revision_is_looked_up_only_once(monkeypatch, tmp_path):
    """It shells out twice, and the Streamlit script showing it re-runs a lot."""
    monkeypatch.setattr(runtime, "_REVISION", runtime._UNSET)
    calls = []
    monkeypatch.setattr(runtime, "_read_git_revision",
                        lambda repo: calls.append(repo) or ("abc1234", False))
    runtime.git_revision(tmp_path)
    runtime.git_revision(tmp_path)
    assert len(calls) == 1


def test_build_id_names_this_package_version():
    import transcriber

    assert runtime.build_id().startswith(transcriber.__version__)
