"""Tests for Hugging Face token resolution.

The token is a credential, so two things matter as much as finding it: never
returning it as part of a message, and never having to type it again.
"""
from __future__ import annotations

import stat

import pytest

from transcriber import credentials

TOKEN = "hf_notarealtoken"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """No ambient token, and both file locations inside the tmp dir."""
    for name in credentials.ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TRANSCRIBER_HOME", str(tmp_path / "transcriber"))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    (tmp_path / "transcriber").mkdir()
    (tmp_path / "hf").mkdir()


def test_nothing_anywhere_resolves_to_nothing():
    assert credentials.resolve_hf_token() == (None, "")


def test_an_explicit_token_wins():
    token, source = credentials.resolve_hf_token(TOKEN)
    assert token == TOKEN
    assert source == "the value you passed in"


def test_the_environment_is_used_when_nothing_is_passed(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", TOKEN)
    assert credentials.resolve_hf_token() == (TOKEN, "$HF_TOKEN")


def test_the_alternate_environment_name_also_works(monkeypatch):
    monkeypatch.setenv("HUGGING_FACE_HUB_TOKEN", TOKEN)
    token, source = credentials.resolve_hf_token()
    assert (token, source) == (TOKEN, "$HUGGING_FACE_HUB_TOKEN")


def test_our_token_file_is_read():
    credentials.token_file().write_text(TOKEN + "\n")
    token, source = credentials.resolve_hf_token()
    assert token == TOKEN
    assert source == str(credentials.token_file())


def test_the_huggingface_cli_login_file_is_read():
    """`huggingface-cli login` is the documented way; it should just work."""
    credentials.huggingface_token_file().write_text(TOKEN)
    token, source = credentials.resolve_hf_token()
    assert token == TOKEN
    assert source == str(credentials.huggingface_token_file())


def test_our_file_takes_precedence_over_the_cli_one():
    credentials.token_file().write_text("hf_ours")
    credentials.huggingface_token_file().write_text("hf_theirs")
    assert credentials.resolve_hf_token()[0] == "hf_ours"


def test_the_environment_takes_precedence_over_both_files(monkeypatch):
    credentials.token_file().write_text("hf_fromfile")
    monkeypatch.setenv("HF_TOKEN", TOKEN)
    assert credentials.resolve_hf_token()[0] == TOKEN


def test_surrounding_whitespace_is_stripped():
    """An editor leaves a trailing newline; a token with one in it fails."""
    credentials.token_file().write_text(f"  {TOKEN}  \n\n")
    assert credentials.resolve_hf_token()[0] == TOKEN


def test_only_the_first_line_is_used():
    credentials.token_file().write_text(f"{TOKEN}\nsome note to self\n")
    assert credentials.resolve_hf_token()[0] == TOKEN


def test_an_empty_file_is_not_a_token():
    credentials.token_file().write_text("\n   \n")
    assert credentials.resolve_hf_token() == (None, "")


def test_an_unreadable_file_falls_through_rather_than_raising():
    path = credentials.token_file()
    path.mkdir()                       # a directory where a file was expected
    assert credentials.resolve_hf_token() == (None, "")


def test_an_empty_explicit_value_is_not_a_token(monkeypatch):
    """The GUI field is "" when untouched; that must not shadow the file."""
    credentials.token_file().write_text(TOKEN)
    assert credentials.resolve_hf_token("")[0] == TOKEN


# --------------------------------------------------------------------------- #
# The token itself must never be in a message
# --------------------------------------------------------------------------- #
def test_the_source_never_contains_the_token(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", TOKEN)
    _token, source = credentials.resolve_hf_token()
    assert TOKEN not in source


def test_the_setup_help_names_no_real_token():
    assert "hf_..." in credentials.setup_help()
    assert TOKEN not in credentials.setup_help()


# --------------------------------------------------------------------------- #
# File permissions
# --------------------------------------------------------------------------- #
def test_a_world_readable_token_file_is_flagged():
    path = credentials.token_file()
    path.write_text(TOKEN)
    path.chmod(0o644)
    note = credentials.permission_warning(path)
    assert note is not None
    assert "chmod 600" in note
    assert TOKEN not in note


def test_an_owner_only_token_file_is_not_flagged():
    path = credentials.token_file()
    path.write_text(TOKEN)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert credentials.permission_warning(path) is None


def test_a_missing_file_is_not_flagged():
    assert credentials.permission_warning(credentials.token_file()) is None
