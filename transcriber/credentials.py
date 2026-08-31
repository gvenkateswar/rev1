"""Where the Hugging Face token comes from.

A token is a credential. It does not belong in the source, in a command line
(shells keep history), in a screenshot of the sidebar, or in a chat message.
It belongs in a file only you can read, or in the environment.

Lookup order, first hit wins:

1. a token passed in directly (``--hf-token``, the GUI field)
2. ``HF_TOKEN`` or ``HUGGING_FACE_HUB_TOKEN`` in the environment
3. ``~/.transcriber/hf_token`` -- ours, one line, edit it whenever it changes
4. ``~/.cache/huggingface/token`` -- what ``huggingface-cli login`` writes

4 exists so that setting the token up the way Hugging Face documents just
works. 3 exists because it sits beside the speaker store, under the same
``TRANSCRIBER_HOME``, so one directory holds everything private to this tool.

Nothing here logs or returns the token as part of a message. Callers get the
token and, separately, where it came from, so they can say "using the token
from ~/.transcriber/hf_token" without printing the secret.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

ENV_VARS = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")


def token_file() -> Path:
    """Our own token file, beside the speaker store."""
    home = os.environ.get("TRANSCRIBER_HOME")
    base = Path(home) if home else Path.home() / ".transcriber"
    return base / "hf_token"


def huggingface_token_file() -> Path:
    """Where ``huggingface-cli login`` puts it."""
    hf_home = os.environ.get("HF_HOME")
    base = Path(hf_home) if hf_home else Path.home() / ".cache" / "huggingface"
    return base / "token"


def resolve_hf_token(explicit: str | None = None) -> tuple[str | None, str]:
    """Return (token, where it came from). Both are None/"" when there is none.

    The second value is safe to show a user; the first never is.
    """
    if explicit:
        return explicit.strip(), "the value you passed in"

    for name in ENV_VARS:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value, f"${name}"

    for path in (token_file(), huggingface_token_file()):
        value = _read_first_line(path)
        if value:
            return value, str(path)

    return None, ""


def _read_first_line(path: Path) -> str | None:
    """First non-empty line of *path*, or None if it cannot be read.

    Only the first line: an editor leaves a trailing newline, and a file with
    a stray second line should not silently produce a token with a newline in
    the middle of it.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # Absent, unreadable, or not text. None of those are worth an
        # exception -- there are other places left to look.
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def permission_warning(path: Path) -> str | None:
    """A note if *path* is readable by anyone but its owner, else None.

    A token file everyone on the machine can read is not much better than no
    token file, and the mistake is invisible until it matters.
    """
    try:
        mode = path.stat().st_mode
    except OSError:
        return None
    if not mode & (stat.S_IRWXG | stat.S_IRWXO):
        return None
    return (
        f"{path} is readable by other users on this machine. "
        f"Restrict it with: chmod 600 {path}"
    )


def setup_help() -> str:
    """How to put the token somewhere it will be found. Shown on failure."""
    return (
        "Get a token at https://hf.co/settings/tokens, accept the licence at\n"
        "https://hf.co/pyannote/speaker-diarization-3.1, then store it once:\n"
        "\n"
        f"  printf '%s' 'hf_...' > {token_file()} && chmod 600 {token_file()}\n"
        "\n"
        "or, using Hugging Face's own tooling:\n"
        "\n"
        "  huggingface-cli login\n"
        "\n"
        "Either is picked up automatically from then on. $HF_TOKEN also works.\n"
        "Avoid passing it on the command line -- your shell records that."
    )
